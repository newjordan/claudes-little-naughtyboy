# claudes little naughtyboy

Claude Code hook that watches for an LLM-research cutoff or reroute onto Opus 4 and opens a 1990s-style lockout popup.

The popup text is exactly `ah ah ah, your not allowed to do that`. The hook does not block the turn, rewrite the message, or stop the reroute. It is a local side effect.

Demo recording published with the repository:

https://github.com/user-attachments/assets/e4cf376c-fb89-48cb-bdc2-bd35248d17df

## Requirements

- Python 3.10 or newer. The hook itself uses the standard library.
- Claude Code, so `.claude/settings.json` is loaded as a project hook.
- Tkinter, to show the popup. On Debian or Ubuntu that is the `python3-tk` package. Without Tkinter the detector still runs, and `--test` exits 1 with an install hint.
- Pillow is optional. When it is installed the popup scales the animation frames. Without it, Tkinter's PNG loader is used, and if that also fails the dialog draws a placeholder.

No model weights are downloaded. The hook does not make network calls.

## Setup

Clone this repository and open it in Claude Code. The hook is already wired in `.claude/settings.json` for `MessageDisplay`, `Notification`, `Stop`, and `StopFailure`.

Claude Code holds project hooks until the workspace trust dialog is accepted in an interactive session. A `claude -p` or SDK session treats the folder as trusted and runs the hook without that dialog. Review `.claude/settings.json` before you point an unattended session at a checkout you did not write.

The committed command runs under bash (Claude Code's default, including Windows when Git Bash is installed). It tries `python3`, then `python`, then `py -3`, and it uses `${CLAUDE_PROJECT_DIR}` so the script is found even when the working directory is not the repo root. The hook is `async`, so showing the popup does not hold up message display.

On Windows without Git Bash, Claude Code runs hooks in PowerShell and the bash command will not run. Replace each hook's `shell` and `command` with:

```json
"shell": "powershell",
"command": "$script = Join-Path $env:CLAUDE_PROJECT_DIR '.claude\\hooks\\ah_ah_ah_popup.py'; if (Get-Command python -ErrorAction SilentlyContinue) { python $script } elseif (Get-Command py -ErrorAction SilentlyContinue) { py -3 $script }"
```

Restart Claude Code after changing the settings.

## Usage

From the repository root:

```bash
python3 .claude/hooks/ah_ah_ah_popup.py --probe "llm research cuts you off and re routes you to opus 4.8"
```

That command prints:

```text
MATCH
"llm research" + "cuts you off" + "opus 4.8" within 47 characters
```

`--probe` and `--dry-run` print `MATCH` or `NO_MATCH` as the first line. The process exits 0 on a match and 1 when there is no match. The second line is a short explanation. Neither command opens the popup, and `--dry-run` does not update the session buffer.

```bash
echo '{"hook_event_name":"MessageDisplay","delta":"Rerouting your LLM research to Opus 4.8"}' | python3 .claude/hooks/ah_ah_ah_popup.py --dry-run
```

```text
MATCH
"LLM research" + "Rerouting" + "Opus 4.8" within 31 characters
```

Show the dialog in the current terminal:

```bash
python3 .claude/hooks/ah_ah_ah_popup.py --test
```

Close it with the title-bar X, the OK button, Enter, or Escape. With no arguments, a terminal prints help and exits 2 instead of waiting on stdin. A real hook is not a terminal. An empty pipe is a quiet miss and exits 0.

During a hook event the script prints nothing and exits 0, including when it launches the popup. `Stop` would treat stdout as a decision, so the hook stays silent.

## Detection

A match needs all three cues inside a window of 520 characters, in any order:

- `llm research` or `llm-research`
- a cutoff (`cutoff`, `cut-off`, `cut off`, `cuts you off`, `cutting you off`, and the same forms without `you`) or a reroute (`reroute`, `re-route`, `re route`, including `rerouted`, `rerouting`, and `reroutes`)
- `Opus 4`, including `Opus 4.8`, `opus-4.8`, and `opus4.8`

`route`, `router`, and `routing` do not count. A cutoff or a reroute that never mentions LLM research does not count. Mentioning Opus 4.8 next to "llm research" without a cutoff or a reroute does not count.

The hook searches three texts separately:

- the strings on this event, except `transcript_path` and `cwd`
- the last 160000 bytes of `transcript_path`, with the current event text appended
- a per-session buffer of recent hook text, so a sentence split across `MessageDisplay` batches still matches

`MessageDisplay` can deliver the reply in several batches, and the transcript file can lag the live text. The buffer is what joins those batches. `--dry-run` checks one payload only.

The same cues in the same session are suppressed for 30 seconds. A different reroute in that session is not. `Stop` often has no `message_id`, so the key is the session id plus the cue text, not the message id.

## Popup

The dialog is a borderless, topmost window with gray and blue 1990s chrome. It takes a Tk keyboard grab until it closes, so Enter and Escape reach the dialog. It stays up for 9000 ms unless you close it first. Set `AH_AH_AH_DURATION_MS=0` to wait until it is closed. A system bell plays once. `AH_AH_AH_BELL=0` skips the bell.

Three frames wag in the order 1, 2, 3, 2. The frames are:

| File | Size |
| --- | --- |
| `dario-lockout-frame-1.png` | 719×724 |
| `dario-lockout-frame-2.png` | 714×724 |
| `dario-lockout-frame-3.png` | 719×724 |

`dario-lockout.png` is a byte-for-byte copy of frame 2 and is used only when one of those three files is missing. `dario-lockout-spritesheet.png` is 2172×724 and is the source strip. The popup does not load it. None of the PNGs contain text or EXIF chunks.

A status line names the hook event, or says `Manual test` for `--test`. The picture's own title-bar X is part of the artwork. The X on the outer dialog is the control that closes the window.

## Configuration

Environment variables read by the script:

| Variable | Default | Effect |
| --- | --- | --- |
| `AH_AH_AH_PATTERNS` | unset | Regexes separated by `;;`. When set, they replace the three-cue search. A bad regex is ignored. |
| `AH_AH_AH_WINDOW` | `520` | Maximum character distance from the earliest cue in a hit to the latest. |
| `AH_AH_AH_DEBOUNCE_SECONDS` | `30` | How long a repeat of the same cues stays quiet. `0` or a negative value disables it. |
| `AH_AH_AH_DURATION_MS` | `9000` | Popup lifetime. `0` waits for the user. A negative or non-integer value uses the default. |
| `AH_AH_AH_FRAME_MS` | `180` | Delay between animation frames. `0` shows the first frame only. |
| `AH_AH_AH_BUFFER_CHARS` | `4000` | Recent hook text kept for the session. `0` disables the buffer. |
| `AH_AH_AH_BELL` | `1` | `0`, `false`, `no`, or `off` skips the bell. |
| `AH_AH_AH_FRAMES` | the three frame files | Extra frame paths, separated by the OS path separator. |
| `AH_AH_AH_IMAGE` | `dario-lockout.png` | Fallback image when the three default frames are not all present. |
| `AH_AH_AH_STATE_DIR` | system temp directory | Buffer, debounce files, and the debug log. |
| `AH_AH_AH_DEBUG` | unset | `1` appends a short log in the state directory. The log does not include the transcript. |

A non-integer in a numeric variable falls back to that variable's default instead of crashing the hook.

State files are written mode `0600`. The buffer can contain recent hook text, so it can contain a snippet of the conversation. It stays on the local machine.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest
```

The `dev` extra installs pytest, ruff, and Pillow. Pillow 13 requires Python 3.11 or newer; pip selects an older Pillow on Python 3.10. The `images` extra installs Pillow alone.

GitHub Actions (`.github/workflows/ci.yml`) runs the same ruff checks and pytest on Python 3.10, 3.11, 3.12, and 3.13.

The manual test and tuning notes for the hook live in `.claude/skills/ah-ah-ah-lockout/SKILL.md`.

## License

This repository does not include a license file.
