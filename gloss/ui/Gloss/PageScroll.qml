import QtQuick

// 页面容器：大标题 + 可滚动的一列分组
Item {
    id: root
    property string title: ""
    property string subtitle: ""
    default property alias content: col.data
    property alias header: headerSlot.data

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.y + col.implicitHeight + 32
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Column {
            id: titles
            x: 36
            y: 2
            width: flick.width - 72 - headerSlot.width - 16
            spacing: 6
            visible: root.title !== ""
            Text {
                text: root.title
                font.pixelSize: 28
                font.weight: Font.DemiBold
                font.letterSpacing: -0.3
                color: Theme.text
            }
            Text {
                visible: root.subtitle !== ""
                width: parent.width
                text: root.subtitle
                font.pixelSize: 13
                color: Theme.textFaint
                wrapMode: Text.Wrap
            }
        }
        Item {
            id: headerSlot
            anchors.right: parent.right
            anchors.rightMargin: 36
            y: 6
            width: childrenRect.width
            height: childrenRect.height
        }
        Column {
            id: col
            x: 36
            y: titles.visible ? titles.y + titles.height + 26 : 0
            width: flick.width - 72
            spacing: 22
        }
    }

    Rectangle {
        visible: flick.contentHeight > flick.height
        anchors.right: parent.right
        anchors.rightMargin: 8
        y: flick.visibleArea.yPosition * flick.height
        width: 3
        height: flick.visibleArea.heightRatio * flick.height
        radius: 1.5
        color: Theme.veil(flick.moving ? 0.3 : 0.12)
        Behavior on color { ColorAnimation { duration: Theme.base } }
    }
}
