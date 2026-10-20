import QtQuick 6.11
import QtQuick.Controls as QQC
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "QuickTaskLogic.js" as QuickTaskLogic

Item {
  id: root

  property var shell: null
  property var manifest: null

  property bool opened: false
  property bool submitting: false
  property bool parseQueued: false
  property bool showDescription: false
  property bool showSyntax: false
  property string draft: ""
  property string description: ""
  property string errorMessage: ""
  property var tokens: []
  property var recognitions: []
  property var account: ({ projects: [], sections: [], labels: [], collaborators: ({}) })
  property string accountNote: ""
  property var completion: null
  property int completionIndex: -1
  // Where the field has scrolled its text to. The field scrolls itself when the text outgrows the box;
  // the coloured layer and the tints must follow, and positionToRectangle() does not notify.
  property real textOriginX: 0

  // Settings replace the task field in the same card (Ctrl+,). The token only ever lives in tokenDraft
  // until it is written to the helper's stdin; it is never in a command line, a log or the IPC state.
  property bool settingsOpen: false
  property string tokenDraft: ""
  property string tokenSource: ""
  property bool tokenOk: false
  property string tokenError: ""
  property bool tokenChecking: false
  property bool tokenSaving: false
  readonly property bool tokenBusy: root.tokenChecking || root.tokenSaving
  readonly property string tokenLine: {
    if (root.tokenBusy)
      return "Checking with Todoist…"
    if (root.tokenSource.length === 0)
      return "No token yet. In Todoist open Settings, Integrations, Developer, copy your API token and paste it here."
    var names = {
      "environment": "TODOIST_API_TOKEN from your environment",
      "saved": "the token saved by Quick Task",
      "tod.cfg": "the token in your tod.cfg"
    }
    return "Using " + (names[root.tokenSource] || root.tokenSource) + (root.tokenOk ? ", accepted by Todoist." : ".")
  }

  function syncTextOrigin() {
    root.textOriginX = keyCatcher.positionToRectangle(0).x
  }

  readonly property string helperScript:
    Qt.resolvedUrl("helper/quick-task").toString().replace(/^file:\/\//, "")
  // -B: never write __pycache__ into the plugin folder. The shell watches that folder and reloads the
  // plugin on any change, which closes the overlay under the user's hands.
  readonly property var helperCommand: ["/usr/bin/python3", "-I", "-B", root.helperScript]
  property string omarchyPath: Quickshell.env("OMARCHY_PATH") || "/usr/share/omarchy"
  readonly property string fontFamily: Style.font.menuFamily
  readonly property int cornerRadius: Style.cornerRadius
  readonly property int contentPadding: Style.spacing.panelPadding
  readonly property bool hasDraft: root.draft.trim().length > 0
  readonly property color background: Color.menu.background
  readonly property color foreground: Color.menu.text
  readonly property color border: Color.menu.border
  readonly property color scrim: Color.menu.scrim
  readonly property var borderSpec: Border.surfaceSpec(
    "menu", "border", root.border, Math.max(Style.spacing.hairline, Style.space(1)))
  readonly property int cardWidth: Math.min(Style.space(640), panel.width - Style.gapsOut * 2)
  readonly property int cardHeight: Math.min(
    (root.settingsOpen ? settingsColumn.implicitHeight : contentColumn.implicitHeight) + root.contentPadding * 2,
    panel.height - Style.gapsOut * 2)

  function open(payloadJson) {
    var payload = ({})
    try { payload = JSON.parse(payloadJson || "{}") } catch (e) { payload = ({}) }
    root.draft = String(payload.text || "")
    root.description = String(payload.description || "")
    root.errorMessage = ""
    root.tokens = []
    root.recognitions = []
    root.showDescription = root.description.length > 0
    root.showSyntax = false
    root.submitting = false
    root.settingsOpen = false
    root.tokenDraft = ""
    root.completion = null
    root.completionIndex = -1
    root.opened = true
    root.loadAccount()
    parseTimer.restart()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.opened = false
  }

  function dismiss() {
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "io.github.danitrrga.quick-task")
  }

  function toggle() {
    if (root.opened) root.dismiss()
    else root.open("{}")
  }

  function openSettings() {
    root.settingsOpen = true
    root.tokenDraft = ""
    root.tokenError = ""
    root.completion = null
    root.completionIndex = -1
    root.refreshTokenStatus()
    Qt.callLater(function() { tokenField.forceActiveFocus() })
  }

  function closeSettings() {
    root.settingsOpen = false
    root.tokenDraft = ""
    root.tokenError = ""
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function toggleSettings() {
    if (root.settingsOpen) root.closeSettings()
    else root.openSettings()
  }

  function refreshTokenStatus() {
    if (tokenStatusProc.running) return
    root.tokenChecking = true
    tokenStatusProc.running = true
  }

  function handleTokenStatus(output) {
    var parsed
    try { parsed = JSON.parse(output || "") } catch (e) { parsed = null }
    root.tokenChecking = false
    if (!parsed) {
      root.tokenOk = false
      root.tokenError = "Quick Task could not read its helper’s answer."
      return
    }
    root.tokenSource = parsed.source ? String(parsed.source) : ""
    root.tokenOk = parsed.ok === true
    root.tokenError = parsed.ok || !root.tokenSource ? "" : String(parsed.error || "")
  }

  function saveToken() {
    var value = root.tokenDraft.trim()
    if (value.length === 0 || root.tokenBusy) return
    root.tokenError = ""
    root.tokenSaving = true
    tokenSetProc.pendingInput = value
    tokenSetProc.running = true
  }

  function handleTokenSet(output) {
    var parsed
    try { parsed = JSON.parse(output || "") } catch (e) {
      parsed = { ok: false, error: "Quick Task could not read its helper’s answer." }
    }
    root.tokenSaving = false
    if (!parsed.ok) {
      root.tokenError = String(parsed.error || "Todoist did not accept the token.")
      Qt.callLater(function() { tokenField.forceActiveFocus() })
      return
    }
    root.tokenDraft = ""
    root.tokenSource = String(parsed.source || "")
    if (root.tokenSource === "environment") {
      // The saved token is kept, but the variable in the user's shell still wins: say so, stay here.
      root.tokenOk = true
      root.tokenError = "Saved. TODOIST_API_TOKEN is set in your environment and is still the one in use."
      return
    }
    root.errorMessage = ""
    root.accountNote = ""
    root.closeSettings()
    if (!syncProc.running) syncProc.running = true
  }

  function forgetToken() {
    if (tokenClearProc.running || root.tokenBusy) return
    root.tokenError = ""
    tokenClearProc.running = true
  }

  function parsePayload() {
    return JSON.stringify({ text: root.draft })
  }

  function requestParse() {
    if (!root.opened) return
    if (!root.draft) {
      root.tokens = []
      root.recognitions = []
      root.parseQueued = false
      return
    }
    if (parseProc.running) {
      root.parseQueued = true
      return
    }
    root.parseQueued = false
    parseProc.pendingInput = root.parsePayload()
    parseProc.running = true
  }

  function handleParseResult(output) {
    var parsed
    try { parsed = JSON.parse(output || "") } catch (e) { return }
    if (parsed && parsed.ok && parsed.result
        && String(parsed.result.original) === root.draft
        && Array.isArray(parsed.result.tokens)
        && Array.isArray(parsed.result.recognitions)) {
      root.tokens = parsed.result.tokens
      root.recognitions = parsed.result.recognitions
    }
  }

  function loadAccount() {
    if (accountProc.running || syncProc.running) return
    accountProc.running = true
  }

  function handleAccountResult(output, fromSync) {
    var parsed
    try { parsed = JSON.parse(output || "") } catch (e) { parsed = null }
    if (parsed && parsed.ok && parsed.account) {
      root.account = parsed.account
      if (fromSync) root.accountNote = ""
      else if (parsed.account.stale && !syncProc.running) syncProc.running = true
      return
    }
    if (fromSync) {
      var known = root.account.projects.length > 0
      root.accountNote = (parsed && parsed.error ? String(parsed.error) : "Could not refresh your Todoist data.")
        + (known ? " Autocomplete may be out of date." : " Autocomplete is off.")
    }
  }

  // Everything that follows a change the user typed; the IPC `type` hook calls it too.
  function edited(text, cursor) {
    var old = root.draft
    var atEnd = old.length > 0 && (text.indexOf(old) === 0 || old.indexOf(text) === 0)
    root.draft = text
    if (atEnd) {
      // Typing or deleting at the end leaves earlier words where they were: keep their colour until
      // the new reading arrives, instead of flashing them back to plain text.
      var limit = Math.min(old.length, text.length)
      root.tokens = root.tokens.filter(function(token) { return token.end <= limit })
      root.recognitions = root.recognitions.filter(function(token) { return token.end <= limit })
    } else {
      root.tokens = []
      root.recognitions = []
    }
    root.errorMessage = ""
    root.refreshCompletion(cursor)
    parseTimer.restart()
  }

  function refreshCompletion(cursor) {
    var next = QuickTaskLogic.completionAt(root.draft, cursor, root.account)
    root.completion = next
    root.completionIndex = next && !next.soft ? 0 : -1
  }

  function applyCompletionItem(item) {
    var picker = root.completion
    if (!picker || !item) return
    var result = QuickTaskLogic.applyCompletion(root.draft, picker, item)
    root.completion = null
    root.completionIndex = -1
    root.draft = result.text
    root.tokens = []
    root.recognitions = []
    parseTimer.restart()
    Qt.callLater(function() {
      keyCatcher.cursorPosition = result.cursor
      keyCatcher.forceActiveFocus()
    })
  }

  // One key path for the real input and for the IPC test hooks. Returns true when it consumed the key.
  function handleKey(key, modifiers) {
    if ((modifiers & Qt.ControlModifier) && key === Qt.Key_Comma) {
      root.toggleSettings()
      return true
    }
    if (root.settingsOpen) {
      if (key === Qt.Key_Escape) {
        root.closeSettings()
        return true
      }
      return false
    }
    var picker = root.completion
    var plain = !(modifiers & Qt.ShiftModifier)
    if (key === Qt.Key_Backspace) {
      var token = QuickTaskLogic.tokenEndingAt(
        root.visibleTokens,
        keyCatcher.cursorPosition,
        keyCatcher.selectionStart,
        keyCatcher.selectionEnd)
      if (token) {
        root.literalizeToken(token)
        return true
      }
      return false
    }
    if (picker) {
      var last = picker.items.length - 1
      if (key === Qt.Key_Escape) {
        root.completion = null
        root.completionIndex = -1
        return true
      }
      if (key === Qt.Key_Down && plain) {
        root.completionIndex = Math.min(root.completionIndex + 1, last)
        return true
      }
      if (key === Qt.Key_Up) {
        root.completionIndex = Math.max(root.completionIndex - 1, picker.soft ? -1 : 0)
        return true
      }
      if (key === Qt.Key_Tab
          || (root.completionIndex >= 0 && (key === Qt.Key_Return || key === Qt.Key_Enter))) {
        root.applyCompletionItem(picker.items[Math.max(root.completionIndex, 0)])
        return true
      }
    }
    if (key === Qt.Key_Escape) {
      root.dismiss()
      return true
    }
    if (key === Qt.Key_Down) {
      if (modifiers & Qt.ShiftModifier) {
        root.showSyntax = !root.showSyntax
      } else {
        root.showDescription = true
        Qt.callLater(function() { descriptionField.forceActiveFocus() })
      }
      return true
    }
    return false
  }

  function submit() {
    if (root.submitting) return
    if (!root.draft.trim()) {
      root.errorMessage = "Type a task before adding it."
      return
    }
    root.errorMessage = ""
    root.submitting = true
    addProc.pendingInput = JSON.stringify({
      text: root.draft,
      description: root.description
    })
    addProc.running = true
  }

  function handleAddResult(output) {
    var parsed
    try { parsed = JSON.parse(output || "") } catch (e) {
      parsed = { ok: false, error: "Quick Task could not read Todoist’s response." }
    }
    root.submitting = false
    if (!parsed.ok) {
      root.errorMessage = String(parsed.error || "Todoist did not accept the task.")
      Qt.callLater(function() { keyCatcher.forceActiveFocus() })
      return
    }
    root.draft = ""
    root.description = ""
    root.tokens = []
    root.recognitions = []
    root.dismiss()
    Quickshell.execDetached([
      root.omarchyPath + "/bin/omarchy-notification-send",
      "Task added to Todoist"
    ])
  }

  function literalizeToken(token) {
    var cursor = keyCatcher.cursorPosition
    var recognized = root.recognitions
    root.draft = QuickTaskLogic.literalizeKind(root.draft, recognized, token.kind)
    root.tokens = QuickTaskLogic.withoutToken(root.tokens, token.id)
    root.recognitions = recognized.filter(function(item) { return item.kind !== token.kind })
    parseTimer.restart()
    Qt.callLater(function() {
      keyCatcher.cursorPosition = QuickTaskLogic.cursorAfterLiteralizingKind(
        cursor, recognized, token.kind)
      keyCatcher.forceActiveFocus()
    })
  }

  function syntaxColor(kind) {
    switch (kind) {
    case "date": return Color.accent
    case "project": return Color.menu.selectedText
    case "section": return Color.popups.border
    case "label": return Color.notifications.countdown
    case "assignee": return Color.foreground
    case "reminder": return Color.polkit.accent
    case "priority": return Color.urgent
    case "deadline": return Color.lock.borderActive
    default: return Color.accent
    }
  }

  readonly property var visibleTokens: root.tokens

  // "synced 10:07", as the agenda's footer says it. Silent while a failed sync is explained elsewhere.
  readonly property string syncStatus: {
    if (root.accountNote.length > 0)
      return ""
    var at = root.account.fetched_at
    return at ? "synced " + Qt.formatDateTime(new Date(at * 1000), "HH:mm") : ""
  }

  function hex(color) {
    function part(value) {
      var digits = Math.round(value * 255).toString(16)
      return digits.length < 2 ? "0" + digits : digits
    }
    return "#" + part(color.r) + part(color.g) + part(color.b)
  }

  // A word that is not in the account reads as plain text, which is what Todoist will make of it.
  function tokenColor(mark) {
    return mark.known === false ? root.hex(Color.muted) : root.hex(root.syntaxColor(mark.kind))
  }

  readonly property string styledDraft:
    QuickTaskLogic.styledDraft(root.draft, root.visibleTokens, root.tokenColor, root.hex(root.foreground))

  Timer {
    id: parseTimer
    interval: 140
    repeat: false
    onTriggered: root.requestParse()
  }

  Process {
    id: parseProc
    property string pendingInput: ""
    stdinEnabled: true
    command: root.helperCommand.concat(["parse"])
    onStarted: {
      write(pendingInput + "\n")
      pendingInput = ""
    }
    onRunningChanged: {
      if (!running && root.parseQueued) Qt.callLater(root.requestParse)
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handleParseResult(text)
    }
  }

  Process {
    id: addProc
    property string pendingInput: ""
    stdinEnabled: true
    command: root.helperCommand.concat(["add"])
    onStarted: {
      write(pendingInput + "\n")
      pendingInput = ""
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handleAddResult(text)
    }
  }

  Process {
    id: accountProc
    command: root.helperCommand.concat(["account"])
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handleAccountResult(text, false)
    }
  }

  Process {
    id: syncProc
    command: root.helperCommand.concat(["sync"])
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handleAccountResult(text, true)
    }
  }

  Process {
    id: tokenStatusProc
    command: root.helperCommand.concat(["token", "status", "--json"])
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handleTokenStatus(text)
    }
  }

  Process {
    id: tokenSetProc
    property string pendingInput: ""
    stdinEnabled: true
    command: root.helperCommand.concat(["token", "set", "--json"])
    onStarted: {
      write(pendingInput + "\n")
      pendingInput = ""
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handleTokenSet(text)
    }
  }
  // end tokenSetProc

  Process {
    id: tokenClearProc
    command: root.helperCommand.concat(["token", "clear", "--json"])
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.refreshTokenStatus()
    }
  }

  Timer {
    interval: 12000
    running: tokenSetProc.running || tokenStatusProc.running
    onTriggered: {
      tokenSetProc.running = false
      tokenStatusProc.running = false
      root.tokenSaving = false
      root.tokenChecking = false
      root.tokenError = "Todoist did not respond. Nothing was saved."
    }
  }

  // A sync that hangs must not block the next one: a Process that is still running cannot be relaunched.
  Timer {
    interval: 15000
    running: syncProc.running
    onTriggered: syncProc.running = false
  }

  Timer {
    interval: 12000
    running: addProc.running
    onTriggered: {
      addProc.running = false
      root.submitting = false
      root.errorMessage = "Todoist did not respond. Your task is still here."
    }
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; right: true; bottom: true; left: true }
    color: "transparent"
    WlrLayershell.namespace: "quick-task"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    BorderSurface {
      id: card
      width: root.cardWidth
      height: root.cardHeight
      anchors.horizontalCenter: parent.horizontalCenter
      y: Math.max(Style.gapsOut, Math.round((parent.height - height) * 0.28))
      color: root.background
      borderSpec: root.borderSpec
      radius: root.cornerRadius
      padding: root.contentPadding

      MouseArea { anchors.fill: parent; onClicked: {} }

      Column {
        id: contentColumn
        visible: !root.settingsOpen
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: card.contentTopInset
        anchors.leftMargin: card.contentLeftInset
        anchors.rightMargin: card.contentRightInset
        spacing: Style.spacing.controlGap

        Item {
          id: inputSurface
          width: parent.width
          height: Math.max(Style.space(46), keyCatcher.implicitHeight)
          clip: true

          // The words are drawn here, each recognised one in its own colour; the field above is
          // transparent and only supplies the caret and the selection.
          Text {
            id: coloredDraft
            x: root.textOriginX
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.StyledText
            text: root.styledDraft
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            font.weight: Font.Medium
          }

          TextInput {
            id: keyCatcher
            anchors.fill: parent
            text: root.draft
            enabled: !root.submitting
            color: "transparent"
            selectionColor: Style.selectionFillFor(root.foreground, Color.accent)
            selectedTextColor: "transparent"
            // The text is drawn by the layer under this field, so the default caret (which takes the
            // transparent text colour) would show only a stub. Draw it: full line height, theme colour.
            cursorDelegate: Rectangle {
              width: Math.max(1, Style.space(2))
              height: keyCatcher.cursorRectangle.height
              color: root.foreground
            }
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            font.weight: Font.Medium
            leftPadding: Style.spacing.xs
            rightPadding: Style.spacing.xs
            topPadding: 0
            bottomPadding: 0
            selectByMouse: true
            verticalAlignment: TextInput.AlignVCenter
            clip: true

            onTextEdited: root.edited(text, keyCatcher.cursorPosition)
            onContentWidthChanged: Qt.callLater(root.syncTextOrigin)
            onCursorRectangleChanged: Qt.callLater(root.syncTextOrigin)
            onWidthChanged: Qt.callLater(root.syncTextOrigin)
            onCursorPositionChanged: {
              if (root.completion && keyCatcher.cursorPosition !== root.completion.end) {
                root.completion = null
                root.completionIndex = -1
              }
            }
            onAccepted: root.submit()
            Keys.onPressed: function(event) {
              if (root.handleKey(event.key, event.modifiers))
                event.accepted = true
            }
          }

          Text {
            anchors.left: parent.left
            anchors.leftMargin: Style.spacing.xs
            anchors.verticalCenter: parent.verticalCenter
            z: 3
            visible: !root.hasDraft
            text: "What needs doing?"
            color: Color.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            font.weight: Font.Medium
          }
        }

        Column {
          id: suggestionList
          width: parent.width
          visible: root.completion !== null
          spacing: Style.space(1)

          Rectangle {
            width: parent.width
            height: Math.max(1, Style.spacing.hairline)
            color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.14)
          }

          Repeater {
            model: root.completion ? root.completion.items : []

            delegate: Item {
              required property var modelData
              required property int index
              readonly property bool current: index === root.completionIndex
              width: suggestionList.width
              height: Style.space(26)

              Text {
                anchors.left: parent.left
                anchors.leftMargin: Style.spacing.xs
                anchors.right: detailText.left
                anchors.rightMargin: Style.spacing.sm
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: parent.current ? Color.accent : root.foreground
                opacity: parent.current ? 1 : 0.8
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.weight: parent.current ? Font.DemiBold : Font.Normal
              }

              Text {
                id: detailText
                anchors.right: parent.right
                anchors.rightMargin: Style.spacing.xs
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, parent.width * 0.4)
                text: modelData.detail
                textFormat: Text.PlainText
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignRight
                color: Color.muted
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onEntered: root.completionIndex = index
                onClicked: root.applyCompletionItem(modelData)
              }
            }
          }
        }

        Flow {
          id: metaFlow
          width: parent.width
          leftPadding: Style.spacing.xs
          rightPadding: Style.spacing.xs
          visible: root.completion === null && root.visibleTokens.length > 0

          Repeater {
            model: QuickTaskLogic.metaParts(root.visibleTokens, root.account)

            delegate: Row {
              required property var modelData
              readonly property bool unusable: modelData.note.length > 0

              Text {
                visible: modelData.separator.length > 0
                text: "  " + modelData.separator + "  "
                textFormat: Text.PlainText
                color: Color.muted
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                text: unusable ? modelData.text + " (" + modelData.note + ")" : modelData.text
                textFormat: Text.PlainText
                color: unusable ? Color.muted : root.syntaxColor(modelData.kind)
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                font.strikeout: modelData.note === "not found"

                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.literalizeToken(modelData.token)
                }
              }
            }
          }
        }

        QQC.TextField {
          id: descriptionField
          width: parent.width
          height: root.showDescription ? implicitHeight : 0
          visible: root.showDescription
          text: root.description
          enabled: !root.submitting
          placeholderText: "Description"
          color: root.foreground
          placeholderTextColor: Color.muted
          selectionColor: Style.selectionFillFor(root.foreground, Color.accent)
          selectedTextColor: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          leftPadding: Style.spacing.xs
          rightPadding: Style.spacing.xs
          topPadding: Style.spacing.inputPaddingY
          bottomPadding: Style.spacing.inputPaddingY
          background: Item {
            Rectangle {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.bottom: parent.bottom
              height: Math.max(1, Style.spacing.hairline)
              color: descriptionField.activeFocus
                ? Color.accent
                : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.2)
            }
          }
          onTextEdited: root.description = text
          onAccepted: root.submit()
          Keys.onEscapePressed: root.dismiss()
        }

        Item {
          width: parent.width
          height: root.showSyntax ? syntaxText.implicitHeight + Style.space(10) : 0
          visible: root.showSyntax

          Text {
            id: syntaxText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Style.spacing.xs
            anchors.rightMargin: Style.spacing.xs
            text: "# Project  ·  / Section  ·  % Label  ·  p1 Priority  ·  + Assignee  ·  ! Reminder  ·  {date} Deadline"
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Color.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Item {
          width: parent.width
          height: root.errorMessage ? errorText.implicitHeight + Style.space(10) : 0
          visible: root.errorMessage.length > 0

          Text {
            id: errorText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Style.spacing.xs
            anchors.rightMargin: Style.spacing.xs
            text: root.errorMessage
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Color.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }
        }

        Item {
          width: parent.width
          height: visible ? noteText.implicitHeight + Style.space(10) : 0
          visible: root.accountNote.length > 0 && root.completion === null

          Text {
            id: noteText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Style.spacing.xs
            anchors.rightMargin: Style.spacing.xs
            text: root.accountNote
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Color.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Item {
          id: actionRow
          width: parent.width
          height: visible ? footer.implicitHeight : 0
          visible: root.hasDraft || root.showDescription || root.showSyntax || root.errorMessage.length > 0

          Column {
            id: footer
            width: parent.width
            spacing: Style.space(8)

            Rectangle {
              width: parent.width
              height: Math.max(1, Style.spacing.hairline)
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.14)
            }

            Item {
              width: parent.width
              height: Math.max(statusText.implicitHeight, hints.implicitHeight)

              Text {
                id: statusText
                anchors.left: parent.left
                anchors.leftMargin: Style.spacing.xs
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: root.syncStatus
                color: Color.muted
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Row {
                id: hints
                anchors.right: parent.right
                anchors.rightMargin: Style.spacing.xs
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(10)

                KeyHint {
                  visible: root.completion !== null
                  key: "↑ ↓"
                  label: "move"
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  interactive: false
                }

                KeyHint {
                  visible: root.completion === null
                  key: "↓"
                  label: "note"
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  onClicked: {
                    root.showDescription = true
                    descriptionField.forceActiveFocus()
                  }
                }

                KeyHint {
                  visible: root.completion === null
                  key: "⇧ ↓"
                  label: root.showSyntax ? "hide syntax" : "syntax"
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  onClicked: root.showSyntax = !root.showSyntax
                }

                KeyHint {
                  visible: root.completion === null
                  key: "ctrl ,"
                  label: "token"
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  onClicked: root.openSettings()
                }

                KeyHint {
                  key: "esc"
                  label: "close"
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  onClicked: root.dismiss()
                }

                KeyHint {
                  key: "enter"
                  label: root.completion !== null && root.completionIndex >= 0
                    ? "choose" : (root.submitting ? "adding…" : "add")
                  accent: true
                  enabled: root.hasDraft && !root.submitting
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  onClicked: {
                    if (root.completion !== null && root.completionIndex >= 0)
                      root.applyCompletionItem(root.completion.items[root.completionIndex])
                    else
                      root.submit()
                  }
                }
              }
            }
          }
        }
      }

      Column {
        id: settingsColumn
        visible: root.settingsOpen
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: card.contentTopInset
        anchors.leftMargin: card.contentLeftInset
        anchors.rightMargin: card.contentRightInset
        spacing: Style.spacing.controlGap

        Text {
          width: parent.width
          leftPadding: Style.spacing.xs
          text: "Todoist token"
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.heading
          font.weight: Font.Medium
        }

        Text {
          width: parent.width
          leftPadding: Style.spacing.xs
          rightPadding: Style.spacing.xs
          text: root.tokenLine
          textFormat: Text.PlainText
          wrapMode: Text.Wrap
          color: Color.muted
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        QQC.TextField {
          id: tokenField
          width: parent.width
          text: root.tokenDraft
          enabled: !root.tokenSaving
          echoMode: TextInput.Password
          placeholderText: "Paste your API token"
          color: root.foreground
          placeholderTextColor: Color.muted
          selectionColor: Style.selectionFillFor(root.foreground, Color.accent)
          selectedTextColor: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          leftPadding: Style.spacing.xs
          rightPadding: Style.spacing.xs
          topPadding: Style.spacing.inputPaddingY
          bottomPadding: Style.spacing.inputPaddingY
          background: Item {
            Rectangle {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.bottom: parent.bottom
              height: Math.max(1, Style.spacing.hairline)
              color: tokenField.activeFocus
                ? Color.accent
                : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.2)
            }
          }
          onTextEdited: root.tokenDraft = text
          onAccepted: root.saveToken()
          Keys.onEscapePressed: root.closeSettings()
          Keys.onPressed: function(event) {
            if (root.handleKey(event.key, event.modifiers))
              event.accepted = true
          }
        }
        // end tokenField

        Text {
          width: parent.width
          visible: root.tokenError.length > 0
          leftPadding: Style.spacing.xs
          rightPadding: Style.spacing.xs
          text: root.tokenError
          textFormat: Text.PlainText
          wrapMode: Text.Wrap
          color: root.tokenError.indexOf("Saved.") === 0 ? Color.muted : Color.urgent
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Rectangle {
          width: parent.width
          height: Math.max(1, Style.spacing.hairline)
          color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.14)
        }

        Item {
          width: parent.width
          height: Math.max(forgetText.implicitHeight, settingsHints.implicitHeight)

          Text {
            id: forgetText
            anchors.left: parent.left
            anchors.leftMargin: Style.spacing.xs
            anchors.verticalCenter: parent.verticalCenter
            visible: root.tokenSource === "saved"
            text: "forget saved token"
            textFormat: Text.PlainText
            color: forgetMouse.containsMouse ? Color.urgent : Color.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption

            MouseArea {
              id: forgetMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.forgetToken()
            }
          }

          Row {
            id: settingsHints
            anchors.right: parent.right
            anchors.rightMargin: Style.spacing.xs
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(10)

            KeyHint {
              key: "esc"
              label: "back"
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.closeSettings()
            }

            KeyHint {
              key: "enter"
              label: root.tokenSaving ? "checking…" : "save"
              accent: true
              enabled: root.tokenDraft.trim().length > 0 && !root.tokenBusy
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.saveToken()
            }
          }
        }
      }
    }
  }

  IpcHandler {
    target: "io.github.danitrrga.quick-task"

    function open(): void { root.open("{}") }
    function close(): void { root.dismiss() }
    function loadAccountJson(json: string): void { root.account = JSON.parse(json) }

    // Drives the same functions a key press and a typed character call.
    function type(text: string): void {
      root.edited(text, text.length)
      Qt.callLater(function() { keyCatcher.cursorPosition = text.length })
    }
    function key(name: string): void {
      var keys = {
        down: Qt.Key_Down, up: Qt.Key_Up, tab: Qt.Key_Tab, enter: Qt.Key_Return,
        escape: Qt.Key_Escape, backspace: Qt.Key_Backspace
      }
      if (name === "ctrl_comma") root.handleKey(Qt.Key_Comma, Qt.ControlModifier)
      else root.handleKey(keys[name], 0)
    }
    function settings(on: bool): void { if (on !== root.settingsOpen) root.toggleSettings() }
    // Test hooks for the token form. The value goes through an argument, so only use a throwaway one.
    function tokenType(text: string): void { root.tokenDraft = text }
    function saveToken(): void { root.saveToken() }
    function forgetToken(): void { root.forgetToken() }
    function submit(): void { root.submit() }
    function pick(index: int): void {
      if (root.completion) root.applyCompletionItem(root.completion.items[index])
    }

    // What the overlay computed and shows. Never the token.
    function state(): string {
      return JSON.stringify({
        opened: root.opened,
        draft: root.draft,
        cursor: keyCatcher.cursorPosition,
        completion: root.completion ? {
          kind: root.completion.kind,
          soft: root.completion.soft,
          index: root.completionIndex,
          items: root.completion.items.map(function(item) { return item.label })
        } : null,
        marks: root.tokens.map(function(mark) {
          var note = QuickTaskLogic.chipNote(mark, root.account)
          return mark.kind + ":" + mark.text + (note ? " (" + note + ")" : "")
        }),
        accountProjects: root.account.projects.length,
        accountPremium: root.account.premium === true,
        accountNote: root.accountNote,
        submitting: root.submitting,
        error: root.errorMessage,
        settingsOpen: root.settingsOpen,
        tokenSource: root.tokenSource,
        tokenOk: root.tokenOk,
        tokenLine: root.tokenLine,
        tokenError: root.tokenError,
        tokenBusy: root.tokenBusy,
        tokenDraft: root.tokenDraft.length
      })
    }
  }
}
