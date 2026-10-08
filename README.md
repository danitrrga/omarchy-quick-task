# Quick Task

Quick Task is a resident Omarchy overlay for capturing Todoist tasks without leaving the current workspace. It replaces the old terminal popup with a native Quickshell surface that inherits the live Omarchy font, colors, spacing, and corner radius.

Press `Super + Shift + ;`, type, and press `Enter`. `Esc` closes the overlay, `Down` opens the description field, and `Shift + Down` shows the inline syntax guide.

## Recognition

English and Spanish date shorthand work in the same sentence, independent of the Todoist account language:

```text
Send revised deck mon 9am #Work p1
Entregar propuesta lun #Trabajo
Preparar la demo este viernes a las 9
Renew passport 21st
Llamar a Marta el 21 #Personal
```

Recognized dates are previewed before submission. Select a date chip to keep that phrase as literal task text for the current draft.

The recognized span is also marked directly inside the task field. Only the last value of each detail type is active; earlier dates, projects, labels, priorities, assignees, reminders, sections, and deadlines remain literal text. With the cursor immediately after a marked span, press `Backspace` once to make every current value of that type literal without deleting visible text. A second `Backspace` edits normally.

Todoist’s remaining Quick Add syntax passes through unchanged:

| Detail | Syntax |
| --- | --- |
| Project | `#Work` |
| Section | `/Admin` after a project |
| Label | `%email` or legacy `@email` |
| Priority | `p1`–`p4` |
| Assignee | `+Name` after a shared project |
| Reminder | `!30 min before` |
| Deadline | `{Sep 30}` |

## Install

```bash
./deploy.sh
```

Deployment is idempotent. It installs the Python helper under `~/.local`, installs and enables the `danitrrga.quick-task` Omarchy plugin, replaces the legacy terminal binding, removes the obsolete terminal window rule, tightens `~/.config/tod.cfg` to mode `0600`, and reloads the shell integration.

The first config mutation creates these rollback copies and never overwrites them:

```text
~/.config/hypr/bindings.lua.quick-task.bak
~/.config/hypr/hyprland.lua.quick-task.bak
```

The legacy `tod-quickadd` files are left in place but become unused, so rollback is only a binding restore away.

## Architecture

- `src/quick_task/parser.py` performs deterministic bilingual date normalization locally.
- `src/quick_task/todoist.py` calls Todoist’s current JSON Quick Add endpoint.
- `src/quick_task/cli.py` exposes a newline-delimited JSON protocol over stdin and stdout.
- `packaging/omarchy/plugins/danitrrga.quick-task/QuickTask.qml` is the keep-loaded native overlay.
- `deploy.sh` performs backup-first installation and migration.

The Todoist token is read from `TODOIST_API_TOKEN` or the existing `~/.config/tod.cfg`. It is never placed in process arguments, QML, logs, or returned errors.

## Verify

```bash
uv venv --python 3.14
uv pip install pytest
.venv/bin/pytest -q
QML_IMPORT_PATH=/usr/share/omarchy/shell qmllint \
  packaging/omarchy/plugins/danitrrga.quick-task/QuickTask.qml
bash -n deploy.sh
```

The suite covers bilingual parsing, last-value precedence, literal syntax protection, the Todoist request contract, secret redaction, QML keyboard behavior, live theme tokens, theme-owned corner geometry, and run-twice installer safety.

The product contract and implementation rationale live in [docs/spec.md](docs/spec.md).
