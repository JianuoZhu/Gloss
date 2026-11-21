import QtQuick
import QtQuick.Templates as T

T.Switch {
    id: control
    implicitWidth: 38
    implicitHeight: 22
    hoverEnabled: true

    indicator: Rectangle {
        width: 38
        height: 22
        radius: 11
        color: control.checked ? Theme.accent : Theme.veil(control.hovered ? 0.24 : 0.17)
        Behavior on color { ColorAnimation { duration: Theme.base } }

        Rectangle {
            width: control.down ? 20 : 16
            height: 16
            radius: 8
            y: 3
            x: control.checked ? parent.width - width - 3 : 3
            color: control.checked ? Theme.accentInk : Theme.knob
            Behavior on x { NumberAnimation { duration: Theme.base; easing.type: Easing.OutCubic } }
            Behavior on width { NumberAnimation { duration: Theme.fast } }
            Behavior on color { ColorAnimation { duration: Theme.base } }
        }
    }
}
