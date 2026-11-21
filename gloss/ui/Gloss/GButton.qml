import QtQuick
import QtQuick.Templates as T

T.Button {
    id: control
    property string variant: "subtle"   // primary | subtle | ghost | danger
    property string glyph: ""

    implicitHeight: 34
    implicitWidth: Math.max(implicitHeight, row.implicitWidth + (text ? 28 : 0))
    font.pixelSize: 13
    hoverEnabled: true
    opacity: enabled ? 1 : 0.38
    scale: down ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }

    readonly property color ink: variant === "primary" ? Theme.accentInk
                               : variant === "danger" ? Theme.danger
                               : hovered ? Theme.text : Theme.textDim

    background: Rectangle {
        radius: Theme.radius
        // 主操作是一道从薄荷到青的渐变，其它按钮只是一块淡淡的底
        gradient: control.variant === "primary" ? primaryFill : null
        color: control.variant === "ghost" ? (control.hovered ? Theme.hover : "transparent")
             : control.variant === "danger" ? (control.hovered ? Qt.alpha(Theme.danger, 0.16) : Qt.alpha(Theme.danger, 0.08))
             : (control.hovered ? Theme.fieldHover : Theme.field)
        Behavior on color { ColorAnimation { duration: Theme.fast } }

        Gradient {
            id: primaryFill
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: control.hovered ? Qt.lighter(Theme.accent, 1.08) : Theme.accent }
            GradientStop { position: 1; color: control.hovered ? Qt.lighter(Theme.accent2, 1.08) : Theme.accent2 }
        }
    }

    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 7
            Icon {
                visible: control.glyph !== ""
                glyph: control.glyph
                size: 14
                color: control.ink
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
            Text {
                visible: control.text !== ""
                text: control.text
                font: control.font
                color: control.ink
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
        }
    }
}
