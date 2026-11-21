import QtQuick
import QtQuick.Templates as T

T.Slider {
    id: control
    implicitWidth: 200
    implicitHeight: 22
    hoverEnabled: true

    background: Rectangle {
        x: control.leftPadding
        y: (control.height - height) / 2
        width: control.availableWidth
        height: 4
        radius: 2
        color: Theme.veil(0.12)
        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 2
            color: Theme.accent
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: (control.height - height) / 2
        width: 14
        height: 14
        radius: 7
        color: Theme.knob
        border.width: Theme.dark ? 0 : 1
        border.color: Theme.strokeHi
        scale: control.pressed ? 1.25 : control.hovered ? 1.12 : 1
        Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
    }
}
