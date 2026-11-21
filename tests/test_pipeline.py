"""管线里"块的维护"这一段的测试：不开窗口、不跑 OCR，直接喂识别结果。"""

from __future__ import annotations

import copy
import time
from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import QCoreApplication

from gloss import pipeline as pipeline_mod
from gloss.config import DEFAULT_PROFILE, DEFAULT_SETTINGS
from gloss.pipeline import Pipeline, _Roi
from gloss.translate.base import TranslateError
from gloss.types import TextLine

FRAME = np.zeros((900, 1600, 3), np.uint8)
# 翻译在工作线程里完成，它发的信号要靠主线程的事件循环送达
APP = QCoreApplication.instance() or QCoreApplication([])


class FakeTranslator:
    def __init__(self, same: bool = False, fail_first: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.contexts = []
        self.same, self.fail_first = same, fail_first

    def translate(self, items, ctx, on_partial=None):
        self.calls.append(list(items))
        self.contexts.append(ctx)
        if self.fail_first and len(self.calls) == 1:
            raise TranslateError("boom")
        return [t if self.same else f"译:{t}" for t in items]


def make(translator, **profile_over) -> tuple[Pipeline, list]:
    profile = copy.deepcopy(DEFAULT_PROFILE)
    profile.update(profile_over)
    p = Pipeline(0, copy.deepcopy(DEFAULT_SETTINGS), profile)
    p._engine = SimpleNamespace(font_factor=0.7)
    p._translator = translator
    synced: list = []
    p.blocksSynced.connect(synced.append)
    return p, synced


def feed(p: Pipeline, lines: list[TextLine], stable: bool = True) -> None:
    roi = _Roi(0, 0, 1600, 900)
    roi.lines = lines
    p._update_blocks(FRAME, [roi], stable)


def wait_for(cond, timeout: float = 3.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        APP.processEvents()
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError("等待超时")


def line(text: str, x=160, y=700, w=None, h=48) -> TextLine:
    return TextLine(text, x, y, w or 26 * len(text), h, 0.99)


def test_new_block_translated_once_and_cached():
    tr = FakeTranslator()
    p, synced = make(tr, source_lang="ja")
    feed(p, [line("準備ができたら、北の門で待ち合わせましょう。")])
    wait_for(lambda: any(b.final for b in p._blocks.values()))
    feed(p, [line("準備ができたら、北の門で待ち合わせましょう。")])  # 同一句再识别一次
    time.sleep(0.1)
    assert tr.calls == [["準備ができたら、北の門で待ち合わせましょう。"]]
    assert synced[-1][0]["text"] == "译:準備ができたら、北の門で待ち合わせましょう。"

    # 这句话消失后再出现：直接用缓存，不再请求
    feed(p, [])
    feed(p, [line("準備ができたら、北の門で待ち合わせましょう。")])
    assert len(tr.calls) == 1
    assert synced[-1][0]["final"] is True


def test_typewriter_text_keeps_block_and_retranslates_after_pause(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "_GROW_DEBOUNCE", 0.15)
    tr = FakeTranslator()
    p, synced = make(tr, source_lang="ja")
    feed(p, [line("わかった。装備を整えて")])
    wait_for(lambda: len(tr.calls) == 1)
    first_id = synced[-1][0]["id"]

    feed(p, [line("わかった。装備を整えてからすぐに向かうよ。")])  # 同一行继续打字
    assert synced[-1][0]["id"] == first_id  # 还是同一个块，界面上不会闪
    assert len(tr.calls) == 1  # 没有立刻请求
    assert p._deferred_at > 0

    time.sleep(0.2)
    p._dispatch(stable=True)  # 主循环到点后会调用它
    wait_for(lambda: len(tr.calls) == 2)
    assert tr.calls[1] == ["わかった。装備を整えてからすぐに向かうよ。"]
    wait_for(lambda: all(b.final for b in p._blocks.values()))
    (block,) = p._blocks.values()
    assert block.translation == "译:わかった。装備を整えてからすぐに向かうよ。"


def test_ocr_jitter_does_not_retranslate():
    tr = FakeTranslator()
    p, synced = make(tr)
    feed(p, [line("Quit to Desktop", w=270)])
    wait_for(lambda: len(tr.calls) == 1)
    feed(p, [line("Quit to Desktap", w=272)])
    time.sleep(0.1)
    assert len(tr.calls) == 1
    assert len(synced[-1]) == 1


def test_unchanged_translation_is_not_shown():
    tr = FakeTranslator(same=True)
    p, synced = make(tr)
    feed(p, [line("Settings", w=150)])
    wait_for(lambda: synced and synced[-1] == [])  # 译文和原文一样，没必要盖一层


def test_unstable_pass_needs_two_sightings():
    tr = FakeTranslator()
    p, _ = make(tr)
    feed(p, [line("Continue", w=160)], stable=False)
    time.sleep(0.1)
    assert tr.calls == []  # 画面在动时只见过一次，先不翻
    feed(p, [line("Continue", w=160)], stable=False)
    wait_for(lambda: len(tr.calls) == 1)


def test_filters_and_glossary_reach_translator():
    tr = FakeTranslator()
    p, _ = make(
        tr,
        glossary=[{"src": "Relic", "dst": "圣遗物", "note": ""}],
        prompt="奇幻 RPG",
        filter={"min_conf": 0.6, "min_height": 14, "ignore": ["^FPS"]},
    )
    feed(p, [line("Find the Relic", w=300), line("FPS 60 counter", y=20, w=200), line("tiny text here", y=100, h=9), TextLine("low conf text", 0, 300, 200, 40, 0.3)])
    wait_for(lambda: len(tr.calls) == 1)
    assert tr.calls[0] == ["Find the Relic"]
    ctx = tr.contexts[0]
    assert ctx.glossary[0].dst == "圣遗物" and ctx.game_hint == "奇幻 RPG"


def test_translate_error_is_retried(monkeypatch):
    tr = FakeTranslator(fail_first=True)
    p, _ = make(tr)
    errors = []
    p.statusChanged.connect(lambda level, text: errors.append((level, text)))
    feed(p, [line("Continue", w=160)])
    wait_for(lambda: errors)
    assert errors[0] == ("error", "boom")
    assert p._deferred_at > 0  # 记下了重试时间
    p._retry_at = 0.0
    p._dispatch(stable=True)
    wait_for(lambda: any(b.final for b in p._blocks.values()))
    assert len(tr.calls) == 2
