# Quick Task: working on this plugin

An Omarchy 4 shell overlay for capturing Todoist tasks without leaving the workspace, with a helper
CLI (`src/quick_task/`, entry point in `bin/`). `README.md` says what it does and the date shorthand it
recognises; `docs/spec.md` is the behaviour spec.

## Layout

- `packaging/omarchy/plugins/danitrrga.quick-task/`: the plugin itself (`manifest.json`, `QuickTask.qml`, `QuickTaskLogic.js`). The manifest is not at the repo root, so the `omarchy-plugin-dev` skill's `deploy_plugin.py` cannot deploy this one.
- `src/quick_task/`: the parser and the Todoist client. `tests/`: pytest, including the plugin-contract and deploy tests.

## Work loop

`./deploy.sh` installs the CLI, the plugin folder under `~/.config/omarchy/plugins/` and the keybind; a
restart of the shell (`omarchy restart shell`) is needed after any QML change. Watch
`qs log -p /usr/share/omarchy/shell`. Run the tests with the repo's `.venv` (`.venv/bin/python -m pytest`).

## Rules that bit before

- A test is not evidence until it has been seen to fail: mutate the code, watch the test go red.
- The Todoist token is read from the user's `tod` config; never put it in an error message, a log or argv.
- Bilingual input (English and Spanish date words) is the point: change one language's rules and the other's tests must still pass.
