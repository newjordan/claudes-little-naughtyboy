"""Stdin payloads, transcript tail, session buffer, and debounce."""

from __future__ import annotations

import json

SAMPLE = "llm research cuts you off and re routes you to opus 4.8"


def test_split_message_batches_match_only_after_they_are_remembered(hook, tmp_path):
    first = {
        "session_id": "session-1",
        "hook_event_name": "MessageDisplay",
        "message_id": "m1",
        "delta": "llm research cuts you off and",
    }
    second = {
        "session_id": "session-1",
        "hook_event_name": "MessageDisplay",
        "message_id": "m1",
        "delta": "re routes you to opus 4.8",
    }
    assert hook.find_payload_match(first, remember=False) is None
    assert hook.find_payload_match(second, remember=False) is None
    assert hook.find_payload_match(first, remember=True) is None
    remembered = hook.find_payload_match(second, remember=True)
    assert remembered is not None
    buffers = list((tmp_path / "state").glob("*.buf"))
    assert len(buffers) == 1


def test_dry_run_remember_flag_does_not_write_state(hook, tmp_path):
    payload = {"session_id": "session-1", "delta": SAMPLE}
    assert hook.find_payload_match(payload, remember=False) is not None
    state = tmp_path / "state"
    assert not state.exists() or not any(state.iterdir())


def test_repeating_the_same_live_text_does_not_grow_the_buffer(hook, tmp_path):
    payload = {"session_id": "session-1", "delta": SAMPLE}
    hook.find_payload_match(payload, remember=True)
    buffer = next((tmp_path / "state").glob("*.buf"))
    first = buffer.read_text(encoding="utf-8")
    hook.find_payload_match(payload, remember=True)
    assert buffer.read_text(encoding="utf-8") == first
    assert first.count(SAMPLE) == 1


def test_transcript_tail_is_scanned_and_the_head_is_not(hook, tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    # Newlines, not word characters: a run of letters would glue onto "llm" and
    # remove the word boundary the detector requires.
    filler = b"\n" * (hook.TRANSCRIPT_TAIL_BYTES + 50)
    transcript.write_bytes(b"llm research cutoff opus 4\n" + filler + SAMPLE.encode())
    payload = {"session_id": "s", "delta": "working", "transcript_path": str(transcript)}
    assert hook.find_payload_match(payload, remember=False) is not None

    hidden = tmp_path / "hidden.jsonl"
    hidden.write_bytes(SAMPLE.encode() + b"\n" + filler)
    missed = {"session_id": "s", "delta": "working", "transcript_path": str(hidden)}
    assert hook.find_payload_match(missed, remember=False) is None


def test_missing_transcript_is_not_an_error(hook, tmp_path):
    payload = {
        "session_id": "s",
        "delta": "hello",
        "transcript_path": str(tmp_path / "missing.jsonl"),
    }
    assert hook.find_payload_match(payload, remember=False) is None


def test_invalid_json_still_scans_the_raw_text(hook):
    payload = hook._loads_json(SAMPLE)
    assert payload["_raw_stdin"] == SAMPLE
    assert hook.find_payload_match(payload, remember=False) is not None


def test_non_object_json_is_scanned(hook):
    payload = hook._loads_json(json.dumps(["reroute to opus 4.8 for llm research"]))
    assert hook.find_payload_match(payload, remember=False) is not None


def test_transcript_path_string_is_not_treated_as_message_text(hook, tmp_path):
    tricky = tmp_path / "llm research cutoff opus 4.txt"
    tricky.write_text("notes", encoding="utf-8")
    payload = {"session_id": "s", "delta": "hello", "transcript_path": str(tricky)}
    assert hook.find_payload_match(payload, remember=False) is None


def test_invalid_debounce_env_falls_back_and_still_suppresses(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_DEBOUNCE_SECONDS", "nope")
    monkeypatch.setattr(hook.time, "time", lambda: 1_000.0)
    payload = {"session_id": "s", "delta": SAMPLE}
    match = hook.find_payload_match(payload, remember=False)
    assert match is not None
    assert hook.should_suppress(payload, match) is False
    assert hook.should_suppress(payload, match) is True


def test_debounce_expires_and_does_not_share_keys(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_DEBOUNCE_SECONDS", "30")
    now = {"value": 5_000.0}
    monkeypatch.setattr(hook.time, "time", lambda: now["value"])
    first = hook.find_match("llm research cutoff opus 4")
    second = hook.find_match("llm research reroute opus 4.8")
    assert first is not None and second is not None
    assert first.fingerprint != second.fingerprint
    payload = {"session_id": "alpha"}
    other_session = {"session_id": "beta"}
    assert hook.should_suppress(payload, first) is False
    assert hook.should_suppress(payload, first) is True
    assert hook.should_suppress(payload, second) is False
    assert hook.should_suppress(other_session, first) is False
    now["value"] = 5_031.0
    assert hook.should_suppress(payload, first) is False


def test_zero_debounce_disables_suppression(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_DEBOUNCE_SECONDS", "0")
    payload = {"session_id": "s"}
    match = hook.find_match(SAMPLE)
    assert match is not None
    assert hook.should_suppress(payload, match) is False
    assert hook.should_suppress(payload, match) is False


def test_negative_debounce_disables_suppression(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_DEBOUNCE_SECONDS", "-4")
    match = hook.find_match(SAMPLE)
    assert match is not None
    assert hook.should_suppress({"session_id": "s"}, match) is False


def test_hook_mode_is_silent_and_launches_once(hook, monkeypatch, capsys):
    launched: list[str] = []
    monkeypatch.setattr(hook, "_launch_popup", lambda reason="": launched.append(reason))
    monkeypatch.setattr(hook, "_stdin_is_tty", lambda: False)
    raw = json.dumps(
        {
            "session_id": "s",
            "hook_event_name": "MessageDisplay",
            "delta": SAMPLE,
        }
    )
    monkeypatch.setattr(hook, "_read_stdin", lambda: raw)
    assert hook.main([]) == 0
    assert launched == ["MessageDisplay"]
    assert capsys.readouterr().out == ""
    assert hook.main([]) == 0
    assert launched == ["MessageDisplay"]


def test_stop_without_message_id_does_not_swallow_a_different_alert(hook, monkeypatch):
    launched: list[str] = []
    monkeypatch.setattr(hook, "_launch_popup", lambda reason="": launched.append(reason))
    monkeypatch.setattr(hook, "_stdin_is_tty", lambda: False)
    payloads = [
        {"session_id": "s", "hook_event_name": "Stop", "last_assistant_message": SAMPLE},
        {
            "session_id": "s",
            "hook_event_name": "Stop",
            "last_assistant_message": "llm research rerouted this to Opus 4.1",
        },
    ]

    def feed(payload: dict) -> None:
        monkeypatch.setattr(hook, "_read_stdin", lambda: json.dumps(payload))
        assert hook.main([]) == 0

    feed(payloads[0])
    feed(payloads[1])
    assert launched == ["Stop", "Stop"]


def test_session_id_is_sanitized_for_state_files(hook, tmp_path):
    payload = {"session_id": "a/b c", "delta": SAMPLE}
    match = hook.find_payload_match(payload, remember=True)
    assert match is not None
    hook.should_suppress(payload, match)
    names = sorted(path.name for path in (tmp_path / "state").iterdir())
    assert names
    assert all("/" not in name and " " not in name for name in names)
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in (tmp_path / "state").iterdir())
