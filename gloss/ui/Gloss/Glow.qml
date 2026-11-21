import QtQuick

// 一团从中心向外淡出的光晕，颜色跟着主题走。只在颜色或尺寸变了的时候重画一次
Canvas {
    id: root
    property color tint: Theme.glowA

    onTintChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        // 在单位圆里画，再拉伸到整个画布，这样椭圆形的光晕也能用
        ctx.translate(width / 2, height / 2)
        ctx.scale(width / 2, height / 2)
        const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1)
        g.addColorStop(0, Qt.rgba(tint.r, tint.g, tint.b, 1))
        g.addColorStop(0.45, Qt.rgba(tint.r, tint.g, tint.b, 0.34))
        g.addColorStop(1, Qt.rgba(tint.r, tint.g, tint.b, 0))
        ctx.fillStyle = g
        ctx.fillRect(-1, -1, 2, 2)
    }
}
