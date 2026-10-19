import QtQuick 6.11
import qs.Commons

// A key and the word beside it, one button, written once. The key is an underlined word, the way a
// link is set in an editorial layout: no box, no glyph the font may not have.
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
  opacity: !enabled ? 0.45 : (mouse.containsMouse ? 1 : 0.92)

  Row {
    id: row
    spacing: Style.space(4)

    Text {
      textFormat: Text.PlainText
      text: root.key
      color: root.accent ? Color.accent : root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      font.underline: true
    }

    Text {
      textFormat: Text.PlainText
      text: root.label
      color: root.dim
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
