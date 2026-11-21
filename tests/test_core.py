from gloss.config import Store, set_path
from gloss.layout import group_lines, normalize, sample_colors, worth_translating
from gloss.translate.base import (
    NumberedStreamParser,
    Term,
    TranslateContext,
    build_user_prompt,
    relevant_terms,
    substitute_terms,
)
from gloss.types import TextLine

import numpy as np


def L(text, x, y, w, h=50):
    return TextLine(text, x, y, w, h, 0.99)


def test_wrapped_paragraph_becomes_one_block():
    lines = [
        L("この先の遺跡には、古代の魔導兵器が眠っていると聞いたわ。", 199, 833, 1100, 52),
        L("準備ができたら、北の門で待ち合わせましょう。", 195, 893, 864, 52),
    ]
    blocks = group_lines(lines)
    assert len(blocks) == 1
    assert blocks[0].multiline
    assert blocks[0].text.startswith("この先") and blocks[0].text.endswith("ましょう。")
    assert "。準備" in blocks[0].text  # 日文行之间不加空格


def test_menu_items_stay_separate():
    lines = [L("New Game", 175, 207, 223), L("Continue", 173, 277, 191), L("Settings", 170, 342, 175, 64), L("Quit to Desktop", 175, 415, 319, 58)]
    assert len(group_lines(lines)) == 4


def test_english_paragraph_joined_with_spaces():
    lines = [L("Find the ancient relic hidden", 1303, 193, 363, 35), L("beneath the northern ruins.", 1304, 233, 352, 36)]
    blocks = group_lines(lines)
    assert len(blocks) == 1
    assert blocks[0].text == "Find the ancient relic hidden beneath the northern ruins."
    assert blocks[0].align == "left"


def test_name_label_not_merged_into_dialogue():
    lines = [L("アリシア", 196, 775, 141, 43), L("この先の遺跡には、古代の魔導兵器が眠っていると聞いたわ。", 199, 833, 1100, 52)]
    assert len(group_lines(lines)) == 2


def test_centered_menu_detected():
    lines = [L("Start", 900, 300, 120), L("Load Game", 860, 380, 200), L("Exit", 915, 460, 90)]
    blocks = group_lines(lines)
    assert [b.align for b in blocks] == ["center"] * 3


def test_worth_translating():
    assert not worth_translating("12 / 30")
    assert not worth_translating("HP")
    assert worth_translating("Settings")
    assert worth_translating("準備ができたら")
    assert not worth_translating("设置")  # 已经是中文
    assert worth_translating("設定", source_lang="ja")  # 明确是日语时纯汉字词也翻


def test_normalize_ignores_spacing_and_width():
    assert normalize("New  Game") == normalize("ｎｅｗ game")


def test_stream_parser_reports_partials_and_finals():
    events = []
    p = NumberedStreamParser(2, lambda i, t, f: events.append((i, t, f)))
    for chunk in ["1| 新", "游戏\n2| 继", "续"]:
        p.feed(chunk)
    assert p.finish() == ["新游戏", "继续"]
    assert (0, "新", False) in events and (0, "新游戏", True) in events
    assert events[-1] == (1, "继续", True)


def test_stream_parser_ignores_junk_and_bad_indexes():
    p = NumberedStreamParser(1)
    p.feed("Here you go:\n7| x\n1｜好的\n")
    assert p.finish() == ["好的"]


def test_glossary_filtering_and_substitution():
    terms = [Term("アリシア", "艾莉西亚"), Term("Relic", "圣遗物"), Term("ドラゴン", "巨龙")]
    hit = relevant_terms(terms, ["アリシアは relic を見つけた"])
    assert [t.dst for t in hit] == ["艾莉西亚", "圣遗物"]
    assert substitute_terms("the Relic of アリシア", hit) == "the 圣遗物 of 艾莉西亚"
    prompt = build_user_prompt(["アリシア"], TranslateContext(glossary=terms))
    assert "アリシア => 艾莉西亚" in prompt and "ドラゴン" not in prompt and "1| アリシア" in prompt


def test_sample_colors_light_text_on_dark():
    img = np.full((60, 300, 3), (52, 34, 28), np.uint8)  # BGR
    img[20:40, 20:280:3] = (240, 240, 240)
    fg, bg = sample_colors(img, 0, 0, 300, 60)
    assert bg == "#1C2234" and fg == "#F0F0F0"


def test_store_profiles_roundtrip(tmp_path):
    store = Store(tmp_path)
    assert set(store.profiles) == {"default"}
    pid = store.new_game_profile("我的游戏", "Game.exe")
    set_path(store.profiles[pid], "display.opacity", 0.5)
    store.profiles[pid]["glossary"].append({"src": "a", "dst": "b", "note": ""})
    store.save_profile(pid)

    again = Store(tmp_path)
    assert again.profiles[pid]["display"]["opacity"] == 0.5
    assert again.profiles[pid]["display"]["mode"] == "inplace"  # 没写的字段取默认值
    assert again.match_profile("game.EXE", "whatever") == pid
    assert again.match_profile("other.exe", "x") is None
    again.delete_profile(pid)
    assert pid not in Store(tmp_path).profiles
