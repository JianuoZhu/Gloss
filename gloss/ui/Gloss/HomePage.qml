import QtQuick

// 首页。视线的顺序：现在在翻什么 → 开始 / 停止 → 怎么显示 → 运行得怎么样
PageScroll {
    id: page
    signal openProfile()

    readonly property bool hasTarget: backend.target.hwnd !== undefined
    readonly property bool failed: backend.statusLevel === "error"

    // ---- 主操作区 ----
    Item {
        width: parent.width
        height: 100

        Column {
            width: parent.width - startButton.width - 32
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Row {
                spacing: 8
                Rectangle {
                    width: 7; height: 7; radius: 3.5
                    anchors.verticalCenter: parent.verticalCenter
                    color: page.failed ? Theme.danger : backend.running ? Theme.accent : backend.standby ? Theme.accent2 : Theme.textFaint
                    Behavior on color { ColorAnimation { duration: Theme.base } }
                }
                Text {
                    text: page.failed || backend.running || backend.standby ? backend.statusText : "待机"
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    font.letterSpacing: 0.6
                    color: page.failed ? Theme.danger : backend.running ? Theme.accent : backend.standby ? Theme.accent2 : Theme.textFaint
                }
            }
            Text {
                width: parent.width
                text: page.hasTarget ? backend.target.title : "选一个游戏窗口"
                font.pixelSize: 32
                font.weight: Font.DemiBold
                font.letterSpacing: -0.5
                color: Theme.text
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: page.hasTarget
                    ? "预设「" + backend.profile.name + "」  ·  "
                      + (backend.profile.scope === "regions" && backend.profile.regions.length > 0
                         ? backend.profile.regions.length + " 个固定区域" : "识别整个窗口")
                      + "  ·  " + backend.profile.glossary.length + " 条术语"
                    : "Gloss 会把译文按原文的位置和排版显示在游戏画面上"
                font.pixelSize: 13
                color: Theme.textFaint
                elide: Text.ElideRight
            }
        }

        // 开始 / 停止：整页唯一用强调色铺满的东西
        Item {
            id: startButton
            width: 172; height: 56
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            readonly property bool ready: page.hasTarget && !backend.running
            scale: press.pressed ? 0.97 : 1
            Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }

            Glow {      // 按钮身后的光
                tint: Theme.accent
                anchors.centerIn: parent
                width: 330; height: 210
                opacity: backend.running || !page.hasTarget ? 0 : press.containsMouse ? 0.5 : 0.3
                Behavior on opacity { NumberAnimation { duration: Theme.slow } }
            }
            Rectangle {
                anchors.fill: parent
                radius: 28
                gradient: startButton.ready ? fill : null
                color: press.containsMouse && backend.running ? Theme.fieldHover : Theme.field
                border.width: backend.running ? 1 : 0
                border.color: Theme.strokeHi
                Gradient {
                    id: fill
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.accent }
                    GradientStop { position: 1; color: Theme.accent2 }
                }
            }
            Row {
                anchors.centerIn: parent
                spacing: 10
                Icon {
                    glyph: backend.running ? "" : ""
                    size: 15
                    color: startButton.ready ? Theme.accentInk : backend.running ? Theme.text : Theme.textFaint
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: backend.running ? "停止" : "开始翻译"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    color: startButton.ready ? Theme.accentInk : backend.running ? Theme.text : Theme.textFaint
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            MouseArea {
                id: press
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                enabled: backend.running || page.hasTarget
                onClicked: backend.toggle()
            }
        }
    }

    // ---- 翻译哪个窗口 ----
    Card {
        FormRow {
            label: "游戏窗口"
            Row {
                width: parent.width
                spacing: 8
                GCombo {
                    id: windowCombo
                    width: parent.width - refresh.width - 8
                    model: backend.windows
                    valueRole: "hwnd"
                    value: backend.target.hwnd
                    placeholder: "选择要翻译的窗口"
                    onPicked: (v) => backend.selectWindow(v)
                    Connections {
                        target: windowCombo.popup
                        function onAboutToShow() { backend.refreshWindows() }
                    }
                }
                GButton { id: refresh; glyph: ""; onClicked: backend.refreshWindows() }
            }
        }
        FormRow {
            label: "游戏预设"
            hint: "每个游戏一份，自动切换"
            Row {
                width: parent.width
                spacing: 8
                GCombo {
                    width: parent.width - edit.width - 8
                    model: backend.profiles
                    value: backend.settings.active_profile
                    onPicked: (v) => backend.selectProfile(v)
                }
                GButton { id: edit; glyph: ""; onClicked: page.openProfile() }
            }
        }
    }

    // ---- 怎么显示 ----
    Column {
        width: parent.width
        spacing: 10
        Text {
            x: 4
            text: "显示方式"
            font.pixelSize: 12
            font.weight: Font.DemiBold
            font.letterSpacing: 1.2
            color: Theme.textDim
        }
        Row {
            width: parent.width
            spacing: 12
            Repeater {
                model: [
                    { mode: "inplace", label: "原位覆盖", desc: "译文盖在原文上，像游戏自带中文" },
                    { mode: "float", label: "悬浮", desc: "不遮原文，译文浮在旁边" },
                    { mode: "subtitle", label: "字幕条", desc: "不遮原文，集中显示最新几句" }
                ]
                ModeCard {
                    width: (parent.width - 24) / 3
                    mode: modelData.mode
                    label: modelData.label
                    desc: modelData.desc
                    selected: backend.profile.display.mode === modelData.mode
                    onPicked: backend.setProfile("display.mode", modelData.mode)
                }
            }
        }
    }

    // ---- 运行得怎么样 ----
    Rectangle {
        width: parent.width
        height: 84
        radius: Theme.cardRadius
        color: Theme.surface
        Row {
            x: 26
            width: parent.width - 52
            anchors.verticalCenter: parent.verticalCenter
            Metric { width: parent.width / 4; divider: false; label: "识别耗时"; unit: "ms"; value: backend.running ? backend.stats.ocrMs : undefined }
            Metric { width: parent.width / 4; label: "译文首字"; unit: "ms"; value: backend.running ? backend.stats.firstTokenMs : undefined }
            Metric { width: parent.width / 4; label: "Gloss 占用 CPU"; unit: "%"; value: backend.usage.cpu }
            Metric { width: parent.width / 4; label: "Gloss 占用内存"; unit: "MB"; value: backend.usage.mem }
        }
    }

    // ---- 快捷键：游戏在前台时也能用。到「设置」页可以改 ----
    Flow {
        x: 4
        width: parent.width - 8
        spacing: 10
        Repeater {
            model: backend.hotkeys
            Row {
                width: (parent.width - 20) / 3
                spacing: 9
                Rectangle {
                    width: keys.implicitWidth + 16
                    height: 24
                    radius: 6
                    color: Theme.field
                    border.width: 1
                    border.color: modelData.conflict ? Theme.warn : "transparent"
                    Text {
                        id: keys
                        anchors.centerIn: parent
                        text: modelData.keys !== "" ? modelData.keys : "未设置"
                        font.pixelSize: 11
                        font.family: "Cascadia Mono"
                        color: modelData.keys !== "" ? Theme.textDim : Theme.textFaint
                    }
                }
                Text {
                    width: parent.width - keys.implicitWidth - 16 - 9
                    text: modelData.label
                    font.pixelSize: 12
                    color: Theme.textFaint
                    elide: Text.ElideRight
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }
}
