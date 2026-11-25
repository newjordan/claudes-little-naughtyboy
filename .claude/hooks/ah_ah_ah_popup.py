#!/usr/bin/env python3
"""Detect an LLM-research cutoff or reroute onto Opus 4 and show a lockout popup.

Claude Code runs this script as a command hook. On a real hook event the
process must stay quiet and exit 0: Stop treats stdout as a decision, and a
non-zero status is a hook error. The popup is a detached child process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

POPUP_TEXT = "ah ah ah, your not allowed to do that"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE_PATH = SCRIPT_DIR / "assets" / "dario-lockout.png"
DEFAULT_FRAME_PATHS = [
    SCRIPT_DIR / "assets" / "dario-lockout-frame-1.png",
    SCRIPT_DIR / "assets" / "dario-lockout-frame-2.png",
    SCRIPT_DIR / "assets" / "dario-lockout-frame-3.png",
]
DEFAULT_DEBOUNCE_SECONDS = 30
DEFAULT_DURATION_MS = 9000
DEFAULT_FRAME_MS = 180
DEFAULT_WINDOW_CHARS = 520
DEFAULT_BUFFER_CHARS = 4000
TRANSCRIPT_TAIL_BYTES = 160_000
MAX_IMAGE_SIDE = 440

# The three cues can appear in any order. The old pattern list missed
# "cutoff" / "cut-off" / "opus-4.8", and it treated plain "routing" or a
# cutoff that never mentioned LLM research as a hit.
LLM_RESEARCH_RE = re.compile(r"\bllm[\s-]+research\b", re.IGNORECASE)
ACTION_RE = re.compile(
    r"\b(?:cut(?:s|ting)?(?:\s+you)?\s+off|cut[\s-]*off|re[\s-]*rout(?:e|es|ed|ing))\b",
    re.IGNORECASE,
)
OPUS_RE = re.compile(r"\bopus[\s-]*4(?:[.\-]\d+)?\b", re.IGNORECASE)
_SKIPPED_LIVE_FIELDS = frozenset({"transcript_path", "cwd"})


@dataclass(frozen=True, slots=True)
class Match:
    """One positive detection."""

    summary: str
    fingerprint: str
    custom: bool = False


@dataclass(frozen=True, slots=True)
class _Cue:
    start: int
    kind: str
    text: str


def _write_private(path: Path, text: str, *, append: bool = False) -> None:
    """Write state that may contain conversation text so it is not world-readable."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "a" if append else "w", encoding="utf-8") as handle:
        handle.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        return


def _debug(message: str) -> None:
    if os.environ.get("AH_AH_AH_DEBUG") != "1":
        return
    log_path = _state_dir() / "claude-ah-ah-ah-hook.log"
    try:
        _write_private(
            log_path,
            f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n",
            append=True,
        )
    except OSError:
        return


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw, 10)
    except ValueError:
        _debug(f"{name} is not an integer: {raw!r}; using {default}")
        return default


def _state_dir() -> Path:
    raw = os.environ.get("AH_AH_AH_STATE_DIR")
    path = Path(raw) if raw else Path(tempfile.gettempdir())
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _debug(f"state dir unavailable: {exc}")
        fallback = Path(tempfile.gettempdir())
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    return path


def _safe_token(value: str, limit: int = 80) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return (safe or "default")[:limit]


def _session_token(payload: dict[str, Any]) -> str:
    return _safe_token(str(payload.get("session_id") or "no-session"))


def _snippet(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fingerprint(*parts: str) -> str:
    normalized = "|".join(re.sub(r"[\s-]+", "", part.casefold()) for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin is None or bool(sys.stdin.isatty())
    except Exception as exc:
        _debug(f"stdin tty check failed: {exc}")
        return False


def _read_stdin() -> str:
    if _stdin_is_tty():
        return ""
    try:
        return sys.stdin.read()
    except Exception as exc:
        _debug(f"stdin read failed: {exc}")
        return ""


def _loads_json(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        _debug(f"invalid JSON input: {exc}")
        return {"_raw_stdin": raw}
    if isinstance(value, dict):
        return value
    return {"_json_value": value}


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _live_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in payload.items():
        if key in _SKIPPED_LIVE_FIELDS:
            continue
        parts.extend(_iter_strings(value))
    return "\n".join(part for part in parts if part)


def _read_transcript_tail(path_value: Any) -> str:
    if not isinstance(path_value, str) or not path_value:
        return ""
    path = Path(path_value)
    try:
        if not path.is_file():
            return ""
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > TRANSCRIPT_TAIL_BYTES:
                handle.seek(size - TRANSCRIPT_TAIL_BYTES)
            data = handle.read(TRANSCRIPT_TAIL_BYTES)
        return data.decode("utf-8", errors="replace")
    except OSError as exc:
        _debug(f"transcript read skipped: {exc}")
        return ""


def _buffer_chars() -> int:
    return max(0, _env_int("AH_AH_AH_BUFFER_CHARS", DEFAULT_BUFFER_CHARS))


def _buffer_path(payload: dict[str, Any]) -> Path:
    return _state_dir() / f"claude-ah-ah-ah-{_session_token(payload)}.buf"


def _update_live_buffer(payload: dict[str, Any], live_text: str) -> str:
    """Remember recent hook text so a cue split across MessageDisplay batches still matches."""
    limit = _buffer_chars()
    path = _buffer_path(payload)
    prior = ""
    try:
        prior = path.read_text(encoding="utf-8")
    except OSError:
        prior = ""
    if not live_text:
        return prior[-limit:] if limit else ""
    if prior.endswith(live_text):
        combined = prior
    elif prior:
        combined = f"{prior}\n{live_text}"
    else:
        combined = live_text
    combined = combined[-limit:]
    try:
        _write_private(path, combined)
    except OSError as exc:
        _debug(f"buffer write failed: {exc}")
    return combined


def haystacks_for(payload: dict[str, Any], *, remember: bool) -> list[str]:
    """Texts worth scanning for this event.

    The rolling buffer is separate from the transcript. Concatenating a long
    buffer in between them pushes the newest delta away from the transcript tail
    and hides a split phrase. Each candidate is searched on its own.
    """
    live = _live_text(payload)
    chunks: list[str] = []
    if live:
        chunks.append(live)
    if remember and live and _buffer_chars() > 0:
        buffered = _update_live_buffer(payload, live)
        if buffered and buffered != live:
            chunks.append(buffered)
    transcript = _read_transcript_tail(payload.get("transcript_path"))
    if transcript and live:
        chunks.append(f"{transcript}\n{live}")
    elif transcript:
        chunks.append(transcript)
    return chunks


def _custom_patterns() -> list[str] | None:
    raw = os.environ.get("AH_AH_AH_PATTERNS")
    if raw is None:
        return None
    return [item.strip() for item in raw.split(";;") if item.strip()]


def _window_chars() -> int:
    return max(0, _env_int("AH_AH_AH_WINDOW", DEFAULT_WINDOW_CHARS))


def _match_custom(text: str, patterns: list[str]) -> Match | None:
    for pattern in patterns:
        try:
            found = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        except re.error as exc:
            _debug(f"bad regex ignored: {pattern!r}: {exc}")
            continue
        if not found:
            continue
        snippet = _snippet(found.group(0))[:160]
        return Match(
            summary=f"custom pattern matched: {snippet or pattern}",
            fingerprint=_fingerprint("custom", pattern, snippet),
            custom=True,
        )
    return None


def _match_cues(text: str) -> Match | None:
    window = _window_chars()
    cues: list[_Cue] = []
    for kind, pattern in (
        ("research", LLM_RESEARCH_RE),
        ("action", ACTION_RE),
        ("opus", OPUS_RE),
    ):
        for found in pattern.finditer(text):
            cues.append(_Cue(found.start(), kind, _snippet(found.group(0))))
    if len({cue.kind for cue in cues}) < 3:
        return None
    cues.sort(key=lambda cue: (cue.start, cue.kind))
    counts = {"research": 0, "action": 0, "opus": 0}
    left = 0
    for right, cue in enumerate(cues):
        counts[cue.kind] += 1
        while cue.start - cues[left].start > window:
            counts[cues[left].kind] -= 1
            left += 1
        if not (counts["research"] and counts["action"] and counts["opus"]):
            continue
        chosen: dict[str, _Cue] = {}
        for item in cues[left : right + 1]:
            chosen.setdefault(item.kind, item)
        span = cue.start - cues[left].start
        summary = (
            f'"{chosen["research"].text}" + "{chosen["action"].text}" + '
            f'"{chosen["opus"].text}" within {span} characters'
        )
        return Match(
            summary=summary,
            fingerprint=_fingerprint(
                chosen["research"].text,
                chosen["action"].text,
                chosen["opus"].text,
            ),
        )
    return None


def find_match(text: str) -> Match | None:
    if not text:
        return None
    custom = _custom_patterns()
    if custom is not None:
        return _match_custom(text, custom)
    return _match_cues(text)


def find_payload_match(payload: dict[str, Any], *, remember: bool) -> Match | None:
    for text in haystacks_for(payload, remember=remember):
        match = find_match(text)
        if match is not None:
            _debug(f"matched: {match.summary}")
            return match
    return None


def format_report(match: Match | None) -> str:
    if match is None:
        return "NO_MATCH\nno llm-research cutoff or reroute near Opus 4"
    return f"MATCH\n{match.summary}"


def _debounce_seconds() -> int:
    value = _env_int("AH_AH_AH_DEBOUNCE_SECONDS", DEFAULT_DEBOUNCE_SECONDS)
    return value if value > 0 else 0


def _debounce_path(payload: dict[str, Any], match: Match) -> Path:
    session = _session_token(payload)
    return _state_dir() / f"claude-ah-ah-ah-{session}-{match.fingerprint}.last"


def should_suppress(payload: dict[str, Any], match: Match) -> bool:
    """Suppress a repeat of the same cues in this session.

    MessageDisplay and Stop observe one reply through different ids, so the key
    is the session plus the cue text rather than message_id. A Stop event with
    no message id used to share one global key and swallow later, different alerts.
    """
    seconds = _debounce_seconds()
    if seconds <= 0:
        return False
    path = _debounce_path(payload, match)
    now = time.time()
    try:
        previous = float(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    if previous is not None and now - previous < seconds:
        _debug("trigger suppressed by debounce")
        return True
    try:
        _write_private(path, str(now))
    except OSError as exc:
        _debug(f"debounce write failed: {exc}")
    return False


def _pythonw_executable() -> str:
    executable = Path(sys.executable)
    if os.name == "nt" and executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return sys.executable


def _launch_popup(reason: str = "") -> None:
    env = os.environ.copy()
    env["AH_AH_AH_POPUP_REASON"] = _clean_reason(reason)
    cmd = [_pythonw_executable(), str(Path(__file__).resolve()), "--popup-child"]
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        detached = getattr(subprocess, "DETACHED_PROCESS", 0)
        new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = detached | new_group
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        _debug(f"popup launch failed: {exc}")


def resolve_frame_paths() -> list[Path]:
    explicit = os.environ.get("AH_AH_AH_FRAMES")
    if explicit:
        paths = [Path(item) for item in explicit.split(os.pathsep) if item]
        if paths:
            return paths
    if all(path.is_file() for path in DEFAULT_FRAME_PATHS):
        return list(DEFAULT_FRAME_PATHS)
    return [Path(os.environ.get("AH_AH_AH_IMAGE", str(DEFAULT_IMAGE_PATH)))]


def animation_sequence(frame_count: int) -> list[int]:
    """Wag frame 1, 2, 3, 2 when all three poses are present."""
    if frame_count >= 3:
        return [0, 1, 2, 1]
    return list(range(frame_count))


def _clean_reason(reason: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", reason).strip()
    return cleaned[:80]


def _reason_caption(reason: str) -> str:
    if not reason:
        return ""
    if reason == "manual test":
        return "Manual test"
    return f"Detected on {reason}"


def _duration_ms() -> int:
    value = _env_int("AH_AH_AH_DURATION_MS", DEFAULT_DURATION_MS)
    if value < 0:
        return DEFAULT_DURATION_MS
    return value


def _frame_ms() -> int:
    value = _env_int("AH_AH_AH_FRAME_MS", DEFAULT_FRAME_MS)
    if value < 0:
        return DEFAULT_FRAME_MS
    return value


def _bell_enabled() -> bool:
    raw = os.environ.get("AH_AH_AH_BELL", "1").strip().casefold()
    return raw not in {"0", "false", "no", "off"}


def _ui_font(root: Any, size: int, *, bold: bool) -> tuple[str, int, str]:
    import tkinter.font as tkfont

    weight = "bold" if bold else "normal"
    try:
        families = set(tkfont.families(root))
    except Exception:
        families = set()
    for name in ("MS Sans Serif", "Tahoma", "Verdana", "Liberation Sans", "DejaVu Sans", "Arial"):
        if name in families:
            return (name, size, weight)
    return ("TkDefaultFont", size, weight)


def _load_photo_frames(root: Any, paths: list[Path], max_side: int) -> list[Any]:
    import tkinter as tk

    photos: list[Any] = []
    try:
        from PIL import Image, ImageTk

        resampling = getattr(Image, "Resampling", Image).LANCZOS
        for path in paths:
            try:
                with Image.open(path) as opened:
                    image = opened.convert("RGBA")
                image.thumbnail((max_side, max_side), resampling)
                photos.append(ImageTk.PhotoImage(image, master=root))
            except Exception as exc:
                _debug(f"image load failed: {path}: {exc}")
        if photos:
            return photos
    except Exception as exc:
        _debug(f"pillow unavailable: {exc}")

    for path in paths:
        try:
            photo = tk.PhotoImage(file=str(path), master=root)
        except tk.TclError as exc:
            _debug(f"tk image load failed: {path}: {exc}")
            continue
        width = max(photo.width(), 1)
        height = max(photo.height(), 1)
        divisor = max(1, int(max(width / max_side, height / max_side)))
        if divisor > 1:
            try:
                photo = photo.subsample(divisor, divisor)
            except tk.TclError as exc:
                _debug(f"tk subsample failed: {path}: {exc}")
                continue
        photos.append(photo)
    return photos


def _draw_placeholder(canvas: Any, width: int, height: int) -> None:
    canvas.create_rectangle(0, 0, width, height, fill="#008080", outline="")
    canvas.create_rectangle(
        70, 36, width - 70, height - 36, fill="#c0c0c0", outline="#404040", width=3
    )
    canvas.create_rectangle(82, 48, width - 82, 84, fill="#000080", outline="#ffffff", width=2)
    canvas.create_text(
        width // 2,
        height // 2,
        text="ah ah ah",
        fill="#000080",
        font=("TkDefaultFont", 18, "bold"),
    )


def _bind_drag(root: Any, widget: Any) -> None:
    state = {"x": 0, "y": 0}

    def start(event: Any) -> None:
        state["x"] = event.x_root - root.winfo_x()
        state["y"] = event.y_root - root.winfo_y()

    def move(event: Any) -> None:
        root.geometry(f"+{event.x_root - state['x']}+{event.y_root - state['y']}")

    widget.bind("<ButtonPress-1>", start)
    widget.bind("<B1-Motion>", move)


def create_popup(root: Any) -> dict[str, Any]:
    """Build the retro dialog. The caller runs the event loop."""
    import tkinter as tk

    reason = _reason_caption(_clean_reason(os.environ.get("AH_AH_AH_POPUP_REASON", "")))
    frame_ms = _frame_ms()
    try:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
    except tk.TclError:
        screen_w, screen_h = 1280, 800
    max_side = min(MAX_IMAGE_SIDE, max(220, screen_w - 160), max(220, screen_h - 280))

    root.title("Access denied")
    root.configure(bg="#c0c0c0")
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass

    shell = tk.Frame(root, bg="#c0c0c0", bd=2, relief="raised")
    shell.pack(fill="both", expand=True)

    title_font = _ui_font(root, 10, bold=True)
    body_font = _ui_font(root, 16, bold=True)
    small_font = _ui_font(root, 9, bold=False)
    button_font = _ui_font(root, 11, bold=True)

    titlebar = tk.Frame(shell, bg="#000080")
    titlebar.pack(fill="x", padx=8, pady=(8, 0))
    title = tk.Label(
        titlebar,
        text="System Message",
        bg="#000080",
        fg="#ffffff",
        font=title_font,
        anchor="w",
        padx=8,
        pady=4,
    )
    title.pack(side="left", fill="both", expand=True)
    close = tk.Button(
        titlebar,
        text="X",
        command=root.destroy,
        bg="#c0c0c0",
        fg="#000000",
        activebackground="#d8d8d8",
        relief="raised",
        bd=2,
        font=title_font,
        cursor="hand2",
        width=2,
        padx=0,
        pady=0,
    )
    close.pack(side="right", padx=(0, 6), pady=4)
    _bind_drag(root, titlebar)
    _bind_drag(root, title)

    message = tk.Label(
        shell,
        text=POPUP_TEXT,
        bg="#c0c0c0",
        fg="#000000",
        font=body_font,
        wraplength=max_side,
        justify="center",
        pady=10,
    )
    message.pack(fill="x", padx=12)

    paths = resolve_frame_paths()
    photos = _load_photo_frames(root, paths, max_side)
    if photos:
        canvas_width = max(photo.width() for photo in photos)
        canvas_height = max(photo.height() for photo in photos)
    else:
        canvas_width, canvas_height = min(max_side, 420), min(max_side, 280)

    image_box = tk.Frame(shell, bg="#c0c0c0", bd=2, relief="sunken")
    image_box.pack(padx=14, pady=(0, 4))
    canvas = tk.Canvas(
        image_box,
        width=canvas_width,
        height=canvas_height,
        bg="#008080",
        highlightthickness=0,
        bd=0,
    )
    canvas.pack()

    image_id = None
    if photos:
        image_id = canvas.create_image(canvas_width // 2, canvas_height // 2, image=photos[0])
    else:
        _draw_placeholder(canvas, canvas_width, canvas_height)

    caption = None
    if reason:
        caption = tk.Label(
            shell,
            text=reason,
            bg="#c0c0c0",
            fg="#000000",
            font=small_font,
            anchor="w",
            padx=6,
            pady=2,
            bd=1,
            relief="sunken",
        )
        caption.pack(fill="x", padx=14, pady=(6, 0))

    ok = tk.Button(
        shell,
        text="OK",
        command=root.destroy,
        bg="#c0c0c0",
        fg="#000000",
        activebackground="#d8d8d8",
        activeforeground="#000000",
        relief="raised",
        bd=3,
        padx=28,
        pady=4,
        font=button_font,
        cursor="hand2",
    )
    ok.pack(pady=12)

    sequence = animation_sequence(len(photos))
    state = {"index": 0}

    def animate() -> None:
        if image_id is not None and len(sequence) > 1:
            state["index"] = (state["index"] + 1) % len(sequence)
            canvas.itemconfig(image_id, image=photos[sequence[state["index"]]])
        if frame_ms > 0 and len(sequence) > 1:
            root.after(frame_ms, animate)

    if frame_ms > 0 and len(sequence) > 1:
        root.after(frame_ms, animate)

    def dismiss(_event: Any = None) -> str:
        for sequence in ("<Escape>", "<Return>", "<KP_Enter>"):
            try:
                root.unbind_all(sequence)
            except tk.TclError:
                pass
        try:
            root.destroy()
        except tk.TclError:
            pass
        return "break"

    def accept(_event: Any = None) -> str:
        try:
            ok.invoke()
        except tk.TclError:
            dismiss()
        return "break"

    close.configure(command=dismiss)
    ok.configure(command=dismiss)
    root.protocol("WM_DELETE_WINDOW", dismiss)
    # bind_all reaches the dialog even when a child widget holds the keyboard.
    # A borderless window often never becomes the focused toplevel on its own.
    root.bind("<Escape>", dismiss)
    root.bind_all("<Escape>", dismiss)
    root.bind("<Return>", accept)
    root.bind_all("<Return>", accept)
    root.bind("<KP_Enter>", accept)
    root.bind_all("<KP_Enter>", accept)

    return {
        "message": message,
        "close": close,
        "ok": ok,
        "canvas": canvas,
        "caption": caption,
        "frames": photos,
        "sequence": sequence,
        "animate": animate,
    }


def present_popup(root: Any) -> None:
    import tkinter as tk

    root.update_idletasks()
    width = max(root.winfo_reqwidth(), 1)
    height = max(root.winfo_reqheight(), 1)
    try:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
    except tk.TclError:
        screen_w, screen_h = width, height
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 3)
    root.geometry(f"{width}x{height}+{x}+{y}")
    duration_ms = _duration_ms()
    if duration_ms > 0:
        root.after(duration_ms, root.destroy)

    def take_focus() -> None:
        try:
            root.lift()
            root.focus_force()
            root.grab_set()
        except tk.TclError as exc:
            _debug(f"popup focus skipped: {exc}")
        if _bell_enabled():
            try:
                root.bell()
            except tk.TclError:
                pass

    # The window has to be mapped before the window manager will give it the keyboard.
    root.after(50, take_focus)


def _show_popup() -> int:
    try:
        import tkinter as tk
    except Exception as exc:
        print(
            "This popup needs Tkinter, and this Python does not provide it.\n"
            "On Debian or Ubuntu, install python3-tk and run --test again.",
            file=sys.stderr,
        )
        _debug(f"tkinter import failed: {exc}")
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Could not open the popup window: {exc}", file=sys.stderr)
        _debug(f"tk root failed: {exc}")
        return 1
    exit_code = 0
    try:
        try:
            root.overrideredirect(True)
        except tk.TclError:
            pass
        create_popup(root)
        present_popup(root)
        root.mainloop()
    except tk.TclError as exc:
        print(f"Could not open the popup window: {exc}", file=sys.stderr)
        _debug(f"popup failed: {exc}")
        exit_code = 1
    finally:
        try:
            if root.winfo_exists():
                root.destroy()
        except Exception:
            pass
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Detect an LLM-research cutoff or reroute onto Opus 4 and show a lockout popup."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 .claude/hooks/ah_ah_ah_popup.py --probe "
            '"llm research cuts you off and re routes you to opus 4.8"\n'
            "  python3 .claude/hooks/ah_ah_ah_popup.py --dry-run < payload.json\n"
            "  python3 .claude/hooks/ah_ah_ah_popup.py --test\n"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--popup-child", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--test", action="store_true", help="show the popup in this terminal")
    mode.add_argument(
        "--probe",
        help="print MATCH or NO_MATCH for one sentence and do not show the popup",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="read hook JSON from stdin and print MATCH or NO_MATCH without a popup",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.popup_child:
        return _show_popup()
    if args.test:
        os.environ.setdefault("AH_AH_AH_POPUP_REASON", "manual test")
        print(
            "Opening the lockout popup. Close it with OK, Enter, or Escape.",
            file=sys.stderr,
        )
        return _show_popup()
    if args.probe is not None:
        match = find_match(args.probe)
        print(format_report(match))
        return 0 if match is not None else 1

    raw = _read_stdin()
    if args.dry_run:
        match = find_payload_match(_loads_json(raw), remember=False)
        print(format_report(match))
        return 0 if match is not None else 1

    if _stdin_is_tty() and not raw:
        parser.print_help(sys.stderr)
        return 2

    payload = _loads_json(raw)
    match = find_payload_match(payload, remember=True)
    if match is not None and not should_suppress(payload, match):
        _launch_popup(str(payload.get("hook_event_name") or "hook"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
