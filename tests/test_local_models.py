"""本地翻译模型后端。提示词的拼法随时能测；真正跑模型的测试只在模型已经下载时执行。"""

from __future__ import annotations

import re

import pytest

from gloss import local_mt
from gloss.translate.base import Term, TranslateContext
from gloss.translate.hymt import build_prompt, resolve_device
from gloss.translate.nllb import guess_language

ZH = TranslateContext(source_lang="auto", target_lang="zh-CN")
HAN = re.compile(r"[一-鿿]")


def test_plain_prompt_uses_official_chinese_template():
    p = build_prompt("Quit  to\nDesktop", ZH)
    assert p == "将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释：\n\nQuit to Desktop"


def test_glossary_prompt_lists_only_terms_that_appear():
    ctx = TranslateContext(target_lang="zh-CN", glossary=[Term("アリシア", "艾莉西亚"), Term("レオン", "莱昂")])
    p = build_prompt("アリシア、準備はいい？", ctx)
    assert p.startswith("参考下面的翻译：\nアリシア 翻译成 艾莉西亚\n\n将以下文本翻译为中文")
    assert "レオン" not in p


def test_background_only_for_sentences_and_never_repeats_the_line_itself():
    ctx = TranslateContext(target_lang="zh-CN", game_hint="奇幻 RPG", history=[("この先は危険だ。引き返したほうがいい。", ""), ("アリシア", "")])
    assert "背景信息" not in build_prompt("アリシア", ctx)  # 短标签不带背景，否则模型会把背景也译出来
    p = build_prompt("この先は危険だ。引き返したほうがいい。", ctx)
    assert "【背景信息】\n奇幻 RPG" in p and p.endswith("【待翻译文本】\nこの先は危険だ。引き返したほうがいい。")
    assert p.count("この先は危険だ") == 1


def test_non_chinese_target_uses_english_template():
    p = build_prompt("こんにちは", TranslateContext(target_lang="en"))
    assert p.startswith("Translate the following text into English.") and p.endswith("\n\nこんにちは")


def test_auto_device_falls_back_to_cpu_when_gpu_is_busy():
    assert resolve_device("auto", 0, busy=True)[:2] == ("cpu", 6)
    assert resolve_device("auto", 4, busy=True)[:2] == ("cpu", 4)  # 用户设过线程数就用用户的
    assert "CPU" in resolve_device("auto", 0, busy=True)[2]
    assert resolve_device("auto", 0, busy=False) == ("auto", 0, "")
    assert resolve_device("auto", 0, busy=None) == ("auto", 0, "")  # 查不到显卡状态时照旧用显卡
    assert resolve_device("Vulkan0", 0, busy=True) == ("Vulkan0", 0, "")  # 用户指定了设备就不替他改


def test_guess_language():
    assert guess_language("準備ができたら") == "ja"
    assert guess_language("안녕하세요") == "ko"
    assert guess_language("设置") == "zh"
    assert guess_language("Привет") == "ru"
    assert guess_language("Settings") == "en"


def test_installed_reflects_files(tmp_path, monkeypatch):
    monkeypatch.setattr(local_mt, "NLLB_DIR", tmp_path)
    assert not local_mt.installed("nllb")
    for name in ("model.bin", "config.json", "shared_vocabulary.txt", "sentencepiece.bpe.model"):
        (tmp_path / name).write_bytes(b"x")
    assert local_mt.installed("nllb")


@pytest.mark.skipif(not local_mt.installed("hymt"), reason="混元模型没有下载")
def test_hymt_translates_and_follows_glossary():
    from gloss.translate.hymt import HyMTTranslator

    tr = HyMTTranslator()
    try:
        ctx = TranslateContext(target_lang="zh-CN", glossary=[Term("アリシア", "艾莉西亚"), Term("魔導兵器", "魔导兵器")])
        partials = []
        out = tr.translate(["アリシア、魔導兵器の封印はもう解けかけている。", "Quit to Desktop", "Settings"], ctx,
                           lambda i, text, final: partials.append(i))
        assert "艾莉西亚" in out[0] and "魔导兵器" in out[0]
        assert all(HAN.search(t) for t in out) and all("\n" not in t for t in out)
        assert set(partials) == {0, 1, 2}  # 每一条都有流式输出
        pid = tr.server.pid
    finally:
        tr.close()
    import psutil

    assert not psutil.pid_exists(pid)  # 关闭后服务进程不能留着


@pytest.mark.skipif(not local_mt.installed("nllb"), reason="NLLB 模型没有下载")
def test_nllb_translates_batch():
    from gloss.translate.nllb import NllbTranslator

    out = NllbTranslator().translate(["Graphics Settings", "準備ができたら、北の門で待ち合わせましょう。"], ZH)
    assert len(out) == 2 and all(HAN.search(t) for t in out)
