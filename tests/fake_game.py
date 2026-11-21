"""一个假的"游戏窗口"，用来端到端测试：有菜单、任务面板和会换句子的对话框。

用法：python tests/fake_game.py [宽 高] [--background]   （物理像素，默认 1280 720）
--background：不抢焦点，并把窗口压到所有窗口下面（自动化测试用，窗口捕获不受遮挡影响）。
--animate：背景里有一直在动的色块，模拟画面不停变化的 3D 游戏（测占用用）。
对话每隔几秒换一句，新句子带打字机效果。
"""

from __future__ import annotations

import math
import sys

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QRasterWindow

DIALOGUES = [
    ("アリシア", ["この先の遺跡には、古代の魔導兵器が眠っていると聞いたわ。", "準備ができたら、北の門で待ち合わせましょう。"]),
    ("レオン", ["わかった。装備を整えてからすぐに向かうよ。"]),
]
MENU = ["New Game", "Continue", "Settings", "Quit to Desktop"]


class Game(QRasterWindow):
    def __init__(self, w: int, h: int) -> None:
        super().__init__()
        self.setTitle("Gloss Test Game")
        self.pw, self.ph = w, h
        dpr = self.screen().devicePixelRatio()
        self.resize(round(w / dpr), round(h / dpr))
        self.setFlags(Qt.Window | Qt.FramelessWindowHint)
        self.index, self.typed = 0, 10_000
        self.animate, self.tick = False, 0
        self.mover = QTimer(self, interval=33, timeout=self._move)
        self.typer = QTimer(self, interval=40, timeout=self._type)
        QTimer(self, interval=7000, timeout=self._next).start()

    def _move(self) -> None:
        self.tick += 1
        self.update()

    def _next(self) -> None:
        self.index = (self.index + 1) % len(DIALOGUES)
        self.typed = 0
        self.typer.start()

    def _type(self) -> None:
        self.typed += 2
        if self.typed >= sum(len(s) for s in DIALOGUES[self.index][1]):
            self.typed = 10_000
            self.typer.stop()
        self.update()

    def paintEvent(self, _) -> None:
        img = QImage(self.pw, self.ph, QImage.Format_RGB32)
        s = self.ph / 1080
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.fillRect(img.rect(), QColor(28, 34, 52))
        if self.animate:  # 几个来回飘的大色块：每一帧画面都在变，但文字不变
            p.setPen(Qt.NoPen)
            for i in range(7):
                phase = self.tick * (0.011 + 0.004 * i) + i * 1.7
                cx = self.pw * (0.5 + 0.45 * math.sin(phase))
                cy = self.ph * (0.42 + 0.3 * math.cos(phase * 0.8 + i))
                r = self.ph * (0.10 + 0.03 * i)
                p.setBrush(QColor(40 + 25 * i, 70 + 12 * i, 120 - 10 * i, 150))
                p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

        def font(family: str, px: float) -> None:
            f = QFont(family)
            f.setPixelSize(round(px * s))
            p.setFont(f)

        font("Segoe UI", 44)
        p.setPen(QColor(230, 230, 235))
        for i, item in enumerate(MENU):
            p.drawText(QRectF(180 * s, (200 + i * 70) * s, 800 * s, 60 * s), Qt.AlignLeft | Qt.AlignVCenter, item)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(240, 236, 224))
        p.drawRoundedRect(QRectF(1280 * s, 120 * s, 520 * s, 210 * s), 12 * s, 12 * s)
        font("Segoe UI", 30)
        p.setPen(QColor(120, 60, 20))
        p.drawText(QRectF(1310 * s, 136 * s, 460 * s, 44 * s), Qt.AlignLeft | Qt.AlignVCenter, "Main Quest")
        font("Segoe UI", 28)
        p.setPen(QColor(40, 40, 40))
        p.drawText(QRectF(1310 * s, 188 * s, 470 * s, 40 * s), Qt.AlignLeft | Qt.AlignVCenter, "Find the ancient relic hidden")
        p.drawText(QRectF(1310 * s, 228 * s, 470 * s, 40 * s), Qt.AlignLeft | Qt.AlignVCenter, "beneath the northern ruins.")

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(12, 14, 24))
        p.drawRoundedRect(QRectF(160 * s, 760 * s, 1600 * s, 260 * s), 18 * s, 18 * s)
        name, lines = DIALOGUES[self.index]
        font("Yu Gothic UI", 34)
        p.setPen(QColor(255, 214, 120))
        p.drawText(QRectF(200 * s, 776 * s, 600 * s, 48 * s), Qt.AlignLeft | Qt.AlignVCenter, name)
        font("Yu Gothic UI", 40)
        p.setPen(QColor(240, 240, 240))
        left = self.typed
        for i, line in enumerate(lines):
            shown = line[: max(0, left)]
            left -= len(line)
            p.drawText(QRectF(200 * s, (836 + i * 60) * s, 1520 * s, 56 * s), Qt.AlignLeft | Qt.AlignVCenter, shown)
        p.end()

        img.setDevicePixelRatio(self.devicePixelRatio())
        out = QPainter(self)
        out.drawImage(0, 0, img)
        out.end()


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    size = [int(a) for a in sys.argv[1:] if a.isdigit()]
    w, h = size if len(size) == 2 else (1280, 720)
    game = Game(w, h)
    game.setPosition(60, 60)
    game.animate = "--animate" in sys.argv
    if game.animate:
        game.mover.start()
    background = "--background" in sys.argv
    if background:
        game.setFlag(Qt.WindowDoesNotAcceptFocus)
    game.show()
    if background:
        from gloss import win32

        win32.send_to_back(int(game.winId()))
    sys.exit(app.exec())
