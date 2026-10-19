from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT
MANIFEST = PLUGIN / "manifest.json"
QML = PLUGIN / "QuickTask.qml"
LOGIC = PLUGIN / "QuickTaskLogic.js"


def test_manifest_declares_a_resident_overlay_with_a_real_entrypoint():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schemaVersion"] == 1
    assert manifest["id"] == "io.github.danitrrga.quick-task"
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

    input_start = source.index("id: keyCatcher")
    assert source.rfind("TextInput {", 0, input_start) != -1
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
    assert 'command: root.helperCommand.concat(["parse"])' in source
    assert 'command: root.helperCommand.concat(["add"])' in source
    assert source.count("write(") >= 2
    assert "JSON.stringify" in source
    assert "Authorization" not in source
    assert "TODOIST_API_TOKEN" not in source


def test_live_recognition_and_submit_states_are_present():
    source = QML.read_text(encoding="utf-8")

    assert "Timer" in source and "parseTimer.restart()" in source
    assert "root.tokens" in source
    assert "QuickTaskLogic.literalizeKind" in source
    assert "root.recognitions" in source
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
    assert "onTextEdited: root.edited(text, keyCatcher.cursorPosition)" in source
    edit_start = source.index("function edited(")
    edit_end = source.index("function refreshCompletion(", edit_start)
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
    assert "verticalAlignment: TextInput.AlignVCenter" in input_surface
    assert 'text: "What needs doing?"' in source
    assert "id: actionRow" in source
    assert "visible: root.hasDraft || root.showDescription || root.showSyntax" in source
    assert "anchors.horizontalCenter: parent.horizontalCenter" in source
    assert "Enter  Add" not in source
    assert "↓  Description" not in source


def test_the_footer_is_underlined_words_and_the_enter_hint_is_the_primary_action():
    source = QML.read_text(encoding="utf-8")
    footer = source[source.index("id: actionRow"):source.index("IpcHandler {")]

    assert footer.count("KeyHint {") == 5
    for key in ('key: "enter"', 'key: "↑ ↓"', 'key: "↓"', 'key: "⇧↓"', 'key: "esc"'):
        assert key in footer
    assert 'root.submitting ? "adding…" : "add"' in footer
    assert "enabled: root.hasDraft && !root.submitting" in footer
    assert "root.submit()" in footer
    assert "Rectangle {" not in footer and "Button {" not in footer
    assert not (Path(__file__).parents[1] / "KeyCap.qml").exists()


def test_what_was_recognised_is_one_quiet_line_of_words_not_boxes():
    source = QML.read_text(encoding="utf-8")
    line = source[source.index("id: metaFlow"):source.index("id: descriptionField")]

    assert "model: QuickTaskLogic.metaParts(root.visibleTokens, root.account)" in line
    assert "root.literalizeToken(modelData.token)" in line
    assert "visible: root.completion === null && root.visibleTokens.length > 0" in line
    assert "BorderSurface" not in line and "Rectangle" not in line
    assert "childrenRect.height" not in source
    assert "Grid {" not in source


def test_the_words_come_from_the_parser_ranges_and_the_editor_stays_on_top():
    source = QML.read_text(encoding="utf-8")

    assert 'import "QuickTaskLogic.js" as QuickTaskLogic' in source
    assert "QuickTaskLogic.styledDraft(root.draft, root.visibleTokens" in source
    assert "id: inlineHighlightLayer" not in source and "id: inlineUnderlineLayer" not in source
    assert "positionToRectangle(modelData" not in source
    assert "clip: true" in source
    assert source.index("id: coloredDraft") < source.index("id: keyCatcher")


def test_recognised_words_are_drawn_in_their_own_colour_with_no_tint_and_no_underline():
    source = QML.read_text(encoding="utf-8")
    field = source[source.index("id: keyCatcher"):]
    field = field[:field.index("onTextEdited")]

    assert 'color: "transparent"' in field and 'selectedTextColor: "transparent"' in field
    assert "textFormat: Text.StyledText" in source
    assert "text: root.styledDraft" in source
    assert "x: root.textOriginX" in source
    assert "Style.normalFillFor(" not in source


def test_a_word_missing_from_the_account_is_muted_in_the_text_and_struck_through_in_the_detail_line():
    source = QML.read_text(encoding="utf-8")

    assert "mark.known === false ? root.hex(Color.muted)" in source
    assert 'font.strikeout: modelData.note === "not found"' in source


def test_typing_or_deleting_at_the_end_keeps_the_earlier_words_coloured():
    source = QML.read_text(encoding="utf-8")
    edited = source[source.index("function edited("):source.index("function refreshCompletion(")]

    assert "text.indexOf(old) === 0 || old.indexOf(text) === 0" in edited
    assert "token.end <= limit" in edited
    assert "root.tokens = []" in edited


def test_syntax_types_use_live_semantic_omarchy_color_roles():
    source = QML.read_text(encoding="utf-8")

    assert "function syntaxColor(kind)" in source
    for role in (
        "Color.accent",
        "Color.menu.selectedText",
        "Color.popups.border",
        "Color.notifications.countdown",
        "Color.foreground",
        "Color.polkit.accent",
        "Color.urgent",
        "Color.lock.borderActive",
    ):
        assert role in source


def test_backspace_after_a_marked_range_makes_it_literal_before_deleting_text():
    source = QML.read_text(encoding="utf-8")

    handler = source[source.index("function handleKey("):source.index("function submit()")]
    assert "key === Qt.Key_Backspace" in handler
    assert "QuickTaskLogic.tokenEndingAt" in handler
    assert "root.literalizeToken(token)" in handler
    assert "if (root.handleKey(event.key, event.modifiers))" in source
    assert "event.accepted = true" in source


def test_the_real_input_and_the_ipc_hooks_share_one_key_path():
    source = QML.read_text(encoding="utf-8")

    assert source.count("function handleKey(") == 1
    assert "root.handleKey(event.key, event.modifiers)" in source
    assert "root.handleKey(keys[name], 0)" in source


def test_the_picker_never_takes_enter_until_an_entry_is_highlighted():
    source = QML.read_text(encoding="utf-8")

    assert "root.completionIndex >= 0 && (key === Qt.Key_Return || key === Qt.Key_Enter)" in source
    assert "root.completionIndex = next && !next.soft ? 0 : -1" in source


def test_escape_closes_the_picker_before_it_closes_the_overlay():
    source = QML.read_text(encoding="utf-8")
    handler = source[source.index("function handleKey("):source.index("function submit()")]

    assert handler.index("root.completion = null") < handler.index("root.dismiss()")


def test_account_sync_cannot_block_the_next_sync_and_carries_no_stdin():
    source = QML.read_text(encoding="utf-8")

    assert "syncProc.running = false" in source
    assert 'command: root.helperCommand.concat(["sync"])' in source
    assert 'command: root.helperCommand.concat(["account"])' in source


def test_the_ipc_state_never_exposes_the_token_or_the_account_contents():
    source = QML.read_text(encoding="utf-8")
    state = source[source.index("function state(): string"):]

    assert "token" not in state.lower().replace("tokens", "")
    assert "collaborators" not in state
    assert "email" not in state
    assert "root.account.projects.length" in state


def test_a_failed_sync_is_shown_to_the_user_and_never_hides_the_picker():
    source = QML.read_text(encoding="utf-8")

    assert "visible: root.accountNote.length > 0 && root.completion === null" in source
    assert "text: root.accountNote" in source


def test_typing_and_the_ipc_type_hook_share_the_edit_path_so_both_parse():
    source = QML.read_text(encoding="utf-8")
    edited = source[source.index("function edited("):source.index("function refreshCompletion(")]

    assert "root.edited(text, keyCatcher.cursorPosition)" in source
    assert "root.edited(text, text.length)" in source
    assert "parseTimer.restart()" in edited
    assert "root.refreshCompletion(cursor)" in edited


def test_the_helper_never_writes_bytecode_into_the_watched_plugin_folder():
    source = QML.read_text(encoding="utf-8")

    assert '["/usr/bin/python3", "-I", "-B", root.helperScript]' in source
    assert source.count("root.helperCommand.concat(") == 4
    assert "/usr/bin/python3" not in source.replace('["/usr/bin/python3", "-I", "-B", root.helperScript]', "")


def test_the_ipc_submit_hook_calls_the_same_function_enter_does():
    source = QML.read_text(encoding="utf-8")

    assert "function submit(): void { root.submit() }" in source
    assert "onAccepted: root.submit()" in source


def test_the_caret_is_drawn_explicitly_because_the_field_text_is_transparent():
    source = QML.read_text(encoding="utf-8")
    field = source[source.index("id: keyCatcher"):]
    field = field[:field.index("onTextEdited")]

    assert 'color: "transparent"' in field
    assert "cursorDelegate: Rectangle {" in field
    assert "height: keyCatcher.cursorRectangle.height" in field
    assert "color: root.foreground" in field


def test_the_coloured_layer_follows_the_fields_horizontal_scroll():
    source = QML.read_text(encoding="utf-8")
    field = source[source.index("id: keyCatcher"):]

    assert "root.textOriginX = keyCatcher.positionToRectangle(0).x" in source
    for signal in ("onContentWidthChanged", "onCursorRectangleChanged", "onWidthChanged"):
        assert f"{signal}: Qt.callLater(root.syncTextOrigin)" in field


def test_the_move_hint_is_informational_so_it_is_not_dimmed_like_a_disabled_button():
    source = QML.read_text(encoding="utf-8")
    hint = Path(QML).with_name("KeyHint.qml").read_text(encoding="utf-8")
    move = source[source.index('key: "↑ ↓"'):]
    move = move[:move.index("KeyHint {")]

    assert "interactive: false" in move and "enabled: false" not in move
    assert "enabled: root.enabled && root.interactive" in hint
