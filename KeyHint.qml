import QtQuick 6.11
import qs.Commons

// A keycap and the word beside it, one button, written once (the agenda panel's footer does the same).
Item {
  id: root

  property string key: ""
  property string label: ""
  property color foreground: Color.foreground
  property color dim: Color.muted
  property bool accent: false
  property bool interactive: true
  property string fontFamily: Style.font.family
  signal clicked()

  implicitWidth: row.implicitWidth
  implicitHeight: row.implicitHeight
  opacity: !enabled ? 0.45 : (mouse.containsMouse ? 1 : 0.9)

  Row {
    id: row
    spacing: Style.space(4)

    KeyCap {
      label: root.key
      foreground: root.accent ? Color.accent : root.foreground
      fontFamily: root.fontFamily
    }

    Text {
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: root.label
      color: root.accent ? Color.accent : root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  MouseArea {
    id: mouse
    anchors.fill: parent
    hoverEnabled: true
    enabled: root.enabled && root.interactive
    cursorShape: Qt.PointingHandCursor
    onClicked: root.clicked()
  }
}
