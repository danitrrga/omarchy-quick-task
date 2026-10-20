# Quick Task

![Quick Task: type a task like a sentence and Todoist's projects, sections, labels and dates are read out of it](docs/banner.png)

Capture a Todoist task from anywhere in Omarchy without leaving what you are doing. Press a key, type a sentence, press `Enter`. Dates, projects, sections, labels and priority are read out of the sentence as you type, in English and Spanish, and your own projects, sections and labels autocomplete.

![The overlay with a sentence typed: each part is coloured and the line below says how it was read](docs/screenshots/ready.png)

Add-only: it creates tasks and never reads or changes the ones you have.

## What it does

- **Reads the sentence.** `tomorrow 9am`, `tmr`, `31 oct`, `31 de octubre`, `fri`, `lunes a las 9` become a date; `#Work`, `/Planning`, `@waiting` and `p2` become a project, section, label and priority. What was understood is shown in colour, with one quiet line under the sentence saying it in words.
- **Autocompletes from your account.** `#` lists your projects, `/` the sections of the project before it, `%` or `@` your labels, `+` that project's collaborators. `Enter` or `Tab` picks, the arrows move, `Esc` closes the list.
- **Never in the way.** The window opens on one field. Everything else appears once there is something to show, and the Todoist data is cached so it opens instantly.
- **Takes the theme.** Colours, font, spacing and corner radius come from the live Omarchy theme.

![Typing # opens a list of your projects with their section counts](docs/screenshots/picker.png)

![A Spanish sentence: lunes a las 9 is read as Monday 09:00](docs/screenshots/spanish.png)

The images come from an invented account (`tools/screenshots.py`).

## From a terminal or an agent

The same parser is a command, so a script or an AI agent can send a task without opening anything:

```sh
quick-task add "Call Marta tomorrow 9am #Work @waiting p2" --note "ask about the lease"
```

```text
Added: Call Marta (8401726593)
  date: tomorrow 9am -> Wed 21 Oct, 09:00
  project: #Work
  label: @waiting
  priority: p2
```

`quick-task parse "..."` shows how a sentence is read and adds nothing; `--json` prints the overlay's JSON instead of the plain lines. Success exits 0; a failure prints `error: ...` on stderr and exits 1 (with `--json`, `{"ok":false,"error":...}` on stdout). It is add-only, like the overlay.

The installed command is `~/.config/omarchy/plugins/io.github.danitrrga.quick-task/helper/quick-task`. To have it on your `PATH` as `quick-task` (optional, nothing does this for you):

```sh
ln -s ~/.config/omarchy/plugins/io.github.danitrrga.quick-task/helper/quick-task ~/.local/bin/quick-task
```

It finds the token the same way the overlay does (see [Connect Todoist](#connect-todoist)), so an agent running in your shell usually already has it. To set one up from a terminal or script, pipe it in; it is never taken as an argument, because every user on the machine can read arguments:

```sh
printf %s "$TOKEN" | quick-task token set     # checks it with Todoist, then saves it (mode 0600)
quick-task token status                       # which source is in use, and whether Todoist accepts it
quick-task token clear                        # forget the saved one
```

`token status` never prints the token.

### Tell your agent

Paste this into the `CLAUDE.md` or `AGENTS.md` of any project, or into an agent's instructions:

```text
## Todoist capture
To add a task to my Todoist, run: quick-task add "<sentence>" [--note "<details>"]
- Write the sentence as I would type it. Dates: tomorrow 9am, fri, 31 oct, lunes a las 9.
  Project #Name, section /Name, label @name, priority p1 (urgent) to p4. Only the last
  date, project, section and priority count. Reminders (!) and deadlines ({}) need Todoist Pro.
- Unsure how a sentence is read? Run quick-task parse "<sentence>" first: it adds nothing.
- Success prints "Added: <title> (<id>)" and exits 0: the task exists, never run it again.
  A failure prints "error: ..." on stderr and exits 1: tell me, do not loop.
- It only adds. It cannot list, edit or delete tasks. The sentence is sent to Todoist, so
  put no secrets in it.
- If it says the token is missing or rejected, tell me. Check with quick-task token status.
  Only run quick-task token set with a token I gave you for this, piped in on stdin, never as
  an argument or written to a file.
```

## Install

```sh
omarchy plugin add https://github.com/danitrrga/omarchy-quick-task.git --enable
```

Needs the system `python3` at `/usr/bin/python3` (standard library only, no packages).

### Connect Todoist

Create a personal API token in Todoist under Settings → Integrations → Developer, open Quick Task, press `Ctrl` `,` and paste it. `Enter` asks Todoist whether it accepts the token and saves it only if it does, in `~/.config/quick-task/config.json` (mode `0600`). `Esc` goes back to the task field.

Quick Task looks for a token in this order, and the first one found is used:

1. the `TODOIST_API_TOKEN` environment variable of the shell;
2. the token saved by `Ctrl` `,` (or by `quick-task token set`);
3. the `token` field of `~/.config/tod.cfg`, the config file of the [`tod`](https://github.com/alanvardy/tod) client (JSON, keep it mode `0600`).

The settings view says which one is in use. "forget saved token" there, or `quick-task token clear`, removes the saved one.

### Open it with a key

The plugin does not touch your Hyprland config. Add a binding:

```lua
-- ~/.config/hypr/bindings.lua
o.bind("SUPER + SHIFT + SEMICOLON", "Quick task (Todoist)", "omarchy-shell shell summon io.github.danitrrga.quick-task '{}'")
```

### Remove

```sh
omarchy plugin remove io.github.danitrrga.quick-task
```

Then delete the binding and, to erase what it stored, `~/.cache/quick-task/` (account names) and `~/.config/quick-task/` (the saved token).

## Using it

| Key | Does |
| --- | --- |
| `Enter` | add the task (or pick the highlighted entry when a list is open) |
| `Tab` | pick the highlighted entry |
| `↑` `↓` | move in the list |
| `↓` | with no list open: add a note (description) |
| `⇧` `↓` | show the syntax reminder |
| `Esc` | close the list; a second `Esc` closes the window |
| `Backspace` | right after a coloured word: keep that word as plain text |
| `Ctrl` `,` | open or close the token settings (`Esc` also goes back) |

Click any item on the detail line to keep it as plain text too. After a task is added the window closes and a notification confirms it.

### What is recognised

| In the sentence | Becomes |
| --- | --- |
| `today`, `tomorrow`, `tmr`, `2moro`, `hoy`, `mañana`, `pasado mañana` | a date |
| `mon`, `tues`, `lunes`, `this friday`, `el próximo martes` | the next such day |
| `21st`, `el 21` | the next 21st |
| `31 oct`, `oct 31`, `31 de octubre`, `31 oct 2027`, `31/10`, `5/10/26` | that date (a past one means next year) |
| `at 5pm`, `9am`, `a las 9` after a date | its time |
| `#Work` · `/Planning` · `@waiting` or `%waiting` · `p1` to `p4` | project · section · label · priority |

Names with spaces and emoji work (`#Side project`, `/Rutinas 🔁`). An unknown `#name` stays plain text, exactly as in Todoist, and the detail line says "not found". Only the last date, project, section and priority in a sentence count.

### Todoist Pro

Reminders (`!30 min before`) and deadlines (`{oct 30}`) are Todoist Pro features. On a free account the `!` list is not offered, their detail items say "needs Todoist Pro", and if you submit one anyway Todoist's own refusal is shown. Plain dates never need braces.

### How the names are applied

Todoist's quick-add endpoint reads only single-word names, and only `@label`, so `#Side project`, `/Rutinas 🔁` or `%waiting` would be left in the title. Quick Task therefore matches mentions to your cached account itself (ignoring case and accents), takes them out of the text, adds the task, then moves it and sets its labels by id. If that second step fails the task still exists, in Inbox, and the window says so.

## What leaves your machine

Only requests to `api.todoist.com`, authenticated with your token:

- the task text, note and the ids above, when you add a task;
- reads of your projects, sections, labels, collaborators and plan, to fill the lists.

Nothing else is sent anywhere. The token is never written to a log, an error message, a process argument or the plugin's IPC state.

## What it stores

- `~/.cache/quick-task/account.json` (mode `0600`): the names and ids of your projects, sections, labels and collaborators, refreshed in the background when older than five minutes. No task is stored.
- `~/.config/quick-task/config.json` (mode `0600`, in a `0700` folder): the token, only if you saved one with `Ctrl` `,` or `quick-task token set`. Your `tod.cfg` and your environment are only ever read.

## What it runs

Every command the plugin starts, nothing else:

- `/usr/bin/python3 -I -B <plugin folder>/helper/quick-task parse|add|account|sync|token`, which makes the HTTPS requests above (`token status` and `token set` ask `api.todoist.com` whether a token is accepted; `token set` and `token clear` write or delete the file above);
- `<omarchy>/bin/omarchy-notification-send "Task added to Todoist"` after a task is added (the task text is never put in a command line).

The plugin starts nothing else. `helper/quick-task` also runs when you or an agent call it from a terminal, and then makes the same requests to `api.todoist.com`.

## Development

```sh
uv venv --python 3.14 ~/.cache/venvs/quick-task    # outside the repo: the plugin validator rejects symlinks
VIRTUAL_ENV=~/.cache/venvs/quick-task uv pip install pytest pillow
~/.cache/venvs/quick-task/bin/python -m pytest -q
omarchy plugin validate .
```

`omarchy-shell io.github.danitrrga.quick-task state` shows what the overlay computed; `open`, `type`, `key`, `pick`, `submit` and `close` drive the same code a key press does. Regenerate the screenshots with `python3 tools/screenshots.py` (workspace 5, invented account) and the banner with the command at the top of `tools/banner.html`. The behaviour spec is in [docs/spec.md](docs/spec.md); `CLAUDE.md` has the working notes.

## License

MIT, see [LICENSE](LICENSE).
