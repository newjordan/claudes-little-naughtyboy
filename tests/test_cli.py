"""Command-line probe, dry-run, and no-argument behavior."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "ah_ah_ah_popup.py"


def clean_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("AH_AH_AH_"):
            env.pop(name)
    env["AH_AH_AH_BELL"] = "0"
    return env


SAMPLE = "llm research cuts you off and re routes you to opus 4.8"


def test_probe_match_and_miss_exit_codes(hook, capsys):
    assert hook.main(["--probe", SAMPLE]) == 0
    matched = capsys.readouterr().out
    assert matched.splitlines()[0] == "MATCH"
    assert hook.main(["--probe", "routing your request to Opus 4.5"]) == 1
    missed = capsys.readouterr().out
    assert missed.splitlines()[0] == "NO_MATCH"


def test_probe_runs_as_a_script():
    matched = subprocess.run(
        [sys.executable, str(SCRIPT), "--probe", SAMPLE],
        check=False,
        capture_output=True,
        text=True,
        env=clean_subprocess_env(),
    )
    missed = subprocess.run(
        [sys.executable, str(SCRIPT), "--probe", "routing your request to Opus 4.5"],
        check=False,
        capture_output=True,
        text=True,
        env=clean_subprocess_env(),
    )
    assert matched.returncode == 0
    assert matched.stdout.splitlines()[0] == "MATCH"
    assert missed.returncode == 1
    assert missed.stdout.splitlines()[0] == "NO_MATCH"


def test_dry_run_reads_hook_json(hook, monkeypatch, capsys):
    raw = json.dumps({"hook_event_name": "MessageDisplay", "delta": SAMPLE})
    monkeypatch.setattr(hook, "_read_stdin", lambda: raw)
    monkeypatch.setattr(hook, "_stdin_is_tty", lambda: False)
    assert hook.main(["--dry-run"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "MATCH"


def test_dry_run_of_plain_text_that_is_not_json(hook, monkeypatch, capsys):
    monkeypatch.setattr(hook, "_read_stdin", lambda: SAMPLE)
    monkeypatch.setattr(hook, "_stdin_is_tty", lambda: False)
    assert hook.main(["--dry-run"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "MATCH"


def test_no_arguments_on_a_terminal_prints_help_instead_of_blocking(hook, monkeypatch, capsys):
    monkeypatch.setattr(hook.sys.stdin, "isatty", lambda: True)
    assert hook.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--probe" in captured.err


def test_empty_pipe_is_a_quiet_miss(hook, monkeypatch, capsys):
    monkeypatch.setattr(hook, "_stdin_is_tty", lambda: False)
    monkeypatch.setattr(hook, "_read_stdin", lambda: "")
    launched: list[str] = []
    monkeypatch.setattr(hook, "_launch_popup", lambda reason="": launched.append(reason))
    assert hook.main([]) == 0
    assert launched == []
    assert capsys.readouterr().out == ""


def test_env_integers_that_are_blank_or_garbage_use_defaults(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_DURATION_MS", "   ")
    monkeypatch.setenv("AH_AH_AH_FRAME_MS", "fast")
    monkeypatch.setenv("AH_AH_AH_WINDOW", "wide")
    assert hook._duration_ms() == hook.DEFAULT_DURATION_MS
    assert hook._frame_ms() == hook.DEFAULT_FRAME_MS
    assert hook._window_chars() == hook.DEFAULT_WINDOW_CHARS


def test_zero_duration_waits_for_the_user_and_negative_uses_the_default(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_DURATION_MS", "0")
    assert hook._duration_ms() == 0
    monkeypatch.setenv("AH_AH_AH_DURATION_MS", "-5")
    assert hook._duration_ms() == hook.DEFAULT_DURATION_MS
