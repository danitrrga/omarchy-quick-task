import QtQuick
import QtQuick.Controls as QQC
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui

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
  property var ignoredTokenIds: []

  readonly property string helperPath: Quickshell.env("HOME") + "/.local/bin/quick-task"
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
    contentColumn.implicitHeight + root.contentPadding * 2,
    panel.height - Style.gapsOut * 2)

  function open(payloadJson) {
    var payload = ({})
    try { payload = JSON.parse(payloadJson || "{}") } catch (e) { payload = ({}) }
    root.draft = String(payload.text || "")
    root.description = String(payload.description || "")
    root.errorMessage = ""
    root.tokens = []
    root.ignoredTokenIds = []
    root.showDescription = root.description.length > 0
    root.showSyntax = false
    root.submitting = false
    root.opened = true
    parseTimer.restart()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.opened = false
  }

  function dismiss() {
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "danitrrga.quick-task")
  }

  function toggle() {
    if (root.opened) root.dismiss()
    else root.open("{}")
  }

  function parsePayload() {
    return JSON.stringify({
      text: root.draft,
      ignored: root.ignoredTokenIds
    })
  }

  function requestParse() {
    if (!root.opened) return
    if (!root.draft) {
      root.tokens = []
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
        && Array.isArray(parsed.result.tokens))
      root.tokens = parsed.result.tokens
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
      description: root.description,
      ignored: root.ignoredTokenIds
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
    var taskName = root.draft
    root.draft = ""
    root.description = ""
    root.tokens = []
    root.ignoredTokenIds = []
    root.dismiss()
    Quickshell.execDetached([
      root.omarchyPath + "/bin/omarchy-notification-send",
      "Task added",
      taskName
    ])
  }

  function ignoreToken(tokenId) {
    if (root.ignoredTokenIds.indexOf(tokenId) !== -1) return
    root.ignoredTokenIds = root.ignoredTokenIds.concat([tokenId])
    root.requestParse()
  }

  readonly property var visibleTokens: root.tokens

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
    command: [root.helperPath, "parse"]
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
    command: [root.helperPath, "add"]
    onStarted: {
      write(pendingInput + "\n")
      pendingInput = ""
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.handleAddResult(text)
    }
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
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: card.contentTopInset
        anchors.leftMargin: card.contentLeftInset
        anchors.rightMargin: card.contentRightInset
        spacing: Style.spacing.controlGap

        Item {
          width: parent.width
          height: Math.max(Style.space(46), keyCatcher.implicitHeight)

          QQC.TextField {
            id: keyCatcher
            anchors.fill: parent
            text: root.draft
            enabled: !root.submitting
            placeholderText: "What needs doing?"
            color: root.foreground
            placeholderTextColor: Color.muted
            selectionColor: Style.selectionFillFor(root.foreground, Color.accent)
            selectedTextColor: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            font.weight: Font.Medium
            leftPadding: Style.spacing.xs
            rightPadding: Style.spacing.xs
            topPadding: 0
            bottomPadding: 0
            selectByMouse: true
            background: Item {}

            onTextEdited: {
              root.ignoredTokenIds = []
              root.draft = text
              root.tokens = []
              root.errorMessage = ""
              parseTimer.restart()
            }
            onAccepted: root.submit()
            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Escape) {
                root.dismiss()
                event.accepted = true
              } else if (event.key === Qt.Key_Down) {
                if (event.modifiers & Qt.ShiftModifier) {
                  root.showSyntax = !root.showSyntax
                } else {
                  root.showDescription = true
                  Qt.callLater(function() { descriptionField.forceActiveFocus() })
                }
                event.accepted = true
              }
            }
          }
        }

        Grid {
          id: tokenGrid
          width: parent.width
          visible: root.visibleTokens.length > 0
          columns: Math.max(1, Math.min(4, root.visibleTokens.length))
          columnSpacing: Style.spacing.sm
          rowSpacing: Style.spacing.sm

          Repeater {
            model: root.visibleTokens

            delegate: BorderSurface {
              required property var modelData
              readonly property real columnWidth: (
                tokenGrid.width - tokenGrid.columnSpacing * (tokenGrid.columns - 1)
              ) / tokenGrid.columns
              width: Math.min(
                tokenLabel.implicitWidth + Style.spacing.controlPaddingX * 2,
                columnWidth)
              height: Style.spacing.controlHeight
              radius: root.cornerRadius
              color: modelData.kind === "date"
                ? Color.menu.selectedBackground
                : Style.normalFillFor(root.foreground, Color.accent)
              borderSpec: Border.none()

              Text {
                id: tokenLabel
                anchors.centerIn: parent
                width: parent.width - Style.spacing.controlPaddingX * 2
                text: modelData.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                color: modelData.kind === "date" ? Color.menu.selectedText : root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              MouseArea {
                anchors.fill: parent
                enabled: modelData.kind === "date"
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: root.ignoreToken(modelData.id)
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
          leftPadding: Style.spacing.controlPaddingX
          rightPadding: Style.spacing.controlPaddingX
          topPadding: Style.spacing.inputPaddingY
          bottomPadding: Style.spacing.inputPaddingY
          background: BorderSurface {
            color: Style.controlFill(
              descriptionField.activeFocus, descriptionField.hovered, root.foreground, Color.accent)
            borderSpec: Border.controlSpec(
              descriptionField.activeFocus ? "focus" : (descriptionField.hovered ? "hover-cursor" : "normal"),
              root.foreground,
              Color.accent)
            radius: root.cornerRadius
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
          id: actionRow
          width: parent.width
          height: visible ? Math.max(leftActions.implicitHeight, addButton.implicitHeight) : 0
          visible: root.hasDraft || root.showDescription || root.showSyntax || root.errorMessage.length > 0

          Row {
            id: leftActions
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.spacing.xs

            Button {
              visible: root.hasDraft
              text: "Description"
              foreground: root.foreground
              background: "transparent"
              fontFamily: root.fontFamily
              fontSize: Style.font.bodySmall
              horizontalPadding: Style.spacing.sm
              verticalPadding: Style.spacing.sm
              onClicked: {
                root.showDescription = true
                descriptionField.forceActiveFocus()
              }
            }

            Button {
              visible: root.hasDraft
              text: root.showSyntax ? "Hide syntax" : "Syntax"
              foreground: root.foreground
              background: "transparent"
              fontFamily: root.fontFamily
              fontSize: Style.font.bodySmall
              horizontalPadding: Style.spacing.sm
              verticalPadding: Style.spacing.sm
              onClicked: root.showSyntax = !root.showSyntax
            }
          }

          Button {
            id: addButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: root.hasDraft
            enabled: !root.submitting
            text: root.submitting ? "Adding…" : "Add task"
            foreground: Color.menu.selectedText
            background: Color.menu.selectedBackground
            fontFamily: root.fontFamily
            fontSize: Style.font.body
            horizontalPadding: Style.spacing.controlPaddingX
            verticalPadding: Style.spacing.controlPaddingY
            onClicked: root.submit()
          }
        }
      }
    }
  }
}
