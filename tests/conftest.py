"""Load the hook script and keep each test's state files isolated."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "hooks" / "ah_ah_ah_popup.py"

_HOOK_ENV = (
    "AH_AH_AH_PATTERNS",
    "AH_AH_AH_DEBOUNCE_SECONDS",
    "AH_AH_AH_DURATION_MS",
    "AH_AH_AH_FRAME_MS",
    "AH_AH_AH_WINDOW",
    "AH_AH_AH_BUFFER_CHARS",
    "AH_AH_AH_FRAMES",
    "AH_AH_AH_IMAGE",
    "AH_AH_AH_POPUP_REASON",
    "AH_AH_AH_BELL",
    "AH_AH_AH_DEBUG",
    "AH_AH_AH_STATE_DIR",
)


def load_hook():
    spec = importlib.util.spec_from_file_location("ah_ah_ah_popup", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    # dataclass(slots=True) looks the defining module up in sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def hook():
    return load_hook()


@pytest.fixture(autouse=True)
def isolated_hook_env(monkeypatch, tmp_path):
    for name in _HOOK_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AH_AH_AH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AH_AH_AH_BELL", "0")
