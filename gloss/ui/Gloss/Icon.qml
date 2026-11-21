import QtQuick

// Windows 自带图标字体里的一个字形
Text {
    property string glyph: ""
    property real size: 16
    text: glyph
    font.family: Theme.iconFont
    font.pixelSize: size
    color: Theme.textDim
    renderType: Text.QtRendering
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
}
