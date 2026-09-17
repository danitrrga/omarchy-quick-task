# Quick Task Quattro specification

## Outcome

Quick Task is a resident Omarchy overlay for sending a fully structured task to Todoist from anywhere on the desktop. It must appear immediately from the existing `Super + Shift + ;` binding, accept English and Spanish in the same field, make its interpretation visible before submission, and disappear after a successful add.

## Interaction contract

1. The global binding summons a keep-loaded `danitrrga.quick-task` Omarchy overlay.
2. Focus starts in the task field. `Enter` adds, `Esc` closes, `Down` reveals and focuses the description field, and `Shift + Down` reveals the syntax reference.
3. Recognition runs after a short typing debounce. It never blocks input or contacts Todoist.
4. Recognized details appear as compact chips below the sentence. Selecting a date chip makes that phrase literal for the current draft; editing the sentence clears stale suppressions.
5. During submission, the draft stays visible and the add action shows activity without changing size.
6. Success dismisses the overlay and sends native Omarchy feedback. Failure keeps the full draft and shows a specific retryable error.

## Recognition contract

Recognition is deliberately split in two:

- A deterministic local normalizer handles bilingual date shorthand and produces live preview data.
- Todoist’s Quick Add endpoint remains the authority for projects, sections, labels, priorities, assignees, reminders, deadlines, recurrence, and the final created task.

The normalizer supports English and Spanish simultaneously, regardless of the Todoist account language:

- Weekdays and common abbreviations: `monday`, `mon`, `lunes`, `lun`, and equivalents for all seven days.
- Relative dates: `today`, `tod`, `tomorrow`, `tom`, `tmrw`, `hoy`, `mañana`, `pasado mañana`.
- Qualified weekdays: `this Friday`, `este viernes`, `next Tuesday`, `el próximo martes`.
- Days of month: `21st`, `21º`, `el 21`. A day that has already passed resolves to the next month so quick capture does not silently create an overdue task.
- Times adjacent to dates remain part of the normalized sentence; Spanish `a las 9` is normalized to `at 09:00`.

Recognized date phrases are replaced with an absolute `YYYY-MM-DD` string before submission. This removes account-language ambiguity while preserving Todoist’s parser for the rest of the sentence.

Todoist metadata owns its full recognized span. A date-like label such as `@tomorrow`, project such as `#viernes`, assignee such as `+monday`, or deadline such as `{due friday}` is therefore previewed only as that metadata and never simultaneously as a due date.

The overlay also previews Todoist syntax for `#project`, `/section`, `%label` and legacy `@label`, `p1`–`p4`, `+assignee`, `!reminder`, and `{deadline}`. The description is sent through the API’s `note` field.

## Current Todoist parity

The shipping scope recreates the desktop Quick Add path: global invocation, date/time recognition, project, section, labels, priority, assignee, reminder, deadline, description, keyboard dismissal, and a visible way to disregard a recognized date. Todoist’s newer Ramble voice mode, AI extraction from files/images, attachments, and location reminders are separate capture modes and are not part of this fast text overlay.

Todoist’s current help describes the Quick Add feature and syntax at <https://www.todoist.com/help/todoist/features/use-task-quick-add-in-todoist-va4Lhpzz>. The current API contract is `POST /api/v1/tasks/quick` with JSON, `meta: true`, and the task text in `text`: <https://developer.todoist.com/api/v1/#tag/Tasks/operation/quick-add-task>.

## Visual contract

The chosen direction combines the restrained dark surface with the instrument panel’s explicit state. It is quiet enough to feel native, with recognition—not decoration—as the memorable element.

- All colors come from live `Color.menu.*`, `Color.accent`, and `Color.urgent` roles.
- All type comes from live `Style.font.menuFamily` and the shell’s font scale.
- All outer surfaces, inputs, chips, buttons, feedback, and focus shapes use `Style.cornerRadius`; theme radius `0` must produce square geometry everywhere.
- Spacing derives from `Style.space(...)` and `Style.spacing.*`.
- No literal hex colors, private font names, username paths, blur, gradient, glow, or decorative shadow.
- The overlay sits near the upper third of the active screen, no wider than roughly 640 shell-scaled pixels, and its height grows only for recognized details, description, syntax help, or errors.
- Empty state is a single task field. Secondary actions appear only after typing.

## Architecture

- `src/quick_task/parser.py`: pure bilingual parser and normalizer.
- `src/quick_task/todoist.py`: token loading and Todoist Quick Add HTTP client.
- `src/quick_task/cli.py`: newline-delimited JSON protocol over stdin/stdout with `parse` and `add` commands.
- `packaging/omarchy/plugins/danitrrga.quick-task/QuickTask.qml`: keep-loaded overlay, keyboard interaction, preview, and submit state.
- `deploy.sh`: idempotent user installation, legacy binding replacement, plugin enablement, permission hardening, and rollback backups.

The token is read from `TODOIST_API_TOKEN` or the existing `~/.config/tod.cfg`; it is never placed in argv, QML, logs, or error text. The installer tightens the existing config to mode `0600`.

## Acceptance contract

- Parser tests cover both languages, every weekday abbreviation, month rollover, accent-insensitive Spanish input, times, overlaps, suppression, and non-date numbers.
- HTTP tests prove JSON encoding, `meta: true`, note handling, timeouts, and token redaction.
- QML contract tests ban literal colors/radii/font names and require direct Omarchy `Color`/`Style` roles plus stdin-enabled process transport.
- Installer tests run twice against fixtures and prove no duplicate binding, backup creation, legacy rule removal, and private config permissions.
- Live verification summons the real overlay, checks exclusive focus and keyboard behavior, submits one disposable task, removes it through the API, and captures screenshots under one square and one rounded theme before restoring the original theme.
