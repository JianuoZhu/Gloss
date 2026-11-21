import QtQuick

PageScroll {
    id: page
    title: "预设"
    subtitle: "每个游戏一份专属配置：识别哪里、怎么显示、术语怎么译"

    readonly property var p: backend.profile
    readonly property bool isDefault: p.id === "default"

    header: GButton {
        glyph: ""
        text: "删除这份预设"
        variant: "danger"
        visible: !page.isDefault
        onClicked: backend.deleteProfile()
    }

    Card {
        FormRow {
            label: "当前预设"
            GCombo {
                width: parent.width
                model: backend.profiles
                value: backend.settings.active_profile
                onPicked: (v) => backend.selectProfile(v)
            }
        }
        Item {
            visible: page.isDefault
            width: parent.width
            height: defaultNote.height + 24
            Rectangle { width: parent.width; height: 1; color: Theme.stroke }
            Text {
                id: defaultNote
                y: 12
                width: parent.width
                text: "这是默认预设。在「翻译」页选中一个游戏窗口时，Gloss 会按这里的设置给它建一份专属预设；认不出程序名的窗口直接用这份。"
                font.pixelSize: 12
                color: Theme.textFaint
                wrapMode: Text.Wrap
                lineHeight: 1.3
            }
        }
        FormRow {
            visible: !page.isDefault
            label: "名称"
            GField {
                width: parent.width
                text: page.p.name
                onEditingFinished: if (text !== page.p.name && text.trim() !== "") backend.setProfile("name", text.trim())
            }
        }
        FormRow {
            visible: !page.isDefault
            label: "所属游戏"
            hint: "选中这个程序的窗口时自动切到这份预设"
            GField {
                width: parent.width
                placeholderText: "程序文件名，例如 Game.exe"
                text: page.p.match.exe
                onEditingFinished: if (text !== page.p.match.exe) backend.setProfile("match.exe", text.trim())
            }
        }
    }

    Card {
        title: "语言"
        FormRow {
            label: "原文语言"
            GCombo {
                width: parent.width
                model: backend.sourceLangs
                value: page.p.source_lang
                onPicked: (v) => backend.setProfile("source_lang", v)
            }
        }
        FormRow {
            label: "翻译成"
            GCombo {
                width: parent.width
                model: backend.targetLangs
                value: page.p.target_lang
                onPicked: (v) => backend.setProfile("target_lang", v)
            }
        }
    }

    Card {
        title: "识别区域"
        caption: "不框选就识别整个窗口。只框有文字的地方（对话框、任务栏……）识别更快、占用更低，也能避开画面里的干扰文字。可以框多个。"
        FormRow {
            label: "连续翻译识别"
            hint: backend.hotkeys[5].keys !== "" ? "游戏里按 " + backend.hotkeys[5].keys + " 切换" : ""
            GSegmented {
                options: [{ value: "regions", label: "固定区域" }, { value: "full", label: "整个窗口" }]
                value: page.p.scope === "regions" && page.p.regions.length > 0 ? "regions" : "full"
                onPicked: (v) => v === "regions" && page.p.regions.length === 0 ? backend.pickRegion() : backend.setScope(v)
            }
        }
        FormRow {
            label: page.p.regions.length > 0 ? page.p.regions.length + " 个固定区域" : "还没有固定区域"
            hint: backend.hotkeys[2].keys !== "" ? "游戏里按 " + backend.hotkeys[2].keys + " 随时打开" : ""
            Row {
                spacing: 8
                GButton { glyph: ""; text: "在游戏里编辑区域"; onClicked: backend.pickRegion() }
                GButton { text: "清除"; variant: "ghost"; enabled: page.p.regions.length > 0; onClicked: backend.clearRegions() }
            }
        }
        FormRow {
            label: "最小文字高度"
            hint: "小于它的文字不翻译"
            Row {
                width: parent.width
                spacing: 12
                GSlider {
                    width: parent.width - 60
                    from: 8; to: 40; stepSize: 1
                    value: page.p.filter.min_height
                    onMoved: backend.setProfile("filter.min_height", value)
                }
                Text { text: page.p.filter.min_height + " px"; font.pixelSize: 12; color: Theme.textDim; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }

    Card {
        id: look
        title: "显示"
        caption: "改动立刻生效，翻译不用重新开始。"
        readonly property var d: page.p.display
        readonly property bool inplace: d.mode === "inplace"
        // 原位覆盖要盖住原文，悬浮和字幕条要透出画面，所以各记各的不透明度
        readonly property string opacityKey: inplace ? "opacity" : "float_opacity"
        readonly property bool customBg: !inplace || d.background === "color" || d.background === "dark"

        FormRow {
            label: "显示方式"
            GSegmented {
                options: [{ value: "inplace", label: "原位覆盖" }, { value: "float", label: "悬浮（不遮原文）" }, { value: "subtitle", label: "字幕条" }]
                value: look.d.mode
                onPicked: (v) => backend.setProfile("display.mode", v)
            }
        }

        // 预览：按当前设置画一条示例译文
        Item { width: parent.width; height: 4 }
        Rectangle {
            width: parent.width
            height: 96
            radius: 10
            clip: true
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#243352" }
                GradientStop { position: 0.55; color: "#5E4A78" }
                GradientStop { position: 1.0; color: "#B9805A" }
            }
            Text { x: 18; y: 14; text: "The ancient relic lies beneath the ruins."; font.pixelSize: 15; color: Qt.rgba(1, 1, 1, 0.85) }
            Item {
                x: 18; y: 44
                width: sample.width + 22
                height: sample.height + 10
                Rectangle {
                    anchors.fill: parent
                    radius: 6
                    visible: !(look.inplace && look.d.background === "none")
                    color: look.customBg ? (look.d.bg_color !== "" ? look.d.bg_color : "#0C0E12") : "#243352"
                    opacity: look.d[look.opacityKey]
                }
                Text {
                    id: sample
                    x: 11; y: 5
                    text: "古代遗物就埋在这片废墟之下。"
                    font.family: look.d.font_family !== "" ? look.d.font_family : "Microsoft YaHei UI"
                    font.pixelSize: Math.round(16 * look.d.font_scale)
                    font.weight: look.d.font_weight === "bold" ? Font.Bold : look.d.font_weight === "normal" ? Font.Normal : Font.Medium
                    color: look.d.text_color !== "" ? look.d.text_color : "#F2F4F7"
                    style: look.d.outline || (look.inplace && look.d.background === "none") ? Text.Outline : Text.Normal
                    styleColor: color.hslLightness < 0.45 ? "#FFFFFF" : "#000000"
                    renderType: Text.QtRendering
                }
            }
        }

        Item { width: parent.width; height: 10 }
        FormRow {
            label: "文字颜色"
            GColor {
                value: look.d.text_color
                autoLabel: look.inplace ? "跟随原文" : "默认"
                onPicked: (v) => backend.setProfile("display.text_color", v)
            }
        }
        FormRow {
            visible: look.inplace
            label: "译文的底"
            GSegmented {
                options: [{ value: "auto", label: "取原画面底色" }, { value: "color", label: "自选颜色" }, { value: "none", label: "不要底" }]
                value: look.d.background === "dark" ? "color" : look.d.background
                onPicked: (v) => backend.setProfile("display.background", v)
            }
        }
        FormRow {
            visible: look.customBg
            label: "底色"
            GColor {
                value: look.d.bg_color
                autoLabel: "默认"
                swatches: ["#0C0E12", "#1E2A44", "#3A2A4A", "#2F3B2F", "#F2EEE2", "#FFFFFF"]
                onPicked: (v) => backend.setProfile("display.bg_color", v)
            }
        }
        FormRow {
            visible: !(look.inplace && look.d.background === "none")
            label: "底色不透明度"
            Row {
                width: parent.width
                spacing: 12
                GSlider {
                    width: parent.width - 60
                    from: 0; to: 1; stepSize: 0.01
                    value: look.d[look.opacityKey]
                    onMoved: backend.setProfile("display." + look.opacityKey, Math.round(value * 100) / 100)
                }
                Text { text: Math.round(look.d[look.opacityKey] * 100) + "%"; font.pixelSize: 12; color: Theme.textDim; anchors.verticalCenter: parent.verticalCenter }
            }
        }
        FormRow {
            label: "字体"
            GCombo {
                width: parent.width
                model: backend.fonts
                value: look.d.font_family
                onPicked: (v) => backend.setProfile("display.font_family", v)
            }
        }
        FormRow {
            label: "字号"
            hint: "相对原文的大小"
            Row {
                width: parent.width
                spacing: 12
                GSlider {
                    width: parent.width - 60
                    from: 0.5; to: 2.0; stepSize: 0.05
                    value: look.d.font_scale
                    onMoved: backend.setProfile("display.font_scale", Math.round(value * 100) / 100)
                }
                Text { text: Math.round(look.d.font_scale * 100) + "%"; font.pixelSize: 12; color: Theme.textDim; anchors.verticalCenter: parent.verticalCenter }
            }
        }
        FormRow {
            label: "字重"
            GSegmented {
                options: [{ value: "normal", label: "常规" }, { value: "medium", label: "中等" }, { value: "bold", label: "粗体" }]
                value: look.d.font_weight
                onPicked: (v) => backend.setProfile("display.font_weight", v)
            }
        }
        FormRow {
            label: "文字描边"
            hint: "背景花的时候更好认"
            GSwitch {
                checked: look.d.outline
                onToggled: backend.setProfile("display.outline", checked)
            }
        }
    }

    Card {
        title: "游戏说明"
        caption: "写给翻译模型看的背景和语气要求，只对 LLM 类翻译后端生效。"
        Rectangle {
            width: parent.width
            height: 96
            radius: Theme.radius
            color: Theme.field
            border.width: 1
            border.color: prompt.activeFocus ? Theme.accent : "transparent"
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
            Flickable {
                anchors.fill: parent
                anchors.margins: 10
                contentHeight: prompt.implicitHeight
                clip: true
                TextEdit {
                    id: prompt
                    width: parent.width
                    text: page.p.prompt
                    font.pixelSize: 13
                    color: Theme.text
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    selectionColor: Theme.accentSelect
                    onEditingFinished: if (text !== page.p.prompt) backend.setProfile("prompt", text)
                }
            }
            Text {
                x: 10; y: 10
                visible: prompt.text === ""
                text: "例如：中世纪奇幻背景，主角说话直率；地名用音译。"
                font.pixelSize: 13
                color: Theme.textFaint
            }
        }
    }
}
