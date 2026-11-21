import QtQuick

// 分段选择：options 是 [{value, label}]，选中的那格底下有一块会滑动的高亮
Rectangle {
    id: root
    property var options: []
    property var value
    signal picked(var value)

    readonly property int currentIndex: {
        for (let i = 0; i < options.length; i++)
            if (options[i].value === value) return i
        return -1
    }

    implicitHeight: 34
    implicitWidth: row.implicitWidth + 6
    radius: Theme.radius
    color: Theme.field

    Rectangle {
        id: thumb
        // 读 rep.count 是为了在各格创建出来之后重新求值（itemAt 本身不会触发更新）
        readonly property Item target: root.currentIndex >= 0 && root.currentIndex < rep.count ? rep.itemAt(root.currentIndex) : null
        visible: target !== null
        x: target ? row.x + target.x : 0
        y: 3
        width: target ? target.width : 0
        height: parent.height - 6
        radius: Theme.radius - 2
        color: Theme.dark ? Theme.veil(0.12) : Theme.surfaceHi   // 浅色主题里选中的那格是一块白
        Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
    }

    Row {
        id: row
        x: 3
        height: parent.height
        Repeater {
            id: rep
            model: root.options
            Item {
                width: label.implicitWidth + 26
                height: row.height
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: modelData.label
                    font.pixelSize: 13
                    color: index === root.currentIndex ? Theme.text : area.containsMouse ? Theme.text : Theme.textDim
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.picked(modelData.value)
                }
            }
        }
    }
}
