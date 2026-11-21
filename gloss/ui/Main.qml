import QtQuick
import QtQuick.Controls.Basic
import Gloss

ApplicationWindow {
    id: win
    objectName: "main"
    width: 1000
    height: 720
    minimumWidth: 880
    minimumHeight: 600
    visible: true
    title: "Gloss"
    color: Theme.bg
    flags: Qt.Window | Qt.FramelessWindowHint

    property int page: 0

    // 整个应用的主题跟着设置走（Theme 是全局的，悬浮层和框选层用的是同一个）
    Binding { target: Theme; property: "name"; value: backend.themeName }

    // ---- 环境光：画布上两团很淡的光晕，给深色背景一点纵深。翻译运行时薄荷色那团会亮起来 ----
    Glow {
        tint: Theme.glowB
        x: rail.width - 260
        y: parent.height - 420
        width: 760; height: 760
        opacity: Theme.glow
    }
    Glow {
        tint: Theme.glowA
        x: parent.width - 520
        y: -360
        width: 820; height: 820
        opacity: backend.running ? Theme.glow * 2 : Theme.glow
        Behavior on opacity { NumberAnimation { duration: 900; easing.type: Easing.InOutSine } }
    }

    // ---- 侧栏 ----
    Rectangle {
        id: rail
        width: 204
        height: parent.height
        color: Theme.rail

        Row {
            x: 22; y: 24
            spacing: 11
            Image {
                source: "icon.svg"
                sourceSize: Qt.size(56, 56)
                width: 28; height: 28
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: "Gloss"
                font.family: Theme.display
                font.pixelSize: 19
                font.weight: Font.DemiBold
                font.letterSpacing: 0.2
                color: Theme.text
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        NavRail {
            x: 14; y: 86
            width: parent.width - 28
            current: win.page
            items: [
                { glyph: "", label: "翻译" },
                { glyph: "", label: "预设" },
                { glyph: "", label: "术语" },
                { glyph: "", label: "设置" }
            ]
            onPicked: (i) => win.page = i
        }

        // 运行状态
        Item {
            x: 22
            y: parent.height - height - 22
            width: parent.width - 44
            height: 40

            Rectangle {
                id: dot
                anchors.verticalCenter: parent.verticalCenter
                width: 8; height: 8; radius: 4
                color: backend.statusLevel === "error" ? Theme.danger
                     : backend.running ? Theme.accent : backend.standby ? Theme.accent2 : Theme.textFaint
                Behavior on color { ColorAnimation { duration: Theme.base } }

                // 运行时向外扩散的一圈。窗口不在前台时停掉，不白白占显卡
                Rectangle {
                    anchors.centerIn: parent
                    width: 8; height: 8; radius: 4
                    color: "transparent"
                    border.width: 1
                    border.color: dot.color
                    visible: backend.running && win.active
                    SequentialAnimation on scale {
                        running: backend.running && win.active
                        loops: Animation.Infinite
                        NumberAnimation { from: 1; to: 2.8; duration: 1400; easing.type: Easing.OutCubic }
                        PauseAnimation { duration: 500 }
                    }
                    SequentialAnimation on opacity {
                        running: backend.running && win.active
                        loops: Animation.Infinite
                        NumberAnimation { from: 0.7; to: 0; duration: 1400; easing.type: Easing.OutCubic }
                        PauseAnimation { duration: 500 }
                    }
                }
            }
            Column {
                x: 20
                width: parent.width - 20
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Text {
                    width: parent.width
                    text: backend.statusLevel === "error" ? "出错了" : backend.running ? "翻译中" : backend.standby ? "快捷翻译待命" : "待机"
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    color: Theme.text
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    text: backend.statusLevel === "error" ? backend.statusText
                        : backend.running || backend.standby ? (backend.target.title || "")
                        : backend.hotkeys[0].keys !== "" ? backend.hotkeys[0].keys + " 开始" : ""
                    font.pixelSize: 11
                    color: Theme.textFaint
                    elide: Text.ElideRight
                }
            }
        }

        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.stroke }
    }

    // ---- 标题栏（可拖动） ----
    Item {
        id: titleBar
        x: rail.width
        width: parent.width - rail.width
        height: 52
        DragHandler {
            target: null
            onActiveChanged: if (active) win.startSystemMove()
        }
        Row {
            anchors.right: parent.right
            anchors.rightMargin: 10
            y: 10
            spacing: 2
            GButton { width: 38; implicitHeight: 30; variant: "ghost"; glyph: ""; onClicked: win.showMinimized() }
            GButton { width: 38; implicitHeight: 30; variant: "ghost"; glyph: ""; onClicked: Qt.quit() }
        }
    }

    // ---- 页面：切换时淡入并上移一点 ----
    Item {
        id: pages
        x: rail.width
        y: titleBar.height
        width: parent.width - rail.width
        height: parent.height - titleBar.height

        component PageSlot: Item {
            id: slot
            property int index: 0
            readonly property bool current: win.page === index
            anchors.fill: parent
            visible: opacity > 0
            opacity: current ? 1 : 0
            transform: Translate { y: slot.current ? 0 : 12; Behavior on y { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } } }
            Behavior on opacity { NumberAnimation { duration: slot.current ? Theme.slow : Theme.fast; easing.type: Easing.OutCubic } }
        }

        PageSlot { index: 0; HomePage { anchors.fill: parent; onOpenProfile: win.page = 1 } }
        PageSlot { index: 1; ProfilePage { anchors.fill: parent } }
        PageSlot { index: 2; GlossaryPage { anchors.fill: parent } }
        PageSlot { index: 3; EnginePage { anchors.fill: parent } }
    }

    // 无边框窗口没有系统描边，自己画一圈
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: Theme.stroke
    }
}
