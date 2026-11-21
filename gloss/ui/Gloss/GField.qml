import QtQuick
import QtQuick.Templates as T

// 输入框：平时只是一块淡淡的底，没有描边；聚焦时才出现强调色的细边
T.TextField {
    id: control
    property bool flat: false   // 表格里用：平时连底都没有，悬停和聚焦才出现

    implicitHeight: 34
    implicitWidth: 200
    leftPadding: 11
    rightPadding: 11
    font.pixelSize: 13
    color: Theme.text
    selectionColor: Theme.accentSelect
    selectedTextColor: Theme.text
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true
    hoverEnabled: true

    background: Rectangle {
        radius: Theme.radius
        color: control.activeFocus ? Theme.fieldHover
             : control.flat ? (control.hovered ? Theme.field : "transparent")
             : control.hovered ? Theme.fieldHover : Theme.field
        border.width: 1
        border.color: control.activeFocus ? Theme.accent : "transparent"
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }

    Text {
        anchors.fill: parent
        anchors.leftMargin: control.leftPadding
        anchors.rightMargin: control.rightPadding
        verticalAlignment: Text.AlignVCenter
        text: control.placeholderText
        font: control.font
        color: Theme.textFaint
        elide: Text.ElideRight
        visible: control.text === "" && control.preeditText === ""
    }
}
