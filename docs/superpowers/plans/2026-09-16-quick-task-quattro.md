# Quick Task Quattro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and install a native Omarchy Todoist quick-capture overlay with deterministic bilingual date shorthand and complete keyboard-first Quick Add submission.

**Architecture:** A pure Python parser normalizes only date phrases, a small HTTP client delegates the remaining syntax to Todoist’s Quick Add endpoint, and a keep-loaded QML overlay talks to the CLI using newline-delimited JSON over stdin. An idempotent deploy script installs the helper and plugin, replaces the legacy binding, and keeps backups.

**Tech Stack:** Python 3.13 standard library, pytest, Qt Quick/QML, Quickshell, Omarchy shell plugin API, Bash installer.

**Spec:** `docs/spec.md`

## Global Constraints

- English and Spanish are recognized simultaneously; no locale switch.
- Todoist tokens never appear in argv, QML, logs, fixtures, or returned errors.
- Every visible color, font, spacing value, and corner radius comes from live Omarchy shell tokens.
- A theme radius of `0` produces square geometry on every surface.
- No runtime dependency outside Python’s standard library and the installed Omarchy shell.
- Existing user config is backed up before mutation; installation is idempotent.

---

### Task 1: Bilingual recognition engine

**Files:**
- Create: `pyproject.toml`
- Create: `src/quick_task/__init__.py`
- Create: `src/quick_task/parser.py`
- Create: `tests/test_parser.py`

**Interfaces:**
- Produces: `parse_quick_text(text: str, now: datetime, ignored: Collection[str] = ()) -> ParseResult`
- Produces: `ParseResult.to_dict() -> dict[str, object]` containing `original`, `normalized`, and `tokens`.

- [ ] **Step 1: Write failing parser tests** for `mon`, `lun`, `este viernes`, `this Friday`, `21st`, `el 21`, month rollover, `mañana`, Spanish time, ignored tokens, and a literal number such as `buy 21 screws`.
- [ ] **Step 2: Run `pytest tests/test_parser.py -q`** and confirm failure because `quick_task.parser` does not exist.
- [ ] **Step 3: Implement immutable token/result dataclasses**, accent-insensitive lexicons, non-overlapping match selection, date resolution, time normalization, and right-to-left text replacement.
- [ ] **Step 4: Run `pytest tests/test_parser.py -q`** and confirm all recognition tests pass.
- [ ] **Step 5: Commit** with `git add pyproject.toml src tests/test_parser.py && git commit -m "feat: add bilingual quick-date parser"`.

### Task 2: Private Todoist Quick Add client and CLI protocol

**Files:**
- Create: `src/quick_task/todoist.py`
- Create: `src/quick_task/cli.py`
- Create: `bin/quick-task`
- Create: `tests/test_todoist.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `parse_quick_text(...)` from Task 1.
- Produces: `load_token(environ, config_path) -> str`.
- Produces: `quick_add(text, note, token, opener=urlopen) -> dict[str, object]`.
- Produces: CLI commands `quick-task parse` and `quick-task add`, each reading one JSON object per line and writing one JSON object per line.

- [ ] **Step 1: Write failing client tests** proving the request URL, bearer header, JSON content type, `text`, `note`, `meta: true`, timeout, and redacted HTTP/network errors.
- [ ] **Step 2: Run `pytest tests/test_todoist.py -q`** and confirm the client module is missing.
- [ ] **Step 3: Implement token loading and the standard-library HTTP client** with explicit timeout and bounded response parsing.
- [ ] **Step 4: Run the client tests** and confirm green.
- [ ] **Step 5: Write failing CLI tests** for parse/add JSON lines, malformed input, empty drafts, description forwarding, and normalized submission.
- [ ] **Step 6: Implement the CLI and launcher**, keeping stdout machine-readable and diagnostics free of secrets.
- [ ] **Step 7: Run `pytest tests/test_todoist.py tests/test_cli.py -q`** and confirm green.
- [ ] **Step 8: Commit** with `git add src bin tests && git commit -m "feat: add private Todoist quick-add bridge"`.

### Task 3: Native Omarchy overlay

**Files:**
- Create: `packaging/omarchy/plugins/danitrrga.quick-task/manifest.json`
- Create: `packaging/omarchy/plugins/danitrrga.quick-task/QuickTask.qml`
- Create: `tests/test_plugin_contract.py`
- Create: `tests/test_theme_contract.py`

**Interfaces:**
- Consumes: installed `~/.local/bin/quick-task parse|add` newline protocol.
- Produces: shell methods `open(payloadJson)`, `close()`, `dismiss()`, and `toggle()` for `omarchy-shell shell summon|toggle`.

- [ ] **Step 1: Write failing manifest and QML contract tests** for overlay kind, `keepLoaded`, entry-point existence, exclusive keyboard focus, stdin transport, parse debounce, submit/error states, and the keyboard contract.
- [ ] **Step 2: Write failing theme tests** banning hex colors, fixed font families, fixed `radius:` values, username paths, and requiring `Color.menu.*`, `Style.font.menuFamily`, `Style.space`, and `Style.cornerRadius` throughout.
- [ ] **Step 3: Run `pytest tests/test_plugin_contract.py tests/test_theme_contract.py -q`** and confirm missing plugin files fail.
- [ ] **Step 4: Implement `QuickTask.qml`** using `PanelWindow`, `BorderSurface`, a focused `TextInput`, recognition/action chips, progressive description/help, stable loading state, native notification feedback, and preserved drafts on failure.
- [ ] **Step 5: Run contract tests and `qmllint` when available**; fix every warning or document only tooling false positives in the test.
- [ ] **Step 6: Commit** with `git add packaging tests && git commit -m "feat: add native Omarchy quick-task overlay"`.

### Task 4: Idempotent installation and migration

**Files:**
- Create: `deploy.sh`
- Create: `tests/test_deploy.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 2 helper and Task 3 plugin tree.
- Produces: `~/.local/bin/quick-task`, `~/.local/share/quick-task/quick_task`, `~/.config/omarchy/plugins/danitrrga.quick-task`, an enabled shell plugin, and the migrated Hyprland binding.

- [ ] **Step 1: Write failing deploy fixture tests** that redirect every destination, run twice, and assert one binding, one plugin tree, a content-preserving backup, removal of the legacy terminal window rule, and mode `0600` on the Todoist config.
- [ ] **Step 2: Run `pytest tests/test_deploy.py -q`** and confirm `deploy.sh` is missing.
- [ ] **Step 3: Implement backup-first deployment** with environment-redirectable targets, exact legacy-line migration, atomic staging, and optional reload suppression for tests.
- [ ] **Step 4: Run the deploy test twice and the complete unit suite**.
- [ ] **Step 5: Replace the scaffold README** with usage, grammar, architecture, install, rollback, and test instructions.
- [ ] **Step 6: Commit** with `git add deploy.sh README.md tests/test_deploy.py && git commit -m "feat: install Quick Task into Omarchy"`.

### Task 5: Live installation and verification

**Files:**
- Modify only through `deploy.sh`: user plugin directory, helper directory, Todoist config permissions, Hyprland binding/config.
- Create: `docs/screenshots/square-theme.png`
- Create: `docs/screenshots/rounded-theme.png`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a working desktop integration and visual evidence for both geometry modes.

- [ ] **Step 1: Run the full suite and static checks**: `pytest -q`, `python -m compileall -q src`, `bash -n deploy.sh`, and `git diff --check`.
- [ ] **Step 2: Run `./deploy.sh` twice** and confirm the second run makes no config duplication.
- [ ] **Step 3: Summon through the real global binding path**, query shell/plugin state, and test `Esc`, `Down`, `Shift + Down`, parse refresh, and error draft preservation.
- [ ] **Step 4: Exercise the required phrases**—`mon`, `lun`, `21st`, `este viernes`, and `el 21`—against a fixed parser clock and the live overlay.
- [ ] **Step 5: Submit a clearly named disposable task**, read the returned task id, delete it with the Todoist API, and verify no test task remains.
- [ ] **Step 6: Switch to one installed square theme and one rounded theme**, capture the overlay, inspect both images for clipping/focus/contrast/radius consistency, then restore the original theme.
- [ ] **Step 7: Run the suite once more after live deployment** and commit documentation/screenshots with `git commit -m "test: verify Quick Task on live Omarchy themes"`.

