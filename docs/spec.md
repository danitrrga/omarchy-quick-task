# Quick Task Quattro specification

## Outcome

Quick Task is a resident Omarchy overlay for sending a fully structured task to Todoist from anywhere on the desktop. It must appear immediately from the existing `Super + Shift + ;` binding, accept English and Spanish in the same field, make its interpretation visible before submission, and disappear after a successful add.

## Interaction contract

1. The global binding summons a keep-loaded `io.github.danitrrga.quick-task` Omarchy overlay.
2. Focus starts in the task field. `Enter` adds, `Esc` closes, `Down` reveals and focuses the description field, and `Shift + Down` reveals the syntax reference.
3. Recognition runs after a short typing debounce. It never blocks input or contacts Todoist.
4. Recognized details appear both as theme-aware inline marks and as compact chips below the sentence. The last occurrence of each detail type wins. With the cursor immediately after an active mark, the first `Backspace` makes every current occurrence of that type literal without deleting visible text; subsequent backspaces edit normally.
5. During submission, the draft stays visible and the add action shows activity without changing size.
6. Success dismisses the overlay and sends native Omarchy feedback. Failure keeps the full draft and shows a specific retryable error.
7. `Ctrl + ,` swaps the task field for the token settings in the same card, and `Ctrl + ,` or `Esc` swaps it back (a second `Esc` closes the window). The settings show which source the token comes from (environment, saved, or `tod.cfg`) and whether Todoist accepts it. `Enter` sends the pasted token to the helper on stdin, Todoist must accept it before it is saved to `~/.config/quick-task/config.json` (mode `0600`), and a rejected token is refused with Todoist’s own message while the field keeps its text. The field is masked, and the token never appears in a command line, a log, an error or the IPC state.

## Recognition contract

Recognition is deliberately split in two:

- A deterministic local normalizer handles bilingual date shorthand and produces live preview data.
- Todoist’s Quick Add endpoint remains the authority for projects, sections, labels, priorities, assignees, reminders, deadlines, recurrence, and the final created task.

The normalizer supports English and Spanish simultaneously, regardless of the Todoist account language:

- Weekdays and common abbreviations: `monday`, `mon`, `lunes`, `lun`, and equivalents for all seven days.
- Relative dates: `today`, `tod`, `tomorrow`, `tom`, `tmrw`, `hoy`, `mañana`, `pasado mañana`.
- Qualified weekdays: `this Friday`, `este viernes`, `next Tuesday`, `el próximo martes`.
- Dates with a month, in either order and either language (`31 oct`, `oct 31`, `31 de octubre`), with an optional year; and `d/m`, `m/d` when unambiguous or `d/m/yy`. A bare `1/2` is not a date. A date already past resolves to next year.
- Days of month: `21st`, `21º`, `el 21`. A day that has already passed resolves to the next month so quick capture does not silently create an overdue task.
- Times adjacent to dates remain part of the normalized sentence; Spanish `a las 9` is normalized to `at 09:00`.

Recognized date phrases are replaced with an absolute `YYYY-MM-DD` string before submission. This removes account-language ambiguity while preserving Todoist’s parser for the rest of the sentence.

Only the final occurrence of each detail type is active. Earlier occurrences are protected with an invisible word joiner before submission, so Todoist leaves them in task content instead of parsing them again. Literalizing an active inline mark protects every current occurrence of that type, preventing an older value from being promoted; newly typed syntax can still be recognized normally.

Todoist metadata owns its full recognized span. A date-like label such as `@tomorrow`, project such as `#viernes`, assignee such as `+monday`, or deadline such as `{due friday}` is therefore previewed only as that metadata and never simultaneously as a due date.

The overlay also previews Todoist syntax for `#project`, `/section`, `%label` and legacy `@label`, `p1`–`p4`, `+assignee`, `!reminder`, and `{deadline}`. The description is set on the task by id after it is created: quick-add’s `note` field would create a comment, not a description.

## Current Todoist parity

The shipping scope recreates the desktop Quick Add path: global invocation, date/time recognition, project, section, labels, priority, assignee, reminder, deadline, description, keyboard dismissal, and a visible way to disregard a recognized date. Todoist’s newer Ramble voice mode, AI extraction from files/images, attachments, and location reminders are separate capture modes and are not part of this fast text overlay.

Todoist’s current help describes the Quick Add feature and syntax at <https://www.todoist.com/help/todoist/features/use-task-quick-add-in-todoist-va4Lhpzz>. The current API contract is `POST /api/v1/tasks/quick` with JSON, `meta: true`, and the task text in `text`: <https://developer.todoist.com/api/v1/#tag/Tasks/operation/quick-add-task>.

## Visual contract

The chosen direction combines the restrained dark surface with the instrument panel’s explicit state. It is quiet enough to feel native, with recognition—not decoration—as the memorable element.

- All colors come from live Omarchy roles. Syntax types use semantic palette tokens (`accent`, selected menu text, popup border, notification countdown, foreground, polkit accent, urgent, and lock active border), so both their inline mark and summary chip adapt with the active theme.
- All type comes from live `Style.font.menuFamily` and the shell’s font scale.
- All outer surfaces, inputs, chips, buttons, feedback, and focus shapes use `Style.cornerRadius`; theme radius `0` must produce square geometry everywhere.
- Inline syntax marks sit behind the native editor, use the parser’s exact source spans, follow horizontal scrolling, and inherit `Style.cornerRadius` without intercepting cursor or selection input.
- Spacing derives from `Style.space(...)` and `Style.spacing.*`.
- No literal hex colors, private font names, username paths, blur, gradient, glow, or decorative shadow.
- The overlay sits near the upper third of the active screen, no wider than roughly 640 shell-scaled pixels, and its height grows only for recognized details, description, syntax help, or errors.
- Empty state is a single task field. Secondary actions appear only after typing.

## Mentions and Todoist Pro

Todoist's Quick Add endpoint cannot read names with spaces or `%label`, so `#project`, `/section` and labels are resolved locally from the cached account and applied by id after the task is created (see README, "What Todoist's API reads"). Unknown mentions remain literal text and are marked "not found". Reminders and deadlines require Todoist Pro: without it the `!` picker is hidden and their chips say so.

## Visual notes

A recognised word is drawn in its kind's colour with a soft tint of the same colour behind it; there is no underline. The text field itself is transparent and supplies only the caret and selection; the words are drawn by a StyledText layer under it, so every character keeps its width. The footer follows the agenda panel: a hairline, a status on the left (`synced 10:07`, silent after a failed sync) and boxed keycaps with a word beside them on the right (`↓ note`, `⇧ ↓ syntax`, `esc close`, `enter add`, the last in the accent colour), each clickable. Keys are plain words in the box, not glyphs the font might lack.

## Autocomplete contract

Typing a sigil at the start of a word opens a picker built from the account (projects, sections of the project written earlier in the sentence, labels, collaborators of that project if shared) plus fixed lists for reminders and priority. `#`, `/`, `%`, `@`, `+`, `!` preselect the first entry; `Enter` and `Tab` pick it. The priority picker (a lone `p`) is soft: nothing is selected and `Enter` still submits until `Down` selects an entry. `Esc` closes the picker first. Picking rewrites only the typed trigger and puts the cursor after the inserted name. Account data comes from a cache refreshed in the background, so opening never waits on the network; a failed refresh is shown under the field.

## Architecture

- `helper/quick_task/parser.py`: pure bilingual parser and normalizer.
- `helper/quick_task/todoist.py`: token loading and the Todoist HTTP client (Quick Add, GET).
- `helper/quick_task/account.py`: paginated account reads and the private cache.
- `helper/quick_task/cli.py`: newline-delimited JSON protocol over stdin/stdout with `parse`, `add`, `account` and `sync` commands.
- `QuickTaskLogic.js`: picker and literal-protection logic, testable without the shell.
- `QuickTask.qml`: keep-loaded overlay, keyboard interaction, preview, picker and submit state.

The token is read from `TODOIST_API_TOKEN` or the existing `~/.config/tod.cfg`; it is never placed in argv, QML, logs, IPC state or error text.

## Acceptance contract

- Parser tests cover both languages, every weekday abbreviation, month rollover, accent-insensitive Spanish input, times, overlaps, suppression, and non-date numbers.
- HTTP tests prove JSON encoding, `meta: true`, note handling, timeouts, and token redaction.
- QML contract tests ban literal colors/radii/font names and require direct Omarchy `Color`/`Style` roles plus stdin-enabled process transport.
- Account tests prove pagination, collaborators only for shared projects, a private atomic cache, and token redaction. Completion tests prove each picker rule and that every rule fails when its code is broken.
- Live verification summons the real overlay, checks exclusive focus and keyboard behavior, submits one disposable task, removes it through the API, and captures screenshots under one square and one rounded theme before restoring the original theme.
