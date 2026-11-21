"""翻译后端的公共部分：接口、提示词、流式输出的增量解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

LANG_NAMES = {
    "auto": "the source language (detect it)",
    "ja": "Japanese",
    "en": "English",
    "ko": "Korean",
    "zh": "Chinese",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "ru": "Russian",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
}


class TranslateError(RuntimeError):
    """翻译失败；消息可以直接显示给用户。"""


@dataclass
class Term:
    src: str
    dst: str
    note: str = ""


@dataclass
class TranslateContext:
    source_lang: str = "auto"
    target_lang: str = "zh-CN"
    glossary: list[Term] = field(default_factory=list)
    game_hint: str = ""  # 预设里写的游戏背景、语气要求
    history: list[tuple[str, str]] = field(default_factory=list)  # 最近的 (原文, 译文)


# on_partial(条目下标, 目前为止的译文, 是否已完成)
PartialCallback = Callable[[int, str, bool], None]


class Translator(Protocol):
    name: str

    def translate(self, items: list[str], ctx: TranslateContext, on_partial: PartialCallback | None = None) -> list[str]:
        """翻译一批文本，返回等长的译文列表。流式后端会边生成边调用 on_partial。"""
        ...


def relevant_terms(terms: list[Term], texts: list[str]) -> list[Term]:
    """只保留在这批原文里出现过的术语，避免把整张术语表塞进每次请求。"""
    blob = "\n".join(texts).lower()
    return [t for t in terms if t.src and t.src.lower() in blob]


def substitute_terms(text: str, terms: list[Term]) -> str:
    """给不支持术语表的机翻用：翻译前直接把术语替换成译名。长词优先，避免被短词截断。"""
    for t in sorted(terms, key=lambda t: len(t.src), reverse=True):
        if t.src and t.dst:
            text = re.sub(re.escape(t.src), t.dst, text, flags=re.IGNORECASE)
    return text


SYSTEM_PROMPT = """You translate on-screen text from video games in real time. The text was captured by OCR, \
so it may contain small recognition errors; silently correct obvious ones.

Input: numbered lines in the form `N| text`. Each line is one independent piece of on-screen text \
(a line of dialogue, a menu item, a quest description, a UI label).

Output: one line per input line, in the same order, in the form `N| translation`. Nothing else: \
no explanations, no notes, no blank lines, no code fences.

Rules:
- Translate into {target} from {source}. Keep the register of the original: dialogue stays spoken and natural, \
UI labels stay short.
- Each translation stays on a single line, however long the original is.
- Follow the glossary exactly when a source term appears.
- Keep numbers, placeholders, key names (e.g. [E], LB, F1) and inline symbols unchanged.
- A line that is already in {target}, or is not translatable text (stray symbols, OCR noise), is returned unchanged.
- Earlier lines given as context are for consistency only; do not translate them again."""


def build_system_prompt(ctx: TranslateContext) -> str:
    prompt = SYSTEM_PROMPT.format(
        target=LANG_NAMES.get(ctx.target_lang, ctx.target_lang),
        source=LANG_NAMES.get(ctx.source_lang, ctx.source_lang),
    )
    if ctx.game_hint.strip():
        prompt += "\n\nAbout this game (from the user):\n" + ctx.game_hint.strip()
    return prompt


def build_user_prompt(items: list[str], ctx: TranslateContext) -> str:
    parts: list[str] = []
    terms = relevant_terms(ctx.glossary, items)
    if terms:
        rows = "\n".join(f"{t.src} => {t.dst}" + (f"  ({t.note})" if t.note else "") for t in terms)
        parts.append(f"<glossary>\n{rows}\n</glossary>")
    if ctx.history:
        rows = "\n".join(f"{s} => {d}" for s, d in ctx.history[-6:])
        parts.append(f"<earlier_lines>\n{rows}\n</earlier_lines>")
    rows = "\n".join(f"{i + 1}| {' '.join(t.split())}" for i, t in enumerate(items))
    parts.append(f"<lines>\n{rows}\n</lines>")
    return "\n\n".join(parts)


_LINE_RE = re.compile(r"^\s*(\d+)\s*[|｜]\s?(.*)$")


class NumberedStreamParser:
    """增量解析 `N| 译文` 格式的流式输出。

    每来一段文本就 feed 一次；已经出现的条目（包括还没写完的最后一行）会通过回调报出来，
    这样界面可以逐字显示。
    """

    def __init__(self, count: int, on_partial: PartialCallback | None = None) -> None:
        self.results: list[str] = [""] * count
        self._done = [False] * count
        self._on_partial = on_partial
        self._buf = ""

    def feed(self, chunk: str) -> None:
        self._buf += chunk
        *complete, tail = self._buf.split("\n")
        for line in complete:
            self._emit(line, final=True)
        self._buf = tail
        self._emit(tail, final=False)

    def finish(self) -> list[str]:
        self._emit(self._buf, final=True)
        self._buf = ""
        return self.results

    def _emit(self, line: str, final: bool) -> None:
        m = _LINE_RE.match(line)
        if not m:
            return
        idx = int(m.group(1)) - 1
        if not 0 <= idx < len(self.results) or self._done[idx]:
            return
        text = m.group(2).strip()
        if not final and not text:
            return
        self.results[idx] = text
        self._done[idx] = final
        if self._on_partial:
            self._on_partial(idx, text, final)
