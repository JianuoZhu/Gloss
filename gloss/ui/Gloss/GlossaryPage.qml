import QtQuick

// 术语表不放进滚动页里：表头和新增行固定，只有列表滚动
Item {
    id: page

    function commitNew() {
        if (newSrc.text.trim() === "") return
        termModel.add(newSrc.text, newDst.text, newNote.text)
        newSrc.text = ""; newDst.text = ""; newNote.text = ""
        newSrc.forceActiveFocus()
    }

    Column {
        id: titles
        x: 36; y: 2
        spacing: 6
        Text { text: "术语"; font.pixelSize: 28; font.weight: Font.DemiBold; font.letterSpacing: -0.3; color: Theme.text }
        Text {
            text: "预设「" + backend.profile.name + "」的专有名词。出现在原文里时，译文会固定用这里的译名"
            font.pixelSize: 13
            color: Theme.textFaint
        }
    }

    Rectangle {
        x: 36
        y: titles.y + titles.height + 26
        width: parent.width - 72
        height: parent.height - y - 32
        radius: Theme.cardRadius
        color: Theme.surface

        readonly property real colSrc: (width - 36 - 44) * 0.3
        readonly property real colDst: (width - 36 - 44) * 0.3
        readonly property real colNote: (width - 36 - 44) * 0.4
        id: table

        Row {
            id: addRow
            x: 14; y: 14
            width: parent.width - 28
            spacing: 8
            GField { id: newSrc; width: table.colSrc - 4; placeholderText: "原文，例如 アリシア"; onAccepted: newDst.forceActiveFocus() }
            GField { id: newDst; width: table.colDst - 4; placeholderText: "译名，例如 艾莉西亚"; onAccepted: page.commitNew() }
            GField { id: newNote; width: table.colNote - 12; placeholderText: "备注（可选），例如 女主角"; onAccepted: page.commitNew() }
            GButton { width: 36; glyph: ""; variant: "primary"; enabled: newSrc.text.trim() !== ""; onClicked: page.commitNew() }
        }

        Rectangle { id: rule; x: 0; y: addRow.y + addRow.height + 14; width: parent.width; height: 1; color: Theme.stroke }

        ListView {
            id: list
            x: 14
            y: rule.y + 9
            width: parent.width - 28
            height: parent.height - y - 10
            clip: true
            model: termModel
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds

            add: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.base }
                NumberAnimation { property: "y"; from: -12; duration: Theme.base; easing.type: Easing.OutCubic }
            }
            remove: Transition {
                NumberAnimation { property: "opacity"; to: 0; duration: Theme.fast }
            }
            displaced: Transition {
                NumberAnimation { property: "y"; duration: Theme.base; easing.type: Easing.OutCubic }
            }

            delegate: Item {
                id: rowItem
                width: list.width
                height: 36
                Row {
                    spacing: 8
                    anchors.verticalCenter: parent.verticalCenter
                    GField {
                        flat: true; width: table.colSrc - 4
                        text: model.src
                        onEditingFinished: termModel.setField(index, "src", text)
                    }
                    GField {
                        flat: true; width: table.colDst - 4
                        text: model.dst
                        color: Theme.accent
                        onEditingFinished: termModel.setField(index, "dst", text)
                    }
                    GField {
                        flat: true; width: table.colNote - 12
                        text: model.note
                        color: Theme.textDim
                        onEditingFinished: termModel.setField(index, "note", text)
                    }
                    GButton {
                        width: 36
                        glyph: ""
                        variant: "ghost"
                        opacity: hover.hovered ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                        onClicked: termModel.remove(index)
                    }
                }
                HoverHandler { id: hover }
            }

            Column {
                anchors.centerIn: parent
                visible: list.count === 0
                spacing: 8
                Icon { glyph: ""; size: 28; color: Theme.textFaint; anchors.horizontalCenter: parent.horizontalCenter }
                Text {
                    text: "还没有术语"
                    font.pixelSize: 13
                    color: Theme.textDim
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    text: "在上面填入人名、地名、技能名和你想要的译名"
                    font.pixelSize: 12
                    color: Theme.textFaint
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }
    }
}
