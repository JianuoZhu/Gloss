"""OneOCR —— Windows 11 截图工具自带的识别引擎（实验性，未随项目测试）。

需要 `uv sync --extra oneocr`，并按 oneocr 包的说明把截图工具安装目录下的
oneocr.dll、oneocr.onemodel、onnxruntime.dll 放到 ~/.config/oneocr/。
这些文件属于微软，Gloss 不附带也不会自动复制它们。
"""

from __future__ import annotations

import numpy as np

from ..types import TextLine
from .base import OcrUnavailable


class OneOcr:
    name = "oneocr"
    font_factor = 0.85

    def __init__(self) -> None:
        try:
            import oneocr
        except ImportError as e:
            raise OcrUnavailable("未安装 oneocr 包：运行 `uv sync --extra oneocr`。") from e
        try:
            self._engine = oneocr.OcrEngine()
        except Exception as e:  # 缺 DLL/模型时 oneocr 抛的异常类型不固定
            raise OcrUnavailable(f"OneOCR 初始化失败（多半是缺少截图工具的模型文件）：{e}") from e

    def recognize(self, bgr: np.ndarray, origin: tuple[int, int] = (0, 0)) -> list[TextLine]:
        res = self._engine.recognize_cv2(bgr)
        lines: list[TextLine] = []
        for line in res.get("lines", []):
            r = line.get("bounding_rect") or {}
            xs = [r.get(f"x{i}", 0) for i in (1, 2, 3, 4)]
            ys = [r.get(f"y{i}", 0) for i in (1, 2, 3, 4)]
            text = (line.get("text") or "").strip()
            if text:
                lines.append(
                    TextLine(text, float(min(xs)), float(min(ys)), float(max(xs) - min(xs)), float(max(ys) - min(ys)), 0.95)
                )
        return lines
