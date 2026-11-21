import QtQuick

// 一个快捷键：点一下进入录入状态，按下新的组合键就改好了。Esc 取消，Backspace 清除（不用这个快捷键）
Rectangle {
    id: root
    property string action: ""
    property string keys: ""
    property bool conflict: false   // 向系统注册失败：多半被别的程序占用了
    property bool capturing: false
    property bool rejected: false   // 刚才按的组合不能用

    function begin() { rejected = false; capturing = true; backend.captureHotkey(true); catcher.forceActiveFocus() }
    function end() { if (capturing) { capturing = false; backend.captureHotkey(false) } }

    implicitWidth: Math.max(96, label.implicitWidth + 28)
    implicitHeight: 30
    radius: 7
    color: capturing ? Theme.accentSoft : area.containsMouse ? Theme.fieldHover : Theme.field
    border.width: 1
    border.color: capturing ? Theme.accent : conflict || rejected ? Theme.warn : "transparent"
    Behavior on color { ColorAnimation { duration: Theme.fast } }
    Behavior on border.color { ColorAnimation { duration: Theme.fast } }

    Text {
        id: label
        anchors.centerIn: parent
        text: root.capturing ? "按下新的快捷键…"
            : root.rejected ? "这个组合不能用"
            : root.keys !== "" ? root.keys : "未设置"
        font.pixelSize: 12
        font.family: root.capturing || root.rejected || root.keys === "" ? Qt.application.font.family : "Cascadia Mono"
        color: root.capturing ? Theme.accent : root.rejected ? Theme.warn : root.keys !== "" ? Theme.text : Theme.textFaint
    }

    Item {
        id: catcher
        onActiveFocusChanged: if (!activeFocus) root.end()
        Keys.onPressed: (event) => {
            if (!root.capturing) return
            event.accepted = true
            if (event.key === Qt.Key_Escape) { root.end(); return }
            if (event.key === Qt.Key_Backspace || event.key === Qt.Key_Delete) {
                backend.setHotkey(root.action, 0, 0)
                root.end()
                return
            }
            // 只按下修饰键时继续等
            if ([Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr].includes(event.key)) return
            root.rejected = !backend.setHotkey(root.action, event.key, event.modifiers)
            root.end()
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.capturing ? root.end() : root.begin()
    }
}
