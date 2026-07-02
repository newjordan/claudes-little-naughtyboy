#!/usr/bin/env python3
"""Detect Claude Code model-reroute text and show a local popup."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable


POPUP_TEXT = "ah ah ah, your not allowed to do that"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE_PATH = SCRIPT_DIR / "assets" / "dario-lockout.png"
DEFAULT_FRAME_PATHS = [
    SCRIPT_DIR / "assets" / "dario-lockout-frame-1.png",
    SCRIPT_DIR / "assets" / "dario-lockout-frame-2.png",
    SCRIPT_DIR / "assets" / "dario-lockout-frame-3.png",
]
DEFAULT_DEBOUNCE_SECONDS = 30
TRANSCRIPT_TAIL_BYTES = 160_000

DEFAULT_TRIGGER_REGEXES = [
    r"\bllm\s+research\b.{0,260}\b(?:cut(?:s|ting)?(?:\s+you)?\s+off|re[\s-]?rout(?:e|es|ed|ing)|rout(?:e|es|ed|ing))\b.{0,260}\bopus\s*4(?:[.\-]\d+)?\b",
    r"\b(?:cut(?:s|ting)?(?:\s+you)?\s+off|re[\s-]?rout(?:e|es|ed|ing)|rout(?:e|es|ed|ing))\b.{0,260}\bopus\s*4(?:[.\-]\d+)?\b",
    r"\bopus\s*4\.8\b.{0,260}\b(?:llm\s+research|cut(?:s|ting)?(?:\s+you)?\s+off|re[\s-]?rout|rout)",
]


def _debug(message: str) -> None:
    if os.environ.get("AH_AH_AH_DEBUG") != "1":
        return
    log_path = Path(tempfile.gettempdir()) / "claude-ah-ah-ah-hook.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except Exception as exc:  # pragma: no cover - stdin failures are environment-specific
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
    return value if isinstance(value, dict) else {"_json_value": value}


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _read_transcript_tail(path_value: Any) -> str:
    if not isinstance(path_value, str) or not path_value:
        return ""
    path = Path(path_value)
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > TRANSCRIPT_TAIL_BYTES:
                handle.seek(-TRANSCRIPT_TAIL_BYTES, os.SEEK_END)
            data = handle.read()
        return data.decode("utf-8", errors="replace")
    except OSError as exc:
        _debug(f"transcript read skipped: {exc}")
        return ""


def _patterns() -> list[str]:
    raw = os.environ.get("AH_AH_AH_PATTERNS")
    if not raw:
        return DEFAULT_TRIGGER_REGEXES
    return [item.strip() for item in raw.split(";;") if item.strip()]


def _matches(text: str) -> bool:
    if not text:
        return False
    for pattern in _patterns():
        try:
            if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                _debug(f"matched pattern: {pattern}")
                return True
        except re.error as exc:
            _debug(f"bad regex ignored: {pattern!r}: {exc}")
    return False


def _debounce_key(payload: dict[str, Any]) -> str:
    session_id = str(payload.get("session_id") or "no-session")
    message_id = str(payload.get("message_id") or payload.get("prompt_id") or "no-message")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{session_id}-{message_id}")[:180]
    return safe or "default"


def _debounced(payload: dict[str, Any]) -> bool:
    seconds = int(os.environ.get("AH_AH_AH_DEBOUNCE_SECONDS", DEFAULT_DEBOUNCE_SECONDS))
    if seconds <= 0:
        return False

    state_path = Path(tempfile.gettempdir()) / f"claude-ah-ah-ah-{_debounce_key(payload)}.last"
    now = time.time()
    try:
        previous = float(state_path.read_text(encoding="utf-8"))
        if now - previous < seconds:
            _debug("trigger suppressed by debounce")
            return True
    except (OSError, ValueError):
        pass

    try:
        state_path.write_text(str(now), encoding="utf-8")
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
    env["AH_AH_AH_POPUP_REASON"] = reason
    cmd = [_pythonw_executable(), str(Path(__file__).resolve()), "--popup-child"]
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def _show_popup() -> int:
    try:
        import tkinter as tk
    except Exception as exc:
        _debug(f"tkinter import failed: {exc}")
        return 0

    duration_ms = int(os.environ.get("AH_AH_AH_DURATION_MS", "9000"))
    frame_ms = int(os.environ.get("AH_AH_AH_FRAME_MS", "180"))

    explicit_frames = os.environ.get("AH_AH_AH_FRAMES")
    if explicit_frames:
        frame_paths = [Path(item) for item in explicit_frames.split(os.pathsep) if item]
    else:
        frame_paths = DEFAULT_FRAME_PATHS if all(path.exists() for path in DEFAULT_FRAME_PATHS) else []

    if not frame_paths:
        frame_paths = [Path(os.environ.get("AH_AH_AH_IMAGE", str(DEFAULT_IMAGE_PATH)))]

    root = tk.Tk()
    root.title("Access denied")
    root.configure(bg="#c0c0c0")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    width, height = 720, 650
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 4)
    root.geometry(f"{width}x{height}+{x}+{y}")

    outer = tk.Frame(root, bg="#c0c0c0", bd=3, relief="raised")
    outer.pack(fill="both", expand=True, padx=8, pady=8)

    titlebar = tk.Frame(outer, bg="#000080", height=30)
    titlebar.pack(fill="x")
    titlebar.pack_propagate(False)
    tk.Label(
        titlebar,
        text="System Message",
        bg="#000080",
        fg="#ffffff",
        font=("MS Sans Serif", 12, "bold"),
        anchor="w",
        padx=8,
    ).pack(side="left", fill="both", expand=True)
    tk.Label(
        titlebar,
        text="X",
        bg="#c0c0c0",
        fg="#000000",
        bd=2,
        relief="raised",
        width=3,
        font=("MS Sans Serif", 10, "bold"),
    ).pack(side="right", padx=4, pady=4)

    title = tk.Label(
        outer,
        text=POPUP_TEXT,
        bg="#c0c0c0",
        fg="#000000",
        font=("MS Sans Serif", 18, "bold"),
        wraplength=650,
        justify="center",
        pady=14,
    )
    title.pack(fill="x")

    image_box = tk.Frame(outer, bg="#808080", bd=2, relief="sunken")
    image_box.pack(padx=14, pady=4)
    canvas_width, canvas_height = 650, 420
    canvas = tk.Canvas(
        image_box,
        width=canvas_width,
        height=canvas_height,
        bg="#008080",
        highlightthickness=0,
    )
    canvas.pack()

    image_frames: list[Any] = []
    image_id: int | None = None
    try:
        try:
            from PIL import Image, ImageTk

            resampling = getattr(Image, "Resampling", Image).LANCZOS
            for path in frame_paths:
                with Image.open(path).convert("RGBA") as img:
                    img.thumbnail((canvas_width - 24, canvas_height - 18), resampling)
                    image_frames.append(ImageTk.PhotoImage(img.copy()))
        except Exception:
            for path in frame_paths:
                photo = tk.PhotoImage(file=str(path))
                divisor = max(
                    1,
                    int(max(photo.width() / (canvas_width - 24), photo.height() / (canvas_height - 18))),
                )
                if divisor > 1:
                    photo = photo.subsample(divisor, divisor)
                image_frames.append(photo)

        if image_frames:
            image_id = canvas.create_image(
                canvas_width // 2,
                canvas_height // 2,
                image=image_frames[0],
            )
    except Exception as exc:
        _debug(f"image load failed: {exc}")
        canvas.create_rectangle(80, 44, 570, 366, fill="#c0c0c0", outline="#404040", width=4)
        canvas.create_rectangle(90, 58, 560, 98, fill="#000080", outline="#ffffff", width=2)
        canvas.create_rectangle(125, 130, 525, 330, fill="#808080", outline="#ffffff", width=3)

    button = tk.Button(
        outer,
        text="OK",
        command=root.destroy,
        bg="#c0c0c0",
        fg="#000000",
        activebackground="#d8d8d8",
        activeforeground="#000000",
        relief="raised",
        bd=3,
        padx=36,
        pady=7,
        font=("MS Sans Serif", 11, "bold"),
    )
    button.pack(pady=14)

    state = {"index": 0}
    sequence = [0, 1, 2, 1] if len(image_frames) >= 3 else list(range(len(image_frames)))

    def animate() -> None:
        if image_id is not None and sequence:
            state["index"] = (state["index"] + 1) % len(sequence)
            canvas.itemconfig(image_id, image=image_frames[sequence[state["index"]]])
        root.after(frame_ms, animate)

    root.after(frame_ms, animate)
    root.after(duration_ms, root.destroy)
    root.lift()
    root.focus_force()
    try:
        root.bell()
    except Exception:
        pass
    root.mainloop()
    return 0


def _build_haystack(payload: dict[str, Any]) -> str:
    strings = list(_iter_strings(payload))
    transcript_tail = _read_transcript_tail(payload.get("transcript_path"))
    if transcript_tail:
        strings.append(transcript_tail)
    return "\n".join(strings)


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude Code reroute popup hook")
    parser.add_argument("--popup-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--test", action="store_true", help="show the popup without reading hook input")
    parser.add_argument("--probe", help="print MATCH or NO_MATCH for a text sample without showing the popup")
    parser.add_argument("--dry-run", action="store_true", help="read hook JSON and print MATCH or NO_MATCH without showing the popup")
    args = parser.parse_args()

    if args.popup_child:
        return _show_popup()
    if args.test:
        _launch_popup("manual test")
        return 0
    if args.probe is not None:
        print("MATCH" if _matches(args.probe) else "NO_MATCH")
        return 0

    raw = _read_stdin()
    payload = _loads_json(raw)
    haystack = _build_haystack(payload)
    matched = _matches(haystack)

    if args.dry_run:
        print("MATCH" if matched else "NO_MATCH")
        return 0

    if matched and not _debounced(payload):
        _launch_popup(str(payload.get("hook_event_name") or "hook"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
