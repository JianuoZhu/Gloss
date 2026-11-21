import QtQuick

// 一个本地翻译模型的安装状态：已安装 / 下载按钮 / 下载进度
FormRow {
    id: root
    property string kind: ""
    readonly property var info: backend.localModels[kind]
    readonly property var job: backend.installProgress
    readonly property bool busy: job.kind === kind

    label: "模型文件"
    hint: info.installed ? "" : "下载到 %LOCALAPPDATA%\\Gloss\\local-mt"

    Item {
        width: parent.width
        height: 34

        Row {
            visible: root.info.installed
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Icon { glyph: ""; size: 13; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
            Text { text: "已安装"; font.pixelSize: 13; color: Theme.text; anchors.verticalCenter: parent.verticalCenter }
        }

        GButton {
            visible: !root.info.installed && !root.busy
            enabled: backend.installProgress.kind === ""
            glyph: ""
            text: "下载（约 " + (root.info.downloadMb >= 1000 ? (root.info.downloadMb / 1000).toFixed(1) + " GB" : root.info.downloadMb + " MB") + "）"
            variant: "primary"
            onClicked: backend.installLocalModel(root.kind)
        }

        Column {
            visible: root.busy
            width: parent.width
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Rectangle {
                width: parent.width
                height: 4
                radius: 2
                color: Theme.veil(0.12)
                Rectangle {
                    width: parent.width * root.job.progress
                    height: parent.height
                    radius: 2
                    color: Theme.accent
                    Behavior on width { NumberAnimation { duration: Theme.base } }
                }
            }
            Text {
                text: Math.round(root.job.progress * 100) + "%  ·  " + root.job.file
                font.pixelSize: 11
                color: Theme.textFaint
            }
        }

        Text {
            visible: !root.busy && !root.info.installed && root.job.error !== "" && root.job.failed === root.kind
            anchors.left: parent.left
            anchors.leftMargin: 190
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - 190
            text: root.job.error
            font.pixelSize: 12
            color: Theme.danger
            elide: Text.ElideRight
        }
    }
}
