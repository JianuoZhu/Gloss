import QtQuick

// 一个指标：大数字 + 小标签，没有盒子。数值变化时数字滚动过去，而不是直接跳
Item {
    id: root
    property string label: ""
    property string unit: ""
    property var value          // undefined 表示还没有数据
    property real shown: 0
    property bool divider: true // 左边画一条细线，和前一个指标隔开

    implicitHeight: 62

    onValueChanged: if (value !== undefined) shown = value
    Behavior on shown { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }

    Rectangle {
        visible: root.divider
        width: 1
        height: 34
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.stroke
    }

    Column {
        x: root.divider ? 22 : 0
        anchors.verticalCenter: parent.verticalCenter
        spacing: 3
        Row {
            spacing: 4
            Text {
                id: number
                text: root.value === undefined ? "—" : Math.round(root.shown)
                font.family: Theme.display
                font.pixelSize: 27
                font.weight: root.value === undefined ? Font.Light : Font.DemiBold
                color: root.value === undefined ? Theme.veil(0.25) : Theme.text
            }
            Text {
                visible: root.value !== undefined
                text: root.unit
                font.pixelSize: 12
                color: Theme.textFaint
                anchors.baseline: number.baseline
            }
        }
        Text {
            text: root.label
            font.pixelSize: 12
            color: Theme.textFaint
        }
    }
}
