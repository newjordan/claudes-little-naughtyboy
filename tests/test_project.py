"""Project wiring, artwork, and a scan for committed credentials."""

from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / ".claude" / "hooks" / "assets"
SETTINGS = ROOT / ".claude" / "settings.json"

# Measured from the PNG IHDR chunks in this repository.
FRAME_SIZES = {
    "dario-lockout-frame-1.png": (719, 724),
    "dario-lockout-frame-2.png": (714, 724),
    "dario-lockout-frame-3.png": (719, 724),
    "dario-lockout.png": (714, 724),
    "dario-lockout-spritesheet.png": (2172, 724),
}

# Strict shapes only. Short fragments such as "sk-" occur inside the PNG bytes.
CREDENTIAL_RES = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(rb"sk-[A-Za-z0-9]{20,}"),
)


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def _metadata_chunks(path: Path) -> list[bytes]:
    data = path.read_bytes()
    index = 8
    found: list[bytes] = []
    while index + 8 <= len(data):
        length = struct.unpack(">I", data[index : index + 4])[0]
        chunk_type = data[index + 4 : index + 8]
        if chunk_type in {b"tEXt", b"iTXt", b"zTXt", b"eXIf"}:
            found.append(chunk_type)
        index += 12 + length
        if chunk_type == b"IEND":
            break
    return found


def test_animation_assets_have_the_measured_dimensions_and_no_text_metadata():
    for name, size in FRAME_SIZES.items():
        path = ASSETS / name
        assert _png_size(path) == size
        assert _metadata_chunks(path) == []


def test_fallback_image_is_the_same_bytes_as_frame_two():
    frame = (ASSETS / "dario-lockout-frame-2.png").read_bytes()
    fallback = (ASSETS / "dario-lockout.png").read_bytes()
    assert hashlib.sha256(frame).digest() == hashlib.sha256(fallback).digest()


def test_hook_settings_run_the_script_on_bash_for_every_watched_event():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    hooks = settings["hooks"]
    assert set(hooks) == {"MessageDisplay", "Notification", "Stop", "StopFailure"}
    commands = []
    for event, groups in hooks.items():
        assert "matcher" not in groups[0], event
        command = groups[0]["hooks"][0]
        assert command["type"] == "command"
        assert command["shell"] == "bash"
        assert command["async"] is True
        assert command["timeout"] == 10
        assert "ah_ah_ah_popup.py" in command["command"]
        assert "python3" in command["command"]
        assert "powershell" not in command["command"].lower()
        commands.append(command["command"])
    assert len(set(commands)) == 1


def test_tracked_project_files_do_not_contain_credential_markers():
    skipped = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or skipped.intersection(path.parts):
            continue
        data = path.read_bytes()
        for pattern in CREDENTIAL_RES:
            if pattern.search(data):
                offenders.append(f"{pattern.pattern.decode()}: {path.relative_to(ROOT)}")
    assert offenders == []
