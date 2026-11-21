import QtQuick
import Gloss

// 临时框选：在游戏画面上拖一个框，松手就把这一块翻译一次。不会存进预设
Window {
    id: snap
    objectName: "snap"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: Qt.rgba(0, 0, 0, 0.32)
    visible: false

    property point origin
    property bool dragging: false

    onVisibleChanged: if (visible) { dragging = false; stage.forceActiveFocus() }

    Item {
        id: stage
        anchors.fill: parent
        focus: true
        Keys.onEscapePressed: snap.visible = false

        Rectangle {
            id: box
            visible: snap.dragging
            color: Qt.rgba(0.49, 0.91, 0.78, 0.14)
            border.width: 2
            border.color: Theme.accent
            radius: 4
        }

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 20
            width: hint.implicitWidth + 36
            height: 40
            radius: 20
            color: Theme.surfaceHi
            border.width: 1
            border.color: Theme.strokeHi
            opacity: snap.dragging ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.fast } }
            Text {
                id: hint
                anchors.centerIn: parent
                text: "拖出要翻译的那一块，松手就翻   ·   Esc 取消"
                renderType: Text.QtRendering
                font.pixelSize: 13
                color: Theme.text
            }
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.CrossCursor
            onPressed: (m) => {
                if (m.button === Qt.RightButton) { snap.visible = false; return }
                snap.origin = Qt.point(m.x, m.y)
                box.x = m.x; box.y = m.y; box.width = 0; box.height = 0
                snap.dragging = true
            }
            onPositionChanged: (m) => {
                if (!snap.dragging) return
                const mx = Math.max(0, Math.min(snap.width, m.x)), my = Math.max(0, Math.min(snap.height, m.y))
                box.x = Math.min(snap.origin.x, mx); box.y = Math.min(snap.origin.y, my)
                box.width = Math.abs(mx - snap.origin.x); box.height = Math.abs(my - snap.origin.y)
            }
            onReleased: {
                if (!snap.dragging) return
                snap.dragging = false
                snap.visible = false
                if (box.width > 16 && box.height > 12)
                    backend.snapRegion(box.x / snap.width, box.y / snap.height, box.width / snap.width, box.height / snap.height)
            }
        }
    }
}
