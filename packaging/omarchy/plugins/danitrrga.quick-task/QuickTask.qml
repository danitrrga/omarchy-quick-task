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
  readonly property string omarchyPath: Quickshell.env("OMARCHY_PATH") || "/usr/share/omarchy"
  readonly property string fontFamily: Style.font.menuFamily
  readonly property int cornerRadius: Style.cornerRadius
  readonly property int contentPadding: Style.spacing.panelPadding
  readonly property color background: Color.menu.background
  readonly property color foreground: Color.menu.text
  readonly property color border: Color.menu.border
  readonly property color scrim: Color.menu.scrim
  readonly property var borderSpec: Border.surfaceSpec(
    "menu", "border", root.border, Math.max(Style.spacing.hairline, Style.space(1)))
  readonly property int cardWidth: Math.min(Style.space(680), panel.width - Style.gapsOut * 2)
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
    if (parsed && parsed.ok && parsed.result && Array.isArray(parsed.result.tokens))
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

  function metadataTokens() {
    var found = []
    var rules = [
      { kind: "project", pattern: /(^|\s)(#[^\s]+)/g, label: "Project" },
      { kind: "label", pattern: /(^|\s)([%@][^\s]+)/g, label: "Label" },
      { kind: "priority", pattern: /(^|\s)(p[1-4])\b/gi, label: "Priority" },
      { kind: "assignee", pattern: /(^|\s)(\+[^\s]+)/g, label: "Assignee" },
      { kind: "deadline", pattern: /(^|\s)(\{[^}]+\})/g, label: "Deadline" }
    ]
    for (var i = 0; i < rules.length; i++) {
      rules[i].pattern.lastIndex = 0
      var match
      while ((match = rules[i].pattern.exec(root.draft)) !== null) {
        found.push({
          id: rules[i].kind + ":" + match.index,
          kind: rules[i].kind,
          text: match[2],
          label: rules[i].label + "  " + match[2]
        })
      }
    }
    return found
  }

  readonly property var visibleTokens: root.tokens.concat(root.metadataTokens())

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
      anchors.centerIn: parent
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
          height: Math.max(Style.space(58), keyCatcher.implicitHeight)

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
            leftPadding: Style.spacing.controlPaddingX
            rightPadding: Style.spacing.controlPaddingX
            topPadding: Style.spacing.inputPaddingY
            bottomPadding: Style.spacing.inputPaddingY
            selectByMouse: true

            background: BorderSurface {
              color: Style.controlFill(
                keyCatcher.activeFocus, keyCatcher.hovered, root.foreground, Color.accent)
              borderSpec: Border.controlSpec(
                keyCatcher.activeFocus ? "focus" : (keyCatcher.hovered ? "hover-cursor" : "normal"),
                root.foreground,
                Color.accent)
              radius: root.cornerRadius
            }

            onTextEdited: {
              root.ignoredTokenIds = []
              root.draft = text
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

        Flow {
          id: tokenFlow
          width: parent.width
          height: visible ? childrenRect.height : 0
          spacing: Style.spacing.sm
          visible: root.visibleTokens.length > 0

          Repeater {
            model: root.visibleTokens

            delegate: BorderSurface {
              required property var modelData
              width: tokenLabel.implicitWidth + Style.spacing.controlPaddingX * 2
              height: Style.spacing.controlHeight
              radius: root.cornerRadius
              color: Color.menu.selectedBackground
              borderSpec: Border.controlSpec("selected", root.foreground, Color.accent)

              Text {
                id: tokenLabel
                anchors.centerIn: parent
                text: modelData.label
                textFormat: Text.PlainText
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
          Keys.onEscapePressed: {
            root.showDescription = false
            keyCatcher.forceActiveFocus()
          }
        }

        BorderSurface {
          width: parent.width
          height: root.showSyntax ? syntaxText.implicitHeight + Style.space(18) : 0
          visible: root.showSyntax
          radius: root.cornerRadius
          color: Color.menu.selectedBackground
          borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)

          Text {
            id: syntaxText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Style.spacing.controlPaddingX
            anchors.rightMargin: Style.spacing.controlPaddingX
            text: "# Project   / Section   % Label   p1 Priority   + Assignee   ! Reminder   {date} Deadline"
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Color.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        BorderSurface {
          width: parent.width
          height: root.errorMessage ? errorText.implicitHeight + Style.space(18) : 0
          visible: root.errorMessage.length > 0
          radius: root.cornerRadius
          color: Color.menu.selectedBackground
          borderSpec: Border.controlSpec("normal", Color.urgent, Color.urgent)

          Text {
            id: errorText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Style.spacing.controlPaddingX
            anchors.rightMargin: Style.spacing.controlPaddingX
            text: root.errorMessage
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Color.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }
        }

        Row {
          width: parent.width
          height: Style.space(34)
          spacing: Style.spacing.sm

          BorderSurface {
            width: descriptionButtonText.implicitWidth + Style.spacing.controlPaddingX * 2
            height: parent.height
            radius: root.cornerRadius
            color: descriptionMouse.containsMouse
              ? Color.menu.selectedBackground : root.background
            borderSpec: Border.controlSpec(
              descriptionMouse.containsMouse ? "hover-cursor" : "normal",
              root.foreground,
              Color.accent)
            Text {
              id: descriptionButtonText
              anchors.centerIn: parent
              text: "↓  Description"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            MouseArea {
              id: descriptionMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                root.showDescription = true
                descriptionField.forceActiveFocus()
              }
            }
          }

          BorderSurface {
            width: syntaxButtonText.implicitWidth + Style.spacing.controlPaddingX * 2
            height: parent.height
            radius: root.cornerRadius
            color: syntaxMouse.containsMouse
              ? Color.menu.selectedBackground : root.background
            borderSpec: Border.controlSpec(
              syntaxMouse.containsMouse ? "hover-cursor" : "normal",
              root.foreground,
              Color.accent)
            Text {
              id: syntaxButtonText
              anchors.centerIn: parent
              text: "Shift + ↓  Syntax"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            MouseArea {
              id: syntaxMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.showSyntax = !root.showSyntax
            }
          }

          Item { width: Math.max(0, parent.width - descriptionButtonText.implicitWidth
            - syntaxButtonText.implicitWidth - addButton.width
            - Style.spacing.controlPaddingX * 4 - parent.spacing * 3); height: 1 }

          BorderSurface {
            id: addButton
            width: addButtonText.implicitWidth + Style.spacing.controlPaddingX * 2
            height: parent.height
            radius: root.cornerRadius
            color: Color.menu.selectedBackground
            borderSpec: Border.controlSpec("selected", root.foreground, Color.accent)

            Rectangle {
              width: Style.space(6)
              height: Style.space(6)
              radius: root.cornerRadius
              color: root.submitting ? Color.accent : Color.menu.selectedText
              anchors.left: parent.left
              anchors.leftMargin: Style.spacing.controlPaddingX
              anchors.verticalCenter: parent.verticalCenter
            }

            Text {
              id: addButtonText
              anchors.centerIn: parent
              text: root.submitting ? "Adding…" : "Enter  Add"
              color: Color.menu.selectedText
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              font.weight: Font.DemiBold
            }

            MouseArea {
              anchors.fill: parent
              enabled: !root.submitting
              cursorShape: Qt.PointingHandCursor
              onClicked: root.submit()
            }
          }
        }
      }
    }
  }
}
