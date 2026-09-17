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


def test_shell_can_inject_its_runtime_path_into_the_plugin():
    source = QML.read_text(encoding="utf-8")

    assert 'property string omarchyPath: Quickshell.env("OMARCHY_PATH")' in source
    assert 'readonly property string omarchyPath' not in source


def test_keyboard_contract_is_implemented_on_the_real_input_surface():
    source = QML.read_text(encoding="utf-8")

    assert "QQC.TextField" in source
    assert "Qt.Key_Escape" in source
    assert "Qt.Key_Return" in source or "onAccepted:" in source
    assert "Qt.Key_Down" in source
    assert "Qt.ShiftModifier" in source
    assert "descriptionField.forceActiveFocus()" in source
    assert "root.showSyntax = !root.showSyntax" in source


def test_escape_dismisses_the_overlay_from_the_description_too():
    source = QML.read_text(encoding="utf-8")
    field_start = source.index("id: descriptionField")
    field_end = source.index("id: syntaxText", field_start)
    description_surface = source[field_start:field_end]

    assert "Keys.onEscapePressed: root.dismiss()" in description_surface


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


def test_plugin_renders_the_tested_parser_tokens_without_a_second_parser():
    source = QML.read_text(encoding="utf-8")

    assert "readonly property var visibleTokens: root.tokens" in source
    assert "function metadataTokens()" not in source


def test_editing_clears_derived_state_and_stale_parse_results_are_ignored():
    source = QML.read_text(encoding="utf-8")
    edit_start = source.index("onTextEdited:")
    edit_end = source.index("onAccepted:", edit_start)
    edit_handler = source[edit_start:edit_end]
    parse_start = source.index("function handleParseResult")
    parse_end = source.index("function submit", parse_start)
    parse_handler = source[parse_start:parse_end]

    assert "root.tokens = []" in edit_handler
    assert "String(parsed.result.original) === root.draft" in parse_handler


def test_draft_is_only_cleared_on_success_not_before_the_request_finishes():
    source = QML.read_text(encoding="utf-8")
    add_finished = source.index("function handleAddResult")
    next_function = source.find("\n  function ", add_finished + 1)
    body = source[add_finished : next_function if next_function != -1 else len(source)]

    assert "root.draft = \"\"" in body
    assert "if (!parsed.ok)" in body
    assert body.index("if (!parsed.ok)") < body.index("root.draft = \"\"")


def test_empty_capture_is_one_quiet_field_instead_of_a_debug_form():
    source = QML.read_text(encoding="utf-8")
    input_start = source.index("id: keyCatcher")
    input_end = source.index("onTextEdited:", input_start)
    input_surface = source[input_start:input_end]

    assert "readonly property bool hasDraft:" in source
    assert "background: Item {}" in input_surface
    assert "id: actionRow" in source
    assert "visible: root.hasDraft || root.showDescription || root.showSyntax" in source
    assert "anchors.horizontalCenter: parent.horizontalCenter" in source
    assert "Enter  Add" not in source
    assert "↓  Description" not in source


def test_primary_action_has_no_decorative_status_dot():
    source = QML.read_text(encoding="utf-8")
    add_start = source.index("id: addButton")
    add_end = source.index("onClicked: root.submit()", add_start)
    add_surface = source[add_start:add_end]

    assert "Rectangle {" not in add_surface
    assert 'text: root.submitting ? "Adding…" : "Add task"' in add_surface


def test_recognition_grid_wraps_without_children_rect_height_bindings():
    source = QML.read_text(encoding="utf-8")
    grid_start = source.index("id: tokenGrid")
    grid_end = source.index("Repeater {", grid_start)
    grid_surface = source[grid_start:grid_end]

    assert "childrenRect.height" not in source
    assert "columns: Math.max(1, Math.min(4, root.visibleTokens.length))" in grid_surface
