"""Windows.Media.Ocr —— 系统自带，速度最快，但只能识别已安装语言包的语言。"""

from __future__ import annotations

import asyncio

import cv2
import numpy as np

from ..types import TextLine
from .base import OcrUnavailable

_LANG_PREFIX = {"ja": "ja", "en": "en", "zh": "zh-Hans", "ko": "ko", "ru": "ru", "fr": "fr", "de": "de", "es": "es"}
_CJK = ("ja", "zh", "ko")


def available_languages() -> list[str]:
    from winrt.windows.media.ocr import OcrEngine

    return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]


class WindowsOcr:
    name = "windows"
    font_factor = 1.25  # Windows OCR 的行框紧贴字形，比字号小

    def __init__(self, source_lang: str = "auto") -> None:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        tags = available_languages()
        if source_lang == "auto":
            engine = OcrEngine.try_create_from_user_profile_languages()
            self._cjk = False
        else:
            prefix = _LANG_PREFIX.get(source_lang, source_lang)
            tag = next((t for t in tags if t.lower().startswith(prefix.lower())), None)
            if tag is None:
                raise OcrUnavailable(
                    f"系统没有安装「{source_lang}」的 OCR 语言包（已安装：{', '.join(tags) or '无'}）。"
                    "可在 Windows 设置 → 时间和语言 → 语言 中添加，或改用 RapidOCR。"
                )
            engine = OcrEngine.try_create_from_language(Language(tag))
            self._cjk = source_lang in _CJK
        if engine is None:
            raise OcrUnavailable("无法创建 Windows OCR 引擎。")
        self._engine = engine
        self._max = int(OcrEngine.max_image_dimension)
        self._loop = asyncio.new_event_loop()

    def recognize(self, bgr: np.ndarray, origin: tuple[int, int] = (0, 0)) -> list[TextLine]:
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.storage.streams import DataWriter

        h, w = bgr.shape[:2]
        if max(h, w) > self._max:
            return []
        bgra = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
        writer = DataWriter()
        writer.write_bytes(bgra.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8, w, h)

        async def run():
            return await self._engine.recognize_async(bitmap)

        result = self._loop.run_until_complete(run())
        lines: list[TextLine] = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            x0 = min(wd.bounding_rect.x for wd in words)
            y0 = min(wd.bounding_rect.y for wd in words)
            x1 = max(wd.bounding_rect.x + wd.bounding_rect.width for wd in words)
            y1 = max(wd.bounding_rect.y + wd.bounding_rect.height for wd in words)
            # 中日韩文本里 Windows OCR 会在每个字之间插空格
            text = "".join(wd.text for wd in words) if self._cjk else line.text
            if text.strip():
                lines.append(TextLine(text.strip(), float(x0), float(y0), float(x1 - x0), float(y1 - y0), 0.9))
        return lines
