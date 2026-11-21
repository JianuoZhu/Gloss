"""自检：不开窗口给人看，只确认各个部件都能加载、能干活，把结果写成 JSON。

用法：Gloss.exe --selftest <结果.json>      （源码运行时：python -m gloss --selftest <结果.json>）
主要用来验证打包出来的程序没有漏掉文件：界面文件、OCR 模型、各个原生库。
用的是临时配置，不碰 %APPDATA%\\Gloss 里的真实设置，也不注册全局快捷键。
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path


def run(out_path: str) -> int:
    result: dict = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)), "steps": {}}

    def step(name: str, fn) -> bool:
        try:
            result["steps"][name] = fn()
            return True
        except Exception:
            result["steps"][name] = "FAILED: " + traceback.format_exc(limit=4)
            return False

    def check_ocr():
        import cv2
        import numpy as np

        from .ocr import create_engine

        img = np.full((160, 760, 3), 245, np.uint8)
        cv2.putText(img, "Quit to Desktop 2026", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (20, 20, 20), 4, cv2.LINE_AA)
        lines = create_engine("rapid", "auto").recognize(img)
        text = " ".join(ln.text for ln in lines)
        if "Desktop" not in text:
            raise RuntimeError(f"识别结果不对：{text!r}")
        return text

    def check_windows_ocr():
        from .ocr.windows import available_languages

        return available_languages()

    def check_native():
        import ctranslate2
        import onnxruntime
        import sentencepiece
        import windows_capture  # noqa: F401

        return {"onnxruntime": onnxruntime.__version__, "ctranslate2": ctranslate2.__version__, "sentencepiece": sentencepiece.__version__}

    def check_backends():
        from .translate import ENGINES, create_translator

        create_translator({"provider": "google"})
        import anthropic  # noqa: F401

        return len(ENGINES)

    def check_ui():
        from PySide6.QtCore import QTimer

        from .app import App
        from .config import Store

        store = Store(Path(tempfile.mkdtemp(prefix="gloss-selftest-")))
        app = App(store, hotkeys=False, overlay_on_top=False)
        app.main.setProperty("visible", False)
        QTimer.singleShot(800, app.qt.quit)
        app.run()
        return {"profiles": sorted(store.profiles), "theme": app.backend.themeName, "windows": len(app.backend.windows) >= 0}

    ok = [step("native libraries", check_native), step("ocr (RapidOCR)", check_ocr), step("windows ocr languages", check_windows_ocr),
          step("translation backends", check_backends), step("user interface", check_ui)]
    result["ok"] = all(ok)
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if result["ok"] else 1
