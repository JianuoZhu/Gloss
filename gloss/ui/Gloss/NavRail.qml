import QtQuick

// 左侧导航：选中项后面的底块在各项之间滑动
Item {
    id: root
    property var items: []      // [{glyph, label}]
    property int current: 0
    signal picked(int index)

    implicitHeight: col.implicitHeight

    Rectangle {
        y: root.current * 42
        width: parent.width
        height: 38
        radius: 10
        color: Theme.dark ? Theme.veil(0.07) : Theme.surface   // 浅色主题里选中项是一块白
        Behavior on y { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
    }

    Column {
        id: col
        width: parent.width
        spacing: 4
        Repeater {
            model: root.items
            Item {
                width: col.width
                height: 38
                readonly property bool active: index === root.current
                Rectangle {
                    anchors.fill: parent
                    radius: 10
                    color: Theme.hover
                    opacity: area.containsMouse && !active ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
                Row {
                    x: 14
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 12
                    Icon {
                        glyph: modelData.glyph
                        size: 15
                        color: active ? Theme.accent : Theme.textDim
                        anchors.verticalCenter: parent.verticalCenter
                        Behavior on color { ColorAnimation { duration: Theme.base } }
                    }
                    Text {
                        text: modelData.label
                        font.pixelSize: 13
                        font.weight: active ? Font.DemiBold : Font.Normal
                        color: active ? Theme.text : Theme.textDim
                        anchors.verticalCenter: parent.verticalCenter
                        Behavior on color { ColorAnimation { duration: Theme.base } }
                    }
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.picked(index)
                }
            }
        }
    }
}
