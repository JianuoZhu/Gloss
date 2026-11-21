import QtQuick
import QtQuick.Templates as T

// model 是 [{value, label}]；外面绑定 value，监听 picked(value)
T.ComboBox {
    id: control
    property var value
    property string placeholder: ""
    signal picked(var value)

    textRole: "label"
    valueRole: "value"
    implicitHeight: 34
    implicitWidth: 220
    font.pixelSize: 13
    hoverEnabled: true

    function sync() { currentIndex = indexOfValue(value) }
    onValueChanged: sync()
    onModelChanged: sync()
    Component.onCompleted: sync()
    onActivated: picked(currentValue)

    background: Rectangle {
        radius: Theme.radius
        color: control.hovered || control.popup.visible ? Theme.fieldHover : Theme.field
        border.width: 1
        border.color: control.popup.visible ? Theme.accent : "transparent"
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }

    contentItem: Text {
        leftPadding: 11
        rightPadding: 30
        text: control.currentIndex >= 0 ? control.displayText : control.placeholder
        font: control.font
        color: control.currentIndex >= 0 ? Theme.text : Theme.textFaint
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Icon {
        x: control.width - width - 10
        y: (control.height - height) / 2
        glyph: ""
        size: 10
        rotation: control.popup.visible ? 180 : 0
        Behavior on rotation { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
    }

    delegate: T.ItemDelegate {
        id: item
        width: ListView.view.width
        height: 32
        hoverEnabled: true
        readonly property bool current: control.currentIndex === index
        background: Rectangle {
            radius: 6
            color: item.hovered || control.highlightedIndex === index ? Theme.hover : "transparent"
        }
        contentItem: Text {
            leftPadding: 9
            rightPadding: 9
            text: modelData[control.textRole]
            font.pixelSize: 13
            color: item.current ? Theme.accent : Theme.text
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    popup: T.Popup {
        y: control.height + 5
        width: control.width
        padding: 5
        implicitHeight: Math.min(list.contentHeight + 10, 264)
        transformOrigin: Item.Top

        contentItem: ListView {
            id: list
            clip: true
            model: control.delegateModel
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
        }
        background: Rectangle {
            radius: Theme.radius + 2
            color: Theme.surfaceHi
            border.width: 1
            border.color: Theme.strokeHi
        }
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.base; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; to: 0; duration: 80 }
        }
    }
}
