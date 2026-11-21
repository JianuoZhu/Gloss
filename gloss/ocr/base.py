from __future__ import annotations

from typing import Protocol

import numpy as np

from ..types import TextLine


class OcrUnavailable(RuntimeError):
    """引擎在这台机器上用不了（缺语言包、缺模型文件等）。"""


class OcrEngine(Protocol):
    name: str

    def recognize(self, bgr: np.ndarray, origin: tuple[int, int] = (0, 0)) -> list[TextLine]:
        """识别一张 BGR 图像，返回的坐标以该图像左上角为原点。

        origin 是这张图左上角在整个画面里的位置，引擎可以用它认出"和上次是同一行"（不用也行）。
        """
        ...
