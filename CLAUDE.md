# Quick Task: working on this plugin

An Omarchy 4 shell overlay for capturing Todoist tasks without leaving the workspace, with a helper
CLI in `helper/`. `README.md` says what it does and the date shorthand it
recognises; `docs/spec.md` is the behaviour spec.

## Layout

Repo root is plugin root (`manifest.json`, `QuickTask.qml`, `QuickTaskLogic.js`); the id is `io.github.danitrrga.quick-task`.
`helper/quick_task/` is the Python helper (parser, Todoist client, account cache, CLI), run by the overlay as
`/usr/bin/python3 helper/quick-task <command>`. `tests/` is pytest; JS logic is tested by running it in `node`.

## Work loop

Deploy with the `omarchy-plugin-dev` skill's `deploy_plugin.py . --restart` (QML edits need a shell restart). The
running shell is the Qt 6.12 patched copy: watch `qs log -p ~/.local/share/omarchy-patched/shell`, and keep
`import QtQuick 6.11` in every QML file that uses `Color.*` (Qt's builtin `Color` otherwise shadows Omarchy's; see
`~/.local/bin/omarchy-shell-color-patch.sh`). Never edit the live copy. The venv lives outside the repo
(`~/.cache/venvs/quick-task`) because `omarchy plugin validate` rejects the symlinks in a `.venv`; run
`~/.cache/venvs/quick-task/bin/python -m pytest`. The keybind is the user's, in `~/.config/hypr/bindings.lua`.
Test the UI through IPC: `omarchy-shell io.github.danitrrga.quick-task state|type|key|pick|loadAccountJson`
(after `open`, wait for the real account load before `loadAccountJson`, or it overwrites the fake one).

## Rules that bit before

- The helper runs as `python3 -I -B`: the shell watches the plugin folder and reloads the plugin (closing the overlay) on any write, so a `__pycache__` appearing there resets the user's draft.
- Token offsets leave the helper in UTF-16 units (what QML and JS index by); Python's are code points, and an emoji shifts every later highlight by one.
- Todoist's `/tasks/quick` cannot read multi-word names or `%label`; mentions are resolved locally (`helper/quick_task/mentions.py`). Reminders and deadlines need Todoist Pro. Probe the live API with disposable tasks and delete them; never guess a Todoist behaviour.

- Todoist's `/tasks/quick` `note` creates a *comment*; the task description is set by id (`set_description`). Probed live 2026-10-20.
- A test is not evidence until it has been seen to fail: mutate the code, watch the test go red.
- The Todoist token comes from `TODOIST_API_TOKEN`, then the file Quick Task saves (`~/.config/quick-task/config.json`, written by `Ctrl+,` or `quick-task token set`), then the `tod` config (`helper/quick_task/credentials.py`). It never goes in an error message, a log, argv or the IPC state: the overlay writes it to the helper's stdin, one line (`readline`, because the overlay never closes the pipe), and `token set` refuses it as an argument.
- Bilingual input (English and Spanish date words) is the point: change one language's rules and the other's tests must still pass.
