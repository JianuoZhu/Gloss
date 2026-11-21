import QtQuick

PageScroll {
    id: page
    title: "设置"
    subtitle: "主题、翻译引擎、识别和快捷键，对所有游戏生效"

    readonly property var s: backend.settings
    readonly property string provider: s.translator.provider
    readonly property var engine: backend.engine

    // ---- 主题：每个选项是一小块按那套色板画的预览 ----
    Column {
        width: parent.width
        spacing: 10
        Text {
            x: 4
            text: "主题"
            font.pixelSize: 12
            font.weight: Font.DemiBold
            font.letterSpacing: 1.2
            color: Theme.textDim
        }
        Row {
            id: themeRow
            width: parent.width
            spacing: 10
            Repeater {
                model: backend.themes
                Rectangle {
                    id: swatch
                    readonly property bool current: page.s.theme === modelData.value
                    // "跟随系统"的预览是一半浅色一半深色
                    readonly property var a: Theme.palettes[modelData.value === "system" ? "light" : modelData.value]
                    readonly property var b: Theme.palettes[modelData.value === "system" ? "dark" : modelData.value]
                    width: (themeRow.width - 40) / 5
                    height: 104
                    radius: Theme.cardRadius
                    color: current ? Theme.accentSoft : pick.containsMouse ? Theme.hover : Theme.surface
                    border.width: 1
                    border.color: current ? Theme.accentLine : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.base } }

                    Item {      // 预览
                        x: 10; y: 10
                        width: parent.width - 20
                        height: 56
                        Rectangle { anchors.fill: parent; radius: 8; color: swatch.a.bg; border.width: 1; border.color: Theme.stroke }
                        Rectangle {   // 右半边（跟随系统时是深色那套）
                            visible: modelData.value === "system"
                            x: parent.width / 2
                            width: parent.width / 2
                            height: parent.height
                            radius: 8
                            color: swatch.b.bg
                            Rectangle { width: 8; height: parent.height; color: swatch.b.bg }
                        }
                        Rectangle { x: 9; y: 10; width: parent.width * 0.34; height: 6; radius: 3; color: swatch.a.text }
                        Rectangle { x: 9; y: 23; width: parent.width * 0.24; height: 5; radius: 2.5; color: swatch.a.textFaint }
                        Rectangle {
                            x: parent.width - width - 9; y: 34
                            width: parent.width * 0.36; height: 13; radius: 6.5
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: swatch.b.accent }
                                GradientStop { position: 1; color: swatch.b.accent2 }
                            }
                        }
                    }
                    Text {
                        x: 12; y: 76
                        text: modelData.label
                        font.pixelSize: 13
                        font.weight: swatch.current ? Font.DemiBold : Font.Normal
                        color: Theme.text
                    }
                    Icon { visible: swatch.current; x: parent.width - 26; y: 78; glyph: "\uE73E"; size: 12; color: Theme.accent }
                    MouseArea {
                        id: pick
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.setSetting("theme", modelData.value)
                    }
                }
            }
        }
    }

    Card {
        title: "翻译"
        Item {
            width: parent.width
            height: picker.implicitHeight + 24
            EnginePicker {
                id: picker
                y: 10
                value: page.provider
                onPicked: (v) => backend.setSetting("translator.provider", v)
            }
        }
        Item {
            visible: page.engine.note !== ""
            width: parent.width
            height: note.height + 22
            Rectangle { width: parent.width; height: 1; color: Theme.stroke }
            Text {
                id: note
                y: 12
                width: parent.width
                text: page.engine.note
                font.pixelSize: 12
                color: Theme.textFaint
                wrapMode: Text.Wrap
                lineHeight: 1.3
            }
        }
        // 没连真实服务验证过的引擎要明说
        Item {
            visible: page.engine.caution !== ""
            width: parent.width
            height: caution.height + 14
            Icon { glyph: "\uE7BA"; size: 13; color: Theme.warn; y: 1 }
            Text {
                id: caution
                x: 22
                width: parent.width - 22
                text: page.engine.caution
                font.pixelSize: 12
                color: Theme.warn
                wrapMode: Text.Wrap
            }
        }

        // 本地翻译模型：安装状态和运行设备
        ModelInstall { visible: page.provider === "hymt"; kind: "hymt" }
        FormRow {
            visible: page.provider === "hymt"
            label: "运行设备"
            hint: "开始翻译时按显卡当时的占用决定"
            GCombo {
                width: parent.width
                model: backend.hymtDevices
                value: page.s.translator.hymt.device
                onPicked: (v) => backend.setSetting("translator.hymt.device", v)
            }
        }
        FormRow {
            visible: page.provider === "hymt" && page.s.translator.hymt.device === "cpu"
            label: "CPU 线程数"
            hint: "实测 6 线程单句约 0.4 秒"
            GSegmented {
                options: [{ value: 4, label: "4" }, { value: 6, label: "6" }, { value: 8, label: "8" }, { value: 0, label: "不限" }]
                value: page.s.translator.hymt.threads
                onPicked: (v) => backend.setSetting("translator.hymt.threads", v)
            }
        }
        ModelInstall { visible: page.provider === "nllb"; kind: "nllb" }

        // 其它引擎要填的东西（密钥、模型名、地址……）由登记表给出
        Repeater {
            model: page.engine.fields
            FormRow {
                label: modelData.label
                hint: modelData.hint
                GField {
                    width: parent.width
                    echoMode: modelData.secret ? TextInput.Password : TextInput.Normal
                    placeholderText: modelData.placeholder
                    text: modelData.value
                    onEditingFinished: if (text.trim() !== modelData.value)
                        backend.setSetting("translator." + page.provider + "." + modelData.key, text.trim())
                }
            }
        }
        FormRow {
            visible: page.provider === "claude"
            label: "思考深度"
            hint: "越低越快"
            GSegmented {
                options: [{ value: "low", label: "低" }, { value: "medium", label: "中" }, { value: "high", label: "高" }]
                value: page.s.translator.claude.effort
                onPicked: (v) => backend.setSetting("translator.claude.effort", v)
            }
        }
    }

    Card {
        title: "快捷键"
        caption: "游戏在前台时也能用。点一下按键再按新的组合就改了；Esc 取消，Backspace 清除。组合里要带 Ctrl、Alt 或 Win，功能键可以单独用。"
        Repeater {
            model: backend.hotkeys
            FormRow {
                label: modelData.label
                hint: modelData.conflict ? "被别的程序占用了，换一个"
                    : modelData.action === "scope" ? "连续翻译在整个窗口和固定区域之间切换"
                    : modelData.action === "snap_full" ? "不用开着连续翻译；再按一次清除"
                    : modelData.action === "snap_region" ? "拖一个框，只翻这一块，不存进预设" : ""
                labelWidth: 260
                Row {
                    spacing: 8
                    GHotkey { action: modelData.action; keys: modelData.keys; conflict: modelData.conflict }
                    GButton {
                        implicitHeight: 30
                        variant: "ghost"
                        text: "恢复默认"
                        onClicked: backend.resetHotkey(modelData.action)
                    }
                }
            }
        }
        FormRow {
            label: "临时译文停留"
            hint: "临时翻译的结果多久后自动消失"
            labelWidth: 260
            Row {
                width: parent.width
                spacing: 12
                GSlider {
                    width: parent.width - 96
                    from: 0; to: 30; stepSize: 1
                    value: page.s.quick.hold_s
                    onMoved: backend.setSetting("quick.hold_s", value)
                }
                Text {
                    text: page.s.quick.hold_s > 0 ? page.s.quick.hold_s + " 秒" : "不自动消失"
                    font.pixelSize: 12
                    color: Theme.textDim
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }

    Card {
        title: "识别"
        FormRow {
            label: "OCR 引擎"
            GCombo {
                width: parent.width
                model: backend.ocrEngines
                value: page.s.ocr.engine
                onPicked: (v) => backend.setSetting("ocr.engine", v)
            }
        }
        FormRow {
            visible: page.s.ocr.engine === "rapid"
            label: "识别模型"
            hint: "日语、韩语请用均衡或精确"
            GSegmented {
                options: [{ value: "fast", label: "快（仅中英）" }, { value: "balanced", label: "均衡" }, { value: "accurate", label: "精确" }]
                value: page.s.ocr.model
                onPicked: (v) => backend.setSetting("ocr.model", v)
            }
        }
        FormRow {
            visible: page.s.ocr.engine === "rapid"
            label: "检测分辨率"
            hint: "小字识别不到就调高"
            Row {
                width: parent.width
                spacing: 12
                GSlider {
                    width: parent.width - 60
                    from: 640; to: 1920; stepSize: 160
                    value: page.s.ocr.det_side
                    onMoved: backend.setSetting("ocr.det_side", value)
                }
                Text { text: page.s.ocr.det_side + " px"; font.pixelSize: 12; color: Theme.textDim; anchors.verticalCenter: parent.verticalCenter }
            }
        }
        FormRow {
            visible: page.s.ocr.engine === "rapid"
            label: "显卡加速"
            hint: "DirectML"
            GSwitch {
                checked: page.s.ocr.use_gpu
                onToggled: backend.setSetting("ocr.use_gpu", checked)
            }
        }
    }

    Card {
        title: "画面捕获"
        FormRow {
            label: "捕获方式"
            hint: "窗口捕获拿不到画面时会自动改用屏幕区域"
            GSegmented {
                options: [{ value: "window", label: "窗口（推荐）" }, { value: "screen", label: "屏幕区域" }]
                value: page.s.capture.mode
                onPicked: (v) => backend.setSetting("capture.mode", v)
            }
        }
    }

    Card {
        title: "响应"
        caption: "文字停止变化后等多久开始识别；画面一直在动时最长隔多久强制识别一次。"
        FormRow {
            label: "稳定等待"
            Row {
                width: parent.width
                spacing: 12
                GSlider {
                    width: parent.width - 60
                    from: 60; to: 500; stepSize: 20
                    value: page.s.pipeline.settle_ms
                    onMoved: backend.setSetting("pipeline.settle_ms", value)
                }
                Text { text: page.s.pipeline.settle_ms + " ms"; font.pixelSize: 12; color: Theme.textDim; anchors.verticalCenter: parent.verticalCenter }
            }
        }
        FormRow {
            label: "最长间隔"
            Row {
                width: parent.width
                spacing: 12
                GSlider {
                    width: parent.width - 60
                    from: 300; to: 2000; stepSize: 100
                    value: page.s.pipeline.max_wait_ms
                    onMoved: backend.setSetting("pipeline.max_wait_ms", value)
                }
                Text { text: page.s.pipeline.max_wait_ms + " ms"; font.pixelSize: 12; color: Theme.textDim; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
}
