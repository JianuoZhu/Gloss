import QtQuick

// 一组设置：小标题和说明在面板外面，面板本身只是一块比画布亮一点点的底，没有描边。
// 里面的各行（FormRow）之间由行自己画细线分隔。
Item {
    id: root
    property string title: ""
    property string caption: ""
    property int pad: 18
    default property alias content: body.data
    property alias spacing: body.spacing

    width: parent ? parent.width : 0
    implicitHeight: panel.y + panel.height

    Column {
        id: head
        x: 4
        width: root.width - 8
        spacing: 4
        visible: root.title !== ""
        Text {
            text: root.title
            font.pixelSize: 12
            font.weight: Font.DemiBold
            font.letterSpacing: 1.2
            color: Theme.textDim
        }
        Text {
            visible: root.caption !== ""
            width: parent.width
            text: root.caption
            font.pixelSize: 12
            color: Theme.textFaint
            wrapMode: Text.Wrap
            lineHeight: 1.25
        }
    }

    Rectangle {
        id: panel
        y: head.visible ? head.height + 10 : 0
        width: root.width
        height: body.implicitHeight + 2 * body.y
        radius: Theme.cardRadius
        color: Theme.surface

        Column {
            id: body
            x: root.pad
            y: 8
            width: panel.width - 2 * root.pad
            spacing: 0
        }
    }
}
