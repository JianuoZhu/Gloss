import QtQuick

// 一行设置项：左边标签（可带一行说明），右边放控件。除了第一行，每行顶上有一条细线。
Item {
    id: root
    property string label: ""
    property string hint: ""
    property int labelWidth: 168
    default property alias content: slot.data

    width: parent ? parent.width : 0
    implicitHeight: Math.max(Theme.rowHeight, slot.childrenRect.height + 14, labels.implicitHeight + 16)

    Rectangle {
        visible: root.y > 1          // 第一行上面不画线
        width: parent.width
        height: 1
        color: Theme.stroke
    }

    Column {
        id: labels
        width: root.labelWidth - 14
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Text {
            width: parent.width
            text: root.label
            font.pixelSize: 13
            color: Theme.text
            wrapMode: Text.Wrap
        }
        Text {
            visible: root.hint !== ""
            width: parent.width
            text: root.hint
            font.pixelSize: 11
            color: Theme.textFaint
            wrapMode: Text.Wrap
        }
    }

    Item {
        id: slot
        x: root.labelWidth
        width: root.width - root.labelWidth
        height: childrenRect.height
        anchors.verticalCenter: parent.verticalCenter
    }
}
