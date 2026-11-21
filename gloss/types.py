"""管线里流动的数据结构。坐标一律是被捕获画面内的物理像素。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextLine:
    """OCR 识别出的一行文字。"""

    text: str
    x: float
    y: float
    w: float
    h: float
    conf: float = 1.0

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2


@dataclass
class Block:
    """排版上属于同一段的若干行；翻译和显示都以它为单位。"""

    lines: list[TextLine]
    text: str
    x: float
    y: float
    w: float
    h: float
    font_px: float
    align: str = "left"  # left | center | right
    fg: str = "#FFFFFF"
    bg: str = "#101216"
    id: str = ""
    translation: str = ""
    final: bool = False
    seen: int = 1  # 连续被识别到的次数
    missed: int = 0  # 连续没被识别到的次数
    extra: dict = field(default_factory=dict)

    @property
    def multiline(self) -> bool:
        return len(self.lines) > 1

    def to_view(self) -> dict:
        """给界面用的精简表示。"""
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "fontPx": self.font_px,
            "align": self.align,
            "fg": self.fg,
            "bg": self.bg,
            "multiline": self.multiline,
            "lineCount": len(self.lines),
            "source": self.text,
            "text": self.translation,
            "final": self.final,
        }
