import QtQuick
import Gloss

// 盖在游戏窗口上的透明层。位置和大小由 Python 按游戏窗口的客户区设置（物理像素），
// 所以块的坐标要除以屏幕缩放比换成 Qt 的逻辑像素。
//
// 三种显示方式：
//   inplace   原位覆盖：译文按原文的位置、字号、颜色盖在原文上
//   float     悬浮：不遮原文，译文以半透明小标签浮在原文旁边（放哪一侧由 BlockModel 算好）
//   subtitle  字幕条：不遮原文，把最近几句集中显示在一处
Window {
    id: overlay
    objectName: "overlay"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
    color: "transparent"
    // 连续翻译、待命（等临时翻译）、或者有提示要显示时都要在
    visible: (backend.running || backend.standby || toast.shown) && backend.overlayVisible

    readonly property real k: 1 / Screen.devicePixelRatio
    readonly property var disp: backend.profile.display
    readonly property string mode: disp.mode
    // 只指定一个西文字体时，中文会回退到宋体；所以默认直接用雅黑
    readonly property string fontFamily: disp.font_family !== "" ? disp.font_family : "Microsoft YaHei UI"
    readonly property int weight: disp.font_weight === "bold" ? Font.Bold : disp.font_weight === "normal" ? Font.Normal : Font.Medium
    readonly property color textColor: disp.text_color !== "" ? disp.text_color : "#F2F4F7"
    readonly property color bgColor: disp.bg_color !== "" ? disp.bg_color : "#0C0E12"
    // 描边用和文字相反的深浅
    readonly property color outlineColor: textColor.hslLightness < 0.45 ? "#FFFFFF" : "#000000"

    Repeater {
        model: blockModel
        delegate: Item {
            id: blk
            readonly property string body: model.text
            readonly property bool has: body !== ""
            readonly property real fpx: Math.max(9, model.fontPx * overlay.k * overlay.disp.font_scale)
            readonly property real pad: Math.round(fpx * 0.3)

            // 按原字号排，译文要占几行
            readonly property real fill: natural.advanceWidth / Math.max(1, width)
            readonly property int rows: Math.max(1, Math.ceil(fill))
            // 只多出一点点就再起一行会留下孤零零的一两个字；差得不多（缩到 86% 以内）就缩字号少排一行
            readonly property real tighten: rows > 1 ? (rows - 1) / fill : 1
            readonly property bool tightened: model.multiline && rows > 1 && tighten >= 0.86
            readonly property int usedRows: tightened ? rows - 1 : rows
            // 单行文本放不下时先缩字号，缩到七成还放不下就让底框变宽
            readonly property real shrink: model.multiline ? (tightened ? tighten * 0.985 : 1)
                                         : fill <= 1 ? 1 : Math.max(0.7, 1 / fill)
            // 译文行数不超过原文时，行距锁成原文的行距，每一行都落在原文那一行的位置上
            readonly property bool pitchLocked: model.multiline && usedRows <= model.lineCount

            x: model.bx * overlay.k
            y: model.by * overlay.k
            width: model.bw * overlay.k
            height: model.bh * overlay.k
            visible: overlay.mode !== "subtitle"
            opacity: model.leaving ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

            TextMetrics {
                id: natural
                text: blk.body
                font.pixelSize: blk.fpx
                font.family: label.font.family
                font.weight: label.font.weight
            }

            // 等译文时，原文下方有一道来回扫的细线
            Rectangle {
                visible: !blk.has
                y: parent.height + 1
                width: parent.width
                height: 2
                radius: 1
                color: Qt.rgba(0.49, 0.91, 0.78, 0.22)
                clip: true
                Rectangle {
                    width: Math.max(24, parent.width * 0.3)
                    height: parent.height
                    radius: 1
                    color: Theme.accent
                    SequentialAnimation on x {
                        running: !blk.has && overlay.visible
                        loops: Animation.Infinite
                        NumberAnimation { from: -parent.width * 0.3; to: blk.width; duration: 900; easing.type: Easing.InOutSine }
                    }
                }
            }

            // ---- 原位覆盖 ----
            Rectangle {
                id: cover
                // 左右多留一些：OCR 的行框经常框不全句末的标点
                x: Math.min(0, label.x) - blk.pad * 1.6
                y: -Math.round(blk.pad * 0.5)
                width: Math.max(blk.width, label.x + label.width) - Math.min(0, label.x) + 3.2 * blk.pad
                height: blk.height + blk.pad
                radius: Math.min(8, blk.fpx * 0.3)
                color: overlay.disp.background === "auto" ? model.bg : overlay.bgColor
                visible: overlay.mode === "inplace" && overlay.disp.background !== "none"
                opacity: 0
            }

            Text {
                id: label
                property real lift: 4
                visible: overlay.mode === "inplace"
                text: blk.body
                opacity: 0
                color: overlay.disp.text_color !== "" ? overlay.textColor
                     : overlay.disp.background === "auto" ? model.fg : "#F2F4F7"
                style: overlay.disp.outline || overlay.disp.background === "none" ? Text.Outline : Text.Normal
                styleColor: color.hslLightness < 0.45 ? "#FFFFFF" : "#000000"
                font.family: overlay.fontFamily
                font.weight: overlay.weight
                renderType: Text.QtRendering  // 透明窗口上系统的次像素抗锯齿会出彩色毛边
                font.pixelSize: blk.fpx * blk.shrink
                lineHeightMode: blk.pitchLocked ? Text.FixedHeight : Text.ProportionalHeight
                lineHeight: blk.pitchLocked ? blk.height / model.lineCount : 1.08
                transform: Translate { y: label.lift }

                // 多行：占满原段落的框，在框里重新折行，放不下就缩字号
                // 单行：按原文的对齐方式贴在原位置
                width: model.multiline ? blk.width : implicitWidth
                height: model.multiline ? blk.height : implicitHeight
                x: model.multiline || model.align === "left" ? 0
                 : model.align === "center" ? (blk.width - width) / 2 : blk.width - width
                y: model.multiline ? 0 : (blk.height - height) / 2
                wrapMode: model.multiline ? Text.Wrap : Text.NoWrap
                // 译文比原文行数多时才需要自动缩字号把它塞回框里
                fontSizeMode: model.multiline && !blk.pitchLocked ? Text.Fit : Text.FixedSize
                minimumPixelSize: Math.max(8, blk.fpx * 0.55)
                horizontalAlignment: model.align === "center" ? Text.AlignHCenter
                                   : model.align === "right" ? Text.AlignRight : Text.AlignLeft
                verticalAlignment: model.multiline ? Text.AlignTop : Text.AlignVCenter
            }

            // ---- 悬浮：半透明小标签，贴在原文的上 / 下 / 右 / 左侧，不遮原文 ----
            Item {
                id: bubble
                readonly property real gap: 5
                readonly property real fpx: Math.max(10, blk.fpx * 0.86)
                readonly property real padH: Math.round(fpx * 0.55)
                readonly property real padV: Math.round(fpx * 0.28)
                // 从原文那一侧滑出来：在上方就从下往上，在下方就从上往下
                property real slide: model.fside === 0 ? 6 : model.fside === 1 ? -6 : 0

                visible: overlay.mode === "float"
                width: bubbleText.width + 2 * padH
                height: bubbleText.height + 2 * padV
                x: model.fside === 2 ? blk.width + gap
                 : model.fside === 3 ? -width - gap
                 : (model.fx - model.bx) * overlay.k
                y: model.fside === 0 ? -height - gap
                 : model.fside === 1 ? blk.height + gap
                 : (blk.height - height) / 2
                opacity: 0
                transform: Translate { y: bubble.slide }
                Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                Behavior on y { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

                Rectangle {   // 只有底是半透明的，文字保持清晰
                    anchors.fill: parent
                    radius: Math.min(7, bubble.fpx * 0.4)
                    color: overlay.bgColor
                    opacity: overlay.disp.float_opacity
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.14)
                }
                Text {
                    id: bubbleText
                    x: bubble.padH
                    y: bubble.padV
                    width: Math.min(implicitWidth, Math.max(40, model.fw * overlay.k - 2 * bubble.padH))
                    text: blk.body
                    color: overlay.textColor
                    style: overlay.disp.outline ? Text.Outline : Text.Normal
                    styleColor: overlay.outlineColor
                    font.family: overlay.fontFamily
                    font.weight: overlay.weight
                    renderType: Text.QtRendering
                    font.pixelSize: bubble.fpx
                    lineHeight: 1.12
                    wrapMode: Text.Wrap
                }
            }

            states: State {
                name: "shown"
                when: blk.has
                PropertyChanges { target: cover; opacity: overlay.disp.opacity }
                PropertyChanges { target: label; opacity: 1; lift: 0 }
                PropertyChanges { target: bubble; opacity: 1; slide: 0 }
            }
            transitions: Transition {
                to: "shown"
                NumberAnimation { properties: "opacity,lift,slide"; duration: 190; easing.type: Easing.OutCubic }
            }
        }
    }

    // ---- 字幕条：不遮原文，把最近出现的几句集中显示在原文上方（上方没地方就放下方） ----
    Rectangle {
        id: subs
        readonly property real fpx: Math.max(15, overlay.height * 0.028) * overlay.disp.font_scale
        readonly property real above: blockModel.minY * overlay.k - height - 14
        visible: overlay.mode === "subtitle" && blockModel.shownCount > 0
        width: Math.min(overlay.width * 0.72, 1100)
        height: lines.implicitHeight + 24
        x: (overlay.width - width) / 2
        y: above >= 8 ? above : Math.min(overlay.height - height - 8, blockModel.maxY * overlay.k + 14)
        color: "transparent"
        Rectangle {   // 只有底是半透明的
            anchors.fill: parent
            radius: 12
            color: overlay.bgColor
            opacity: overlay.disp.float_opacity
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.12)
        }
        Behavior on height { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

        Column {
            id: lines
            x: 22; y: 12
            width: parent.width - 44
            spacing: 6
            Repeater {
                model: overlay.mode === "subtitle" ? blockModel.subtitleLines : []
                Text {
                    width: lines.width
                    text: modelData
                    color: overlay.textColor
                    style: overlay.disp.outline ? Text.Outline : Text.Normal
                    styleColor: overlay.outlineColor
                    font.family: overlay.fontFamily
                    font.pixelSize: subs.fpx
                    font.weight: overlay.weight
                    renderType: Text.QtRendering
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }

    // ---- 提示：在游戏里按了快捷键之后，告诉用户发生了什么 ----
    Rectangle {
        id: toast
        property string message: ""
        readonly property bool shown: opacity > 0
        anchors.horizontalCenter: parent.horizontalCenter
        y: 28 + (backend.toast !== "" ? 0 : -8)
        width: toastText.implicitWidth + 40
        height: 38
        radius: 19
        color: Qt.rgba(0.047, 0.055, 0.071, 0.92)
        border.width: 1
        border.color: Qt.rgba(0.49, 0.91, 0.78, 0.45)
        opacity: backend.toast !== "" ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        // 提示收起的那一小段时间里文字不能先消失
        Connections {
            target: backend
            function onToastChanged() { if (backend.toast !== "") toast.message = backend.toast }
        }
        Row {
            anchors.centerIn: parent
            spacing: 9
            Rectangle { width: 6; height: 6; radius: 3; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
            Text {
                id: toastText
                text: toast.message
                color: "#F2F4F7"
                font.family: "Microsoft YaHei UI"
                font.pixelSize: 14
                font.weight: Font.Medium
                renderType: Text.QtRendering
            }
        }
    }
}
