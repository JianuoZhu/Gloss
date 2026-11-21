"""把控制面板的每一页渲染成 PNG，用来人工检查界面。

用法：python tests/shots.py <输出目录> [翻译后端]
用一份临时配置启动，不会碰 %APPDATA%\\Gloss 里的真实设置，也不注册全局热键。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer

from gloss.app import App
from gloss.config import Store


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    store = Store(Path(tempfile.mkdtemp(prefix="gloss-shots-")))
    if len(sys.argv) > 2:
        store.settings["translator"]["provider"] = sys.argv[2]  # 引擎页显示哪个后端的设置
    store.profiles["default"]["glossary"] = [
        {"src": "アリシア", "dst": "艾莉西亚", "note": "女主角"},
        {"src": "魔導兵器", "dst": "魔导兵器", "note": ""},
        {"src": "Relic", "dst": "圣遗物", "note": "道具类别"},
    ]
    app = App(store, hotkeys=False)
    pages = ["home", "profile", "glossary", "engine"]
    step = {"i": 0}

    def shoot() -> None:
        i = step["i"]
        app.main.grabWindow().save(str(out / f"{pages[i]}.png"))
        step["i"] += 1
        if step["i"] >= len(pages):
            app.qt.quit()
            return
        app.main.setProperty("page", step["i"])
        QTimer.singleShot(700, shoot)

    QTimer.singleShot(900, shoot)
    app.run()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_debug/shots")
