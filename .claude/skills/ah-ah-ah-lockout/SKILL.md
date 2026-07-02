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
- Detector/popup script: `.claude/hooks/ah_ah_ah_popup.py`
- Popup frame PNGs: `.claude/hooks/assets/dario-lockout-frame-1.png`, `dario-lockout-frame-2.png`, `dario-lockout-frame-3.png`
- Fallback PNG: `.claude/hooks/assets/dario-lockout.png`

## Key behavior

- The always-on detector is a Claude Code hook, not the skill body. The skill exists for manual testing and maintenance.
- The hook listens to `MessageDisplay`, `Notification`, `Stop`, and `StopFailure`.
- The detector scans hook JSON text plus the transcript tail for LLM research cutoff/reroute wording near `Opus 4`, including `Opus 4.8`.
- On match, it launches a topmost Tk popup with the exact text `ah ah ah, your not allowed to do that`.
- The popup uses old 1990s OS-style gray/blue chrome and cycles the three Dario lockout frames in a `1,2,3,2` wagging loop.
- It debounces repeated triggers for the same session/message for 30 seconds.

## Commands

Probe a sample without opening the popup:

```bash
python .claude/hooks/ah_ah_ah_popup.py --probe "llm research cut you off and rerouted you to Opus 4.8"
```

Dry-run a hook payload:

```bash
echo '{"hook_event_name":"MessageDisplay","delta":"Rerouting your LLM research to Opus 4.8"}' | python .claude/hooks/ah_ah_ah_popup.py --dry-run
```

Show the popup manually:

```bash
python .claude/hooks/ah_ah_ah_popup.py --test
```

## Tuning

- To add temporary patterns without editing the script, set `AH_AH_AH_PATTERNS` to regexes separated by `;;`.
- To change debounce, set `AH_AH_AH_DEBOUNCE_SECONDS`.
- To change popup duration, set `AH_AH_AH_DURATION_MS`.
- To change animation speed, set `AH_AH_AH_FRAME_MS`.
- To use custom frames, replace `.claude/hooks/assets/dario-lockout-frame-1.png` through `dario-lockout-frame-3.png` with the same filenames.
