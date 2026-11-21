import QtQuick

// 翻译引擎选择器：先按类别分页，再在一格格的引擎里点选。比 24 项的下拉框好找
Item {
    id: root
    property string value: ""                 // 当前引擎 id
    signal picked(string value)

    readonly property var groups: ["本地", "在线机翻", "大模型"]
    readonly property var tints: ({ "本地": Theme.accent, "在线机翻": Theme.accent2, "大模型": Theme.accent3 })
    property string group: {
        for (const e of backend.engines) if (e.value === value) return e.group
        return "本地"
    }

    width: parent ? parent.width : 0
    implicitHeight: tabs.height + 14 + grid.implicitHeight

    GSegmented {
        id: tabs
        options: root.groups.map(g => ({ value: g, label: g + "  " + backend.engines.filter(e => e.group === g).length }))
        value: root.group
        onPicked: (v) => root.group = v
    }

    Flow {
        id: grid
        y: tabs.height + 14
        width: parent.width
        spacing: 8
        Repeater {
            model: backend.engines.filter(e => e.group === root.group)
            Rectangle {
                readonly property bool current: modelData.value === root.value
                width: (grid.width - 16) / 3
                height: 50
                radius: 10
                color: current ? Theme.accentSoft : tile.containsMouse ? Theme.fieldHover : Theme.field
                border.width: 1
                border.color: current ? Theme.accentLine : "transparent"
                Behavior on color { ColorAnimation { duration: Theme.fast } }

                Rectangle {   // 引擎名的首字，按类别着色
                    id: badge
                    x: 11
                    anchors.verticalCenter: parent.verticalCenter
                    width: 28; height: 28; radius: 8
                    color: Qt.alpha(root.tints[modelData.group], 0.16)
                    Text {
                        anchors.centerIn: parent
                        text: modelData.name.charAt(0)
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                        color: root.tints[modelData.group]
                    }
                }
                Column {
                    x: 49
                    width: parent.width - 49 - 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1
                    Text {
                        width: parent.width
                        text: modelData.name
                        font.pixelSize: 13
                        font.weight: current ? Font.DemiBold : Font.Normal
                        color: Theme.text
                        elide: Text.ElideRight
                    }
                    Text {
                        width: parent.width
                        text: modelData.tag
                        visible: text !== ""
                        font.pixelSize: 11
                        color: modelData.verified === "real" ? Theme.accent : Theme.textFaint
                        elide: Text.ElideRight
                    }
                }
                MouseArea {
                    id: tile
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.picked(modelData.value)
                }
            }
        }
    }
}
