from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "packaging" / "omarchy" / "plugins" / "danitrrga.quick-task"
MANIFEST = PLUGIN / "manifest.json"
QML = PLUGIN / "QuickTask.qml"


def test_manifest_declares_a_resident_overlay_with_a_real_entrypoint():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schemaVersion"] == 1
    assert manifest["id"] == "danitrrga.quick-task"
    assert manifest["kinds"] == ["overlay"]
    assert manifest["keepLoaded"] is True
    assert manifest["entryPoints"] == {"overlay": "QuickTask.qml"}
    assert QML.is_file()


def test_overlay_owns_the_shell_lifecycle_and_exclusive_keyboard_focus():
    source = QML.read_text(encoding="utf-8")

    for contract in (
        "function open(payloadJson)",
        "function close()",
        "function dismiss()",
        "function toggle()",
        "PanelWindow",
        'WlrLayershell.namespace: "quick-task"',
        "WlrKeyboardFocus.Exclusive",
        "keyCatcher.forceActiveFocus()",
    ):
        assert contract in source


def test_keyboard_contract_is_implemented_on_the_real_input_surface():
    source = QML.read_text(encoding="utf-8")

    assert "QQC.TextField" in source
    assert "Qt.Key_Escape" in source
    assert "Qt.Key_Return" in source or "onAccepted:" in source
    assert "Qt.Key_Down" in source
    assert "Qt.ShiftModifier" in source
    assert "descriptionField.forceActiveFocus()" in source
    assert "root.showSyntax = !root.showSyntax" in source


def test_parse_and_add_cross_the_process_boundary_over_stdin_not_argv():
    source = QML.read_text(encoding="utf-8")

    assert source.count("stdinEnabled: true") == 2
    assert '[root.helperPath, "parse"]' in source
    assert '[root.helperPath, "add"]' in source
    assert source.count("write(") >= 2
    assert "JSON.stringify" in source
    assert "Authorization" not in source
    assert "TODOIST_API_TOKEN" not in source


def test_live_recognition_and_submit_states_are_present():
    source = QML.read_text(encoding="utf-8")

    assert "Timer" in source and "parseTimer.restart()" in source
    assert "root.tokens" in source
    assert "root.ignoredTokenIds" in source
    assert "root.submitting" in source
    assert "root.errorMessage" in source
    assert "root.draft" in source
    assert "root.dismiss()" in source
    assert "Quickshell.execDetached" in source


def test_draft_is_only_cleared_on_success_not_before_the_request_finishes():
    source = QML.read_text(encoding="utf-8")
    add_finished = source.index("function handleAddResult")
    next_function = source.find("\n  function ", add_finished + 1)
    body = source[add_finished : next_function if next_function != -1 else len(source)]

    assert "root.draft = \"\"" in body
    assert "if (!parsed.ok)" in body
    assert body.index("if (!parsed.ok)") < body.index("root.draft = \"\"")
