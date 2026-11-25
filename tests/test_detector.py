"""Detector cues, window, and custom patterns."""

from __future__ import annotations

import pytest

README_SAMPLE = "llm research cuts you off and re routes you to opus 4.8"
SKILL_PROBE = "llm research cut you off and rerouted you to Opus 4.8"
SKILL_DELTA = "Rerouting your LLM research to Opus 4.8"


def _first_line(hook, text: str) -> str:
    report = hook.format_report(hook.find_match(text))
    return report.splitlines()[0]


@pytest.mark.parametrize(
    "text",
    [
        README_SAMPLE,
        SKILL_PROBE,
        SKILL_DELTA,
        "LLM research cutoff: please use Opus 4.8 instead",
        "LLM research cut-off. Continuing on opus-4.8",
        "Opus 4.8\nllm research cutoff",
        "reroute to opus 4.8 for llm research",
        "access denied: llm research has cut you off and is rerouting to opus 4.8",
        "opus 4 llm research reroute",
        "llm-research re-routes you to Opus 4",
        "LLM  research cutting you off from opus4.8",
        "the llm research team cuts off opus 4.1",
    ],
)
def test_documented_and_related_phrasing_matches(hook, text):
    assert _first_line(hook, text) == "MATCH"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello world",
        "Opus 4.8 is a model",
        "routing your request to Opus 4.5",
        "the router sent this to opus 4",
        "the route to opus 4 for llm research",
        "You were cut off. Continuing with Opus 4",
        "I will reroute you to opus 4",
        "cuts off opus 4",
        "llm research is fascinating and Opus 4.8 is fast",
        "cut-off and reroute to opus-4.8",
    ],
)
def test_unrelated_or_incomplete_phrasing_does_not_match(hook, text):
    assert _first_line(hook, text) == "NO_MATCH"


def test_span_is_the_distance_between_the_outer_cues(hook):
    text = "opus 4 llm research reroute"
    match = hook.find_match(text)
    assert match is not None
    assert match.custom is False
    # "opus 4" starts this sentence and "reroute" starts 20 characters later.
    assert text.index("reroute") - text.index("opus 4") == 20
    assert match.summary == '"llm research" + "reroute" + "opus 4" within 20 characters'


def test_cues_farther_apart_than_the_window_do_not_match(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_WINDOW", "40")
    text = "llm research cutoff " + ("x" * 80) + " opus 4.8"
    assert hook.find_match(text) is None


def test_default_window_still_reaches_across_two_old_hops(hook):
    text = "llm research " + ("x" * 200) + " reroute " + ("x" * 200) + " opus 4"
    assert hook.find_match(text) is not None


def test_custom_patterns_replace_the_cue_search(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_PATTERNS", r"not[a;;\bzigzag\b")
    assert hook.find_match("please zigzag now") is not None
    assert hook.find_match("llm research cuts you off and re routes you to opus 4.8") is None


def test_invalid_custom_regex_is_ignored(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_PATTERNS", r"(unclosed")
    assert hook.find_match("llm research cutoff opus 4") is None


def test_empty_custom_pattern_list_matches_nothing(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_PATTERNS", "   ;;  ")
    assert hook.find_match(README_SAMPLE) is None


def test_report_keeps_a_stable_first_line(hook):
    match = hook.format_report(hook.find_match(README_SAMPLE))
    miss = hook.format_report(hook.find_match("hello"))
    assert match.splitlines()[0] == "MATCH"
    assert "within" in match.splitlines()[1]
    assert miss == "NO_MATCH\nno llm-research cutoff or reroute near Opus 4"
