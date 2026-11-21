import QtQuick

// 选颜色：一个"自动"、几个常用色块、一个可以直接填 #RRGGBB 的输入框
Row {
    id: root
    property string value: ""            // "" 表示自动
    property string autoLabel: "自动"
    property var swatches: ["#F2F4F7", "#FFE08A", "#9BE7FF", "#B5F5A8", "#FFB3C7", "#0C0E12"]
    signal picked(string value)

    spacing: 8
    height: 28

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: autoText.implicitWidth + 20
        height: 26
        radius: 13
        color: root.value === "" ? Theme.surfaceHi : "transparent"
        border.width: 1
        border.color: root.value === "" ? Theme.accent : Theme.stroke
        Text {
            id: autoText
            anchors.centerIn: parent
            text: root.autoLabel
            font.pixelSize: 12
            color: root.value === "" ? Theme.text : Theme.textDim
        }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.picked("") }
    }

    Repeater {
        model: root.swatches
        Rectangle {
            readonly property bool current: root.value.toUpperCase() === modelData.toUpperCase()
            anchors.verticalCenter: parent.verticalCenter
            width: 22; height: 22; radius: 11
            color: modelData
            border.width: current ? 2 : 1
            border.color: current ? Theme.accent : Theme.strokeHi
            scale: dot.containsMouse ? 1.15 : 1
            Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
            MouseArea { id: dot; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.picked(modelData) }
        }
    }

    GField {
        anchors.verticalCenter: parent.verticalCenter
        width: 96
        implicitHeight: 28
        font.pixelSize: 12
        placeholderText: "#RRGGBB"
        text: root.value
        onEditingFinished: {
            const t = text.trim()
            if (t === "" || /^#[0-9a-fA-F]{6}$/.test(t)) {
                if (t.toUpperCase() !== root.value.toUpperCase()) root.picked(t.toUpperCase())
            } else {
                text = root.value   // 不是合法的颜色，改回去
            }
        }
    }
}
