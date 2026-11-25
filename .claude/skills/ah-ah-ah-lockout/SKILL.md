---
name: ah-ah-ah-lockout
description: Test, tune, or explain this project's Claude Code hook that detects LLM research cutoff/reroute messages mentioning Opus and opens the "ah ah ah, your not allowed to do that" Dario lockout popup.
argument-hint: "[test|probe|tune]"
disable-model-invocation: true
---

# Ah Ah Ah Lockout

Use this skill to maintain the project-local lockout gag.

## Files

- Hook config: `.claude/settings.json`
- Detector and popup: `.claude/hooks/ah_ah_ah_popup.py`
- Popup frames: `.claude/hooks/assets/dario-lockout-frame-1.png`, `dario-lockout-frame-2.png`, `dario-lockout-frame-3.png`
- Fallback PNG: `.claude/hooks/assets/dario-lockout.png` (same bytes as frame 2)
- Source strip, not loaded at runtime: `.claude/hooks/assets/dario-lockout-spritesheet.png`
- Tests: `tests/`

## Key behavior

- The always-on detector is a Claude Code hook. This skill is for manual testing and maintenance.
- The hook listens to `MessageDisplay`, `Notification`, `Stop`, and `StopFailure`.
- A match needs all three cues inside the window (default 520 characters), in any order:
  - `llm research` or `llm-research`
  - a cutoff (`cutoff`, `cut-off`, `cut off`, `cuts you off`, `cutting you off`) or a reroute (`reroute`, `re-route`, `re route`, and the same words with `d`, `s`, or `ing`)
  - `Opus 4`, including `Opus 4.8`, `opus-4.8`, and `opus4.8`
- Plain words such as `route`, `router`, and `routing` do not count.
- The hook scans the event JSON, the last 160000 bytes of `transcript_path`, and a per-session buffer of recent hook text so a phrase split across `MessageDisplay` batches still matches.
- On a match it opens a borderless topmost Tk dialog. The exact message is `ah ah ah, your not allowed to do that`. The title-bar X, OK, Enter, and Escape all close it. Three frames wag in a `1, 2, 3, 2` loop.
- The same cues in the same session are suppressed for 30 seconds. A different reroute in that session is not suppressed. `Stop` often has no `message_id`; the key is the session plus the cue text.
- Hook mode prints nothing and exits 0. `--probe` and `--dry-run` print `MATCH` or `NO_MATCH` as the first line and exit 1 on `NO_MATCH`.

## Commands

Probe a sample without opening the popup:

```bash
python3 .claude/hooks/ah_ah_ah_popup.py --probe "llm research cut you off and rerouted you to Opus 4.8"
```

Dry-run one hook payload. This does not update the session buffer:

```bash
echo '{"hook_event_name":"MessageDisplay","delta":"Rerouting your LLM research to Opus 4.8"}' | python3 .claude/hooks/ah_ah_ah_popup.py --dry-run
```

Show the popup in the current terminal:

```bash
python3 .claude/hooks/ah_ah_ah_popup.py --test
```

With no arguments, a terminal session prints help instead of waiting on stdin. A real hook event is not a terminal, and an empty pipe is a quiet miss.

## Tuning

- `AH_AH_AH_PATTERNS`: regexes separated by `;;`. When this is set, it replaces the three-cue search. A bad regex is ignored.
- `AH_AH_AH_WINDOW`: maximum character distance from the first cue in a hit to the last. Default `520`.
- `AH_AH_AH_DEBOUNCE_SECONDS`: repeat suppression. `0` or a negative value disables it. A non-integer uses the default.
- `AH_AH_AH_DURATION_MS`: popup lifetime. `0` waits until the user closes it. A negative or non-integer value uses `9000`.
- `AH_AH_AH_FRAME_MS`: animation delay. `0` shows the first frame only.
- `AH_AH_AH_BUFFER_CHARS`: recent hook text kept per session. `0` disables the buffer. Default `4000`.
- `AH_AH_AH_BELL`: `0` skips the system bell.
- `AH_AH_AH_FRAMES`: `os.pathsep`-separated frame paths.
- `AH_AH_AH_IMAGE`: fallback image used when the three default frames are not all present.
- `AH_AH_AH_STATE_DIR`: directory for the buffer, debounce files, and debug log. Default is the system temp directory. Those files are written mode `0600`. The buffer can hold recent hook text.
- `AH_AH_AH_DEBUG=1`: append a short log under the state directory. The log does not include the transcript.
