"""OCR 引擎。统一接口：recognize(bgr 图像) -> list[TextLine]。"""

from __future__ import annotations

from .base import OcrEngine, OcrUnavailable

ENGINES = {
    "rapid": "RapidOCR（PP-OCRv6，中日英通吃）",
    "windows": "Windows 自带 OCR（最快，需系统语言包）",
    "oneocr": "OneOCR（截图工具引擎，实验性）",
}


def create_engine(name: str, source_lang: str = "auto", **opts) -> OcrEngine:
    """按名字创建引擎；引擎不可用时抛 OcrUnavailable，消息可直接显示给用户。"""
    if name == "windows":
        from .windows import WindowsOcr

        return WindowsOcr(source_lang)
    if name == "oneocr":
        from .oneocr import OneOcr

        return OneOcr()
    from .rapid import RapidOcr

    return RapidOcr(source_lang, **opts)


__all__ = ["ENGINES", "OcrEngine", "OcrUnavailable", "create_engine"]
