import QtQuick

// 一种显示方式：上面是示意图（灰条 = 原文，亮条 = 译文），下面是名字和一句话说明
Rectangle {
    id: root
    property string mode: "inplace"     // inplace | float | subtitle
    property string label: ""
    property string desc: ""
    property bool selected: false
    signal picked()

    implicitHeight: 136
    radius: Theme.cardRadius
    color: selected ? Theme.accentSoft : area.containsMouse ? Theme.hover : Theme.surface
    border.width: 1
    border.color: selected ? Theme.accentLine : "transparent"
    Behavior on color { ColorAnimation { duration: Theme.base } }
    Behavior on border.color { ColorAnimation { duration: Theme.base } }

    readonly property color src: Theme.veil(0.2)
    readonly property color dst: selected ? Theme.accent : Theme.veil(0.6)

    // 示意图：一块"游戏画面"
    Rectangle {
        id: screen
        x: 14; y: 14
        width: parent.width - 28
        height: 60
        radius: 8
        color: Theme.inset

        // 原位覆盖：译文就在原文的位置上
        Column {
            visible: root.mode === "inplace"
            x: 14; anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Rectangle { width: screen.width * 0.56; height: 7; radius: 3.5; color: root.dst; Behavior on color { ColorAnimation { duration: Theme.base } } }
            Rectangle { width: screen.width * 0.38; height: 7; radius: 3.5; color: root.dst; Behavior on color { ColorAnimation { duration: Theme.base } } }
        }

        // 悬浮：原文还在，译文是旁边的小标签
        Item {
            visible: root.mode === "float"
            anchors.fill: parent
            Rectangle {
                x: 14; y: 9
                width: screen.width * 0.42; height: 15; radius: 5
                color: Theme.veil(0.1)
                Rectangle { x: 6; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 12; height: 5; radius: 2.5; color: root.dst; Behavior on color { ColorAnimation { duration: Theme.base } } }
            }
            Rectangle { x: 14; y: 31; width: screen.width * 0.56; height: 7; radius: 3.5; color: root.src }
            Rectangle { x: 14; y: 44; width: screen.width * 0.38; height: 7; radius: 3.5; color: root.src }
        }

        // 字幕条：原文还在，译文集中在一条里
        Item {
            visible: root.mode === "subtitle"
            anchors.fill: parent
            Rectangle { x: 14; y: 9; width: screen.width * 0.5; height: 7; radius: 3.5; color: root.src }
            Rectangle { x: 14; y: 22; width: screen.width * 0.34; height: 7; radius: 3.5; color: root.src }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 37
                width: screen.width * 0.72; height: 16; radius: 5
                color: Theme.veil(0.1)
                Rectangle { anchors.centerIn: parent; width: parent.width * 0.7; height: 5; radius: 2.5; color: root.dst; Behavior on color { ColorAnimation { duration: Theme.base } } }
            }
        }
    }

    Text {
        x: 16; y: 84
        text: root.label
        font.pixelSize: 14
        font.weight: Font.DemiBold
        color: Theme.text
    }
    Text {
        x: 16; y: 107
        width: parent.width - 32
        text: root.desc
        font.pixelSize: 12
        color: Theme.textFaint
        elide: Text.ElideRight
    }
    Icon {
        visible: root.selected
        x: parent.width - 30; y: 86
        glyph: ""
        size: 13
        color: Theme.accent
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.picked()
    }
}
