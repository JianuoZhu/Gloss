import QtQuick
import Gloss

// 盖在游戏窗口上的识别区域编辑器。
// 拖空白处新增一个区域；拖方框移动；拉边和角调整大小；点方框右上角的 × 删除。
// 每次松手都立刻写进当前游戏的预设，正在运行的翻译也马上按新区域识别，不用重新开始。
Window {
    id: picker
    objectName: "picker"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: Qt.rgba(0, 0, 0, 0.45)
    visible: false

    property var rects: []        // 正在编辑的区域 [[x, y, w, h]]，都是相对窗口的 0~1 比例
    property bool busy: false     // 正在拖动：这期间不接收外面来的更新
    property point origin
    property bool drawing: false
    readonly property real minW: 28 / Math.max(1, width)
    readonly property real minH: 20 / Math.max(1, height)

    function load() { rects = backend.profile.regions.map(r => r.slice()) }
    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)) }
    function commit(list) { busy = false; backend.setRegions(list) }

    onVisibleChanged: if (visible) { busy = false; drawing = false; load(); stage.forceActiveFocus() }
    Connections {
        target: backend
        function onProfileChanged() { if (!picker.busy) picker.load() }
    }

    Item {
        id: stage
        anchors.fill: parent
        focus: true
        Keys.onEscapePressed: picker.visible = false
        Keys.onReturnPressed: picker.visible = false
        Keys.onEnterPressed: picker.visible = false

        // 空白处：拖出一个新区域
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.CrossCursor
            onPressed: (m) => {
                picker.origin = Qt.point(m.x, m.y)
                fresh.x = m.x; fresh.y = m.y; fresh.width = 0; fresh.height = 0
                picker.drawing = picker.busy = true
            }
            onPositionChanged: (m) => {
                if (!picker.drawing) return
                const mx = picker.clamp(m.x, 0, picker.width), my = picker.clamp(m.y, 0, picker.height)
                fresh.x = Math.min(picker.origin.x, mx); fresh.y = Math.min(picker.origin.y, my)
                fresh.width = Math.abs(mx - picker.origin.x); fresh.height = Math.abs(my - picker.origin.y)
            }
            onReleased: {
                if (!picker.drawing) return
                picker.drawing = false
                const list = picker.rects.map(r => r.slice())
                if (fresh.width / picker.width >= picker.minW && fresh.height / picker.height >= picker.minH)
                    list.push([fresh.x / picker.width, fresh.y / picker.height, fresh.width / picker.width, fresh.height / picker.height])
                picker.commit(list)
            }
        }

        Rectangle {
            id: fresh
            visible: picker.drawing
            color: Qt.rgba(0.49, 0.91, 0.78, 0.16)
            border.width: 2
            border.color: Theme.accent
            radius: 4
        }

        Repeater {
            model: picker.rects
            delegate: Item {
                id: reg
                // 拖动时只改这四个数，松手才写回去
                property real rx: modelData[0]
                property real ry: modelData[1]
                property real rw: modelData[2]
                property real rh: modelData[3]
                x: rx * picker.width
                y: ry * picker.height
                width: rw * picker.width
                height: rh * picker.height

                function save() {
                    const list = picker.rects.map(r => r.slice())
                    list[index] = [rx, ry, rw, rh]
                    picker.commit(list)
                }

                Rectangle {
                    anchors.fill: parent
                    radius: 4
                    color: Qt.rgba(0.49, 0.91, 0.78, body.containsMouse || body.pressed ? 0.2 : 0.11)
                    border.width: 2
                    border.color: Theme.accent
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                }
                Rectangle {
                    x: 8; y: 8
                    width: 22; height: 22; radius: 11
                    color: Theme.accent
                    Text { anchors.centerIn: parent; text: index + 1; font.pixelSize: 12; font.weight: Font.DemiBold; color: Theme.accentInk }
                }

                MouseArea {   // 整块拖动
                    id: body
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.SizeAllCursor
                    property point start
                    property real sx
                    property real sy
                    onPressed: (m) => { picker.busy = true; start = mapToItem(stage, m.x, m.y); sx = reg.rx; sy = reg.ry }
                    onPositionChanged: (m) => {
                        if (!pressed) return
                        const p = mapToItem(stage, m.x, m.y)
                        reg.rx = picker.clamp(sx + (p.x - start.x) / picker.width, 0, 1 - reg.rw)
                        reg.ry = picker.clamp(sy + (p.y - start.y) / picker.height, 0, 1 - reg.rh)
                    }
                    onReleased: reg.save()
                }

                Repeater {    // 八个调整大小的把手：四角 + 四边中点
                    model: [[-1, -1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1]]
                    Rectangle {
                        readonly property int hx: modelData[0]
                        readonly property int hy: modelData[1]
                        width: 12; height: 12; radius: 6
                        x: (hx + 1) / 2 * reg.width - 6
                        y: (hy + 1) / 2 * reg.height - 6
                        color: Theme.bg
                        border.width: 2
                        border.color: Theme.accent
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -7
                            cursorShape: hx === 0 ? Qt.SizeVerCursor : hy === 0 ? Qt.SizeHorCursor
                                       : hx === hy ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor
                            property point start
                            property var from: []
                            onPressed: (m) => { picker.busy = true; start = mapToItem(stage, m.x, m.y); from = [reg.rx, reg.ry, reg.rw, reg.rh] }
                            onPositionChanged: (m) => {
                                if (!pressed) return
                                const p = mapToItem(stage, m.x, m.y)
                                const dx = (p.x - start.x) / picker.width, dy = (p.y - start.y) / picker.height
                                let x0 = from[0], y0 = from[1], x1 = from[0] + from[2], y1 = from[1] + from[3]
                                if (hx < 0) x0 = picker.clamp(x0 + dx, 0, x1 - picker.minW)
                                if (hx > 0) x1 = picker.clamp(x1 + dx, x0 + picker.minW, 1)
                                if (hy < 0) y0 = picker.clamp(y0 + dy, 0, y1 - picker.minH)
                                if (hy > 0) y1 = picker.clamp(y1 + dy, y0 + picker.minH, 1)
                                reg.rx = x0; reg.ry = y0; reg.rw = x1 - x0; reg.rh = y1 - y0
                            }
                            onReleased: reg.save()
                        }
                    }
                }

                Rectangle {   // 删除这个区域
                    x: parent.width - width - 8; y: 8
                    width: 22; height: 22; radius: 11
                    visible: reg.width > 70 && reg.height > 38
                    color: del.containsMouse ? Theme.danger : Theme.surfaceHi
                    border.width: 1
                    border.color: Theme.strokeHi
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                    Icon { anchors.centerIn: parent; glyph: ""; size: 9; color: del.containsMouse ? "#1A0606" : Theme.text }
                    MouseArea {
                        id: del
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: picker.commit(picker.rects.filter((r, i) => i !== index))
                    }
                }
            }
        }

        // 顶部的说明和按钮
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 20
            width: bar.implicitWidth + 28
            height: 44
            radius: 22
            color: Theme.surfaceHi
            border.width: 1
            border.color: Theme.strokeHi
            opacity: picker.busy ? 0.25 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.fast } }
            MouseArea { anchors.fill: parent }   // 挡住下面的"新增区域"
            Row {
                id: bar
                anchors.centerIn: parent
                spacing: 14
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: (picker.rects.length === 0 ? "还没有区域，现在识别整个窗口" : picker.rects.length + " 个识别区域")
                        + "   ·   拖空白处新增，拖方框移动，拉边角调整"
                    font.pixelSize: 13
                    color: Theme.text
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "已自动保存到「" + backend.profile.name + "」"
                    font.pixelSize: 12
                    color: Theme.accent
                }
                GButton {
                    anchors.verticalCenter: parent.verticalCenter
                    implicitHeight: 30
                    text: "清除全部"
                    variant: "ghost"
                    enabled: picker.rects.length > 0
                    onClicked: picker.commit([])
                }
                GButton {
                    anchors.verticalCenter: parent.verticalCenter
                    implicitHeight: 30
                    text: "完成"
                    variant: "primary"
                    onClicked: picker.visible = false
                }
            }
        }
    }
}
