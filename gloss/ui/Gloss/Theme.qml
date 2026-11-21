pragma Singleton
import QtQuick

// 设计规范。几条原则：
//   - 靠明度分层，不靠边框和阴影：深色主题里往上每一层亮一点点，浅色主题里面板是白的、画布是浅灰
//   - 分隔用很淡的细线，不用描边的盒子
//   - 强调色一屏只出现在一处最重要的地方（主操作、当前选中）
//   - 间距只用 4 的倍数；字号拉开档次，层级主要靠字
//
// 所有颜色都从当前主题的色板里取。界面里不要写死颜色：
// 需要"在底色上叠一层淡淡的深浅"时用 veil()，它在深色主题里叠白、浅色主题里叠黑。
QtObject {
    id: theme

    // 当前主题的名字，由 Main.qml 绑定到设置里选的那个
    property string name: "light"

    readonly property var palettes: ({
        // 浅色：浅灰画布上的白色面板，强调色用深一点的青绿（在白底上要看得清）
        light: {
            dark: false, label: "浅色",
            bg: "#F4F5F7", rail: "#ECEEF2", surface: "#FFFFFF", surfaceHi: "#FFFFFF", inset: Qt.rgba(0, 0, 0, 0.045),
            text: "#15171C", textDim: "#4B5362", textFaint: "#6B7482",
            accent: "#0E9A7B", accent2: "#1486C9", accent3: "#6B5BD6", accentInk: "#FFFFFF",
            danger: "#D14343", warn: "#A8690F", knob: "#FFFFFF",
            glowA: "#3ED6B0", glowB: "#8E9BFF", glow: 0.2
        },
        // 暖纸：米色的纸面，陶土色的强调
        paper: {
            dark: false, label: "暖纸",
            bg: "#F3EEE4", rail: "#EAE3D6", surface: "#FBF8F1", surfaceHi: "#FFFDF8", inset: Qt.rgba(0.27, 0.2, 0.08, 0.07),
            text: "#2B2620", textDim: "#5F574B", textFaint: "#7A6F60",
            accent: "#B4532A", accent2: "#C8892B", accent3: "#7A6A3A", accentInk: "#FFFFFF",
            danger: "#C23B3B", warn: "#9A6410", knob: "#FFFFFF",
            glowA: "#E3A66B", glowB: "#D98C8C", glow: 0.22
        },
        // 深色：近黑的画布，薄荷色的强调
        dark: {
            dark: true, label: "深色",
            bg: "#0B0C0F", rail: "#08090B", surface: Qt.rgba(1, 1, 1, 0.035), surfaceHi: "#1A1D24", inset: Qt.rgba(0, 0, 0, 0.28),
            text: "#EDEFF3", textDim: "#A6AEBB", textFaint: "#7A8391",
            accent: "#7EE7C7", accent2: "#6CC8F5", accent3: "#A99BFF", accentInk: "#04211A",
            danger: "#FF7A7A", warn: "#F5C065", knob: "#EDEFF3",
            glowA: "#7EE7C7", glowB: "#6E7BFF", glow: 0.1
        },
        // 墨蓝：深蓝的画布，冷蓝到淡紫的强调
        midnight: {
            dark: true, label: "墨蓝",
            bg: "#0A0F1E", rail: "#070B17", surface: Qt.rgba(1, 1, 1, 0.045), surfaceHi: "#18203A", inset: Qt.rgba(0, 0, 0, 0.3),
            text: "#E9EDF7", textDim: "#A3AECB", textFaint: "#7480A0",
            accent: "#8AB4FF", accent2: "#B79BFF", accent3: "#7EE7C7", accentInk: "#08122E",
            danger: "#FF7A7A", warn: "#F5C065", knob: "#E9EDF7",
            glowA: "#6E9BFF", glowB: "#9A6CF6", glow: 0.13
        }
    })
    readonly property var p: palettes[name] !== undefined ? palettes[name] : palettes.light
    readonly property bool dark: p.dark

    // 在底色上叠一层：深色主题叠白，浅色主题叠黑（黑比白显眼，所以淡一些）
    function veil(alpha) { return dark ? Qt.rgba(1, 1, 1, alpha) : Qt.rgba(0, 0, 0, alpha * 0.72) }

    // ---- 层 ----
    readonly property color bg: p.bg                          // 画布
    readonly property color rail: p.rail                      // 侧栏
    readonly property color surface: p.surface                // 分组面板
    readonly property color surfaceHi: p.surfaceHi            // 浮层（下拉菜单、提示），必须不透明
    readonly property color inset: p.inset                    // 面板里凹下去的一块
    readonly property color field: veil(0.055)                // 输入控件的底
    readonly property color fieldHover: veil(0.09)
    readonly property color hover: veil(0.06)
    readonly property color stroke: veil(dark ? 0.07 : 0.11)  // 细线
    readonly property color strokeHi: veil(dark ? 0.14 : 0.2)

    // ---- 字 ----
    readonly property color text: p.text
    readonly property color textDim: p.textDim
    readonly property color textFaint: p.textFaint

    // ---- 强调 ----
    readonly property color accent: p.accent
    readonly property color accent2: p.accent2                // 和 accent 组成主操作的渐变
    readonly property color accent3: p.accent3                // 第三个辅助色，只用来区分类别
    readonly property color accentInk: p.accentInk            // 强调色上面的字
    readonly property color accentSoft: Qt.alpha(accent, dark ? 0.13 : 0.1)    // 选中项的底
    readonly property color accentLine: Qt.alpha(accent, 0.55)                 // 选中项的描边
    readonly property color accentSelect: Qt.alpha(accent, 0.3)                // 选中的文字
    readonly property color danger: p.danger
    readonly property color warn: p.warn
    readonly property color knob: p.knob                      // 开关和滑块上的圆钮

    // ---- 环境光 ----
    readonly property color glowA: p.glowA
    readonly property color glowB: p.glowB
    readonly property real glow: p.glow

    // ---- 形 ----
    readonly property int radius: 8
    readonly property int cardRadius: 14
    readonly property int rowHeight: 46

    // ---- 字体 ----
    readonly property string display: "Segoe UI Variable Display"   // 只用在数字和西文字样上：它没有中文字形，中文会回退成宋体
    readonly property string iconFont: "Segoe Fluent Icons"

    // ---- 动效：悬停/按下用 fast，状态切换用 base，页面和入场用 slow ----
    readonly property int fast: 110
    readonly property int base: 170
    readonly property int slow: 260
}
