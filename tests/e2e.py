"""端到端测试：起一个假游戏窗口，让真实管线去识别、翻译，再把悬浮层的画面存下来。

用法：python tests/e2e.py <输出目录> [后端]      后端 = google（默认）| claude | openai_compat
输出：
  frame_N.png      窗口捕获得到的游戏画面
  composite_N.png  游戏画面 + 悬浮层，等同于玩家实际看到的样子
  report.json      每个时间点的文本块、耗时统计

假游戏窗口和悬浮层都压在所有窗口下面，不会打扰正在用电脑的人；窗口捕获不受遮挡影响。
会联网调用所选的翻译后端；用临时配置，不碰真实设置。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QPainter

from gloss import win32
from gloss.app import App
from gloss.capture import WindowCapturer
from gloss.config import Store

HERE = Path(__file__).parent


def find_game(timeout: float = 15.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        for w in win32.list_windows():
            if w["title"] == "Gloss Test Game":
                return w
        time.sleep(0.2)
    raise RuntimeError("假游戏窗口没起来")


def main(out_dir: str, provider: str = "google") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    game = subprocess.Popen([sys.executable, str(HERE / "fake_game.py"), "1600", "900", "--background"])
    report: dict = {"provider": provider, "steps": []}
    try:
        win = find_game()
        store = Store(Path(tempfile.mkdtemp(prefix="gloss-e2e-")))
        store.settings["translator"]["provider"] = provider
        store.profiles["default"]["glossary"] = [
            {"src": "アリシア", "dst": "艾莉西亚", "note": "女主角"},
            {"src": "レオン", "dst": "莱昂", "note": "男主角"},
            {"src": "魔導兵器", "dst": "魔导兵器", "note": ""},
        ]
        app = App(store, hotkeys=False, overlay_on_top=False)
        app.main.setProperty("visible", False)
        backend = app.backend
        backend.refreshWindows()
        backend.selectWindow(win["hwnd"])
        backend.start()
        cap = WindowCapturer(win["hwnd"])

        def snap(name: str) -> None:
            shot = np.ascontiguousarray(cap.grab())
            h, w = shot.shape[:2]
            frame = QImage(shot.data, w, h, w * 3, QImage.Format_BGR888).convertToFormat(QImage.Format_RGB32)
            frame.save(str(out / f"frame_{name}.png"))
            layer = app.overlay.grabWindow()
            painter = QPainter(frame)
            painter.drawImage(frame.rect(), layer)
            painter.end()
            frame.save(str(out / f"composite_{name}.png"))
            rows = [{k: r[k] for k in ("source", "text", "final", "align", "lineCount", "fontPx")} for r in backend.blocks._rows]
            report["steps"].append(
                {"name": name, "status": [backend.statusLevel, backend.statusText], "stats": dict(backend.stats), "blocks": rows}
            )

        def finish() -> None:
            snap("4_region")
            app.qt.quit()

        def to_region() -> None:
            snap("3_subtitle")
            backend.addRegion(0.05, 0.66, 0.9, 0.32)  # 只识别底部对话框；管线会自动重启
            QTimer.singleShot(4000, finish)

        def to_subtitle() -> None:
            snap("2b_float")
            backend.setProfile("display.mode", "subtitle")
            QTimer.singleShot(1500, to_region)

        def to_float() -> None:
            snap("2_next_line")
            backend.setProfile("display.mode", "float")
            QTimer.singleShot(1500, to_subtitle)

        QTimer.singleShot(9000, lambda: snap("1_first"))  # 留出加载 OCR 和翻译模型的时间
        QTimer.singleShot(16000, to_float)
        app.run()
    finally:
        game.kill()
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_debug/e2e", sys.argv[2] if len(sys.argv) > 2 else "google")
