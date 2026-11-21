"""预设是"一个游戏一份"：选中游戏窗口时自动切到它的预设，没有就新建。"""

from __future__ import annotations

import json

from PySide6.QtCore import QCoreApplication

from gloss.app import Backend, BlockModel
from gloss.config import Store
from gloss.placement import ABOVE, BELOW, RIGHT, place_labels

APP = QCoreApplication.instance() or QCoreApplication([])

GAME_A = {"hwnd": 101, "title": "Tales of Something", "exe": "tales.exe", "w": 1280, "h": 720, "label": "A"}
GAME_B = {"hwnd": 102, "title": "Another Game", "exe": "another.exe", "w": 1280, "h": 720, "label": "B"}
NO_EXE = {"hwnd": 103, "title": "Protected Window", "exe": "", "w": 1280, "h": 720, "label": "C"}


def make(tmp_path) -> Backend:
    backend = Backend(Store(tmp_path))
    backend._windows = [GAME_A, GAME_B, NO_EXE]
    return backend


def saved(tmp_path) -> set[str]:
    return {json.loads(p.read_text(encoding="utf-8"))["name"] for p in (tmp_path / "profiles").glob("*.json")}


def test_selecting_a_game_creates_its_own_preset(tmp_path):
    b = make(tmp_path)
    b.selectWindow(101)
    p = b.profile
    assert p["id"] != "default" and p["name"] == "Tales of Something" and p["match"]["exe"] == "tales.exe"
    assert saved(tmp_path) == {"默认"}  # 还没用过，先不存盘


def test_untouched_preset_is_dropped_when_moving_on(tmp_path):
    b = make(tmp_path)
    b.selectWindow(101)
    b.selectWindow(102)
    names = [p["label"] for p in b.profiles]
    assert "Tales of Something" not in names and "Another Game" in names


def test_edited_preset_is_kept_and_reused(tmp_path):
    b = make(tmp_path)
    b.selectWindow(101)
    pid = b.profile["id"]
    b.addRegion(0.1, 0.6, 0.8, 0.3)
    b.terms.add("アリシア", "艾莉西亚", "")
    b.selectWindow(102)  # 换到另一个游戏：它有自己的一份，互不影响
    assert b.profile["regions"] == [] and b.profile["glossary"] == []
    b.selectWindow(101)
    assert b.profile["id"] == pid and len(b.profile["regions"]) == 1 and b.profile["glossary"][0]["dst"] == "艾莉西亚"
    b.shutdown()

    again = Store(tmp_path)  # 重启后还在，并且还认得这个游戏
    assert again.match_profile("TALES.EXE", "whatever") == pid
    assert again.profiles[pid]["glossary"][0]["src"] == "アリシア"
    assert "Another Game" not in {p["name"] for p in again.profiles.values()}


def test_window_without_exe_uses_default(tmp_path):
    b = make(tmp_path)
    b.selectWindow(103)
    assert b.profile["id"] == "default"


def test_legacy_category_templates_are_removed_unless_used(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "default.json").write_text(json.dumps({"id": "default", "name": "通用"}), encoding="utf-8")
    (profiles / "jrpg-dialogue.json").write_text(json.dumps({"id": "jrpg-dialogue", "name": "日式 RPG"}), encoding="utf-8")
    (profiles / "subtitle-en.json").write_text(
        json.dumps({"id": "subtitle-en", "name": "我改过的", "glossary": [{"src": "a", "dst": "b"}]}), encoding="utf-8")
    store = Store(tmp_path)
    assert set(store.profiles) == {"default", "subtitle-en"}  # 用过的那份留着
    assert store.profiles["default"]["name"] == "默认"
    assert not (profiles / "jrpg-dialogue.json").exists()


def test_starting_right_after_picking_a_game_does_not_restart(tmp_path, monkeypatch):
    """选中游戏会切预设，切预设会排一个"稍后重启"。紧接着开始翻译时，这个重启必须作废——否则模型要加载两遍。"""
    from gloss import app as app_mod

    started, live = [], []

    class FakePipeline:
        def __init__(self, hwnd, settings, profile, cache, continuous=True):
            self.profile, self.cache = profile, cache
            started.append(profile["id"])
            for name in ("blocksSynced", "blockUpdated", "geometryChanged", "statsChanged", "statusChanged", "captureModeChanged", "stopped", "snapshotDone"):
                setattr(self, name, type("Sig", (), {"connect": lambda *a, **k: None})())

        def start(self): ...
        def stop(self): ...
        def join(self, timeout=0): ...

        def set_regions(self, regions):
            live.append(regions)

    monkeypatch.setattr(app_mod, "Pipeline", FakePipeline)
    monkeypatch.setattr(app_mod.win32, "is_window", lambda hwnd: True)
    monkeypatch.setattr(app_mod.win32, "foreground_window", lambda: 0)  # 别把测试机上真实的前台窗口当成游戏
    b = make(tmp_path)
    b.selectWindow(101)
    b.start()
    assert not b._restart_timer.isActive()
    assert started == [b.profile["id"]]
    # 运行中改识别区域：直接交给正在跑的管线，不重启（重启要重新加载模型）
    b.addRegion(0.1, 0.6, 0.8, 0.3)
    b.setRegions([[0.1, 0.6, 0.8, 0.3], [0.7, 0.05, 0.25, 0.2]])
    assert live == [[[0.1, 0.6, 0.8, 0.3]], [[0.1, 0.6, 0.8, 0.3], [0.7, 0.05, 0.25, 0.2]]]
    assert not b._restart_timer.isActive() and len(started) == 1
    b.setSetting("ocr.model", "fast")  # 换识别模型这种才需要重启
    assert b._restart_timer.isActive()
    b.shutdown()


def test_regions_are_cleaned_and_saved_to_the_game_preset(tmp_path):
    b = make(tmp_path)
    b.selectWindow(101)
    pid = b.profile["id"]
    b.setRegions([[0.1, 0.6, 0.8, 0.3], [0.9, 0.9, 0.5, 0.5], [0.2, 0.2, 0.001, 0.3]])
    # 第二个超出窗口的部分被裁掉，第三个太窄被丢弃
    assert b.profile["regions"] == [[0.1, 0.6, 0.8, 0.3], [0.9, 0.9, 0.1, 0.1]]
    b.shutdown()
    assert Store(tmp_path).profiles[pid]["regions"] == [[0.1, 0.6, 0.8, 0.3], [0.9, 0.9, 0.1, 0.1]]


def test_usage_monitor_reports_cpu_and_memory(tmp_path):
    b = make(tmp_path)
    sum(i * i for i in range(300_000))  # 烧一点 CPU
    b._measure_usage()
    assert b.usage["mem"] > 20 and b.usage["cores"] >= 0 and 0 <= b.usage["cpu"] <= 100


# ---- 悬浮模式的摆放 ----
def test_label_goes_above_when_free_and_avoids_neighbours():
    menu = [(150, 170, 190, 48, "left"), (150, 228, 160, 48, "left"), (150, 286, 150, 56, "left")]
    sizes = [(100, 44)] * 3
    sides = [s for s, _ in place_labels(menu, sizes, (1600, 900))]
    assert sides[0] == ABOVE  # 第一项上面是空的
    assert sides[1] == RIGHT  # 中间那项上下都是别的菜单项，放右边
    assert sides[2] in (RIGHT, BELOW)


def test_label_stays_inside_the_window():
    (side, x), = place_labels([(1500, 4, 90, 30, "left")], [(160, 36)], (1600, 900))
    assert side == BELOW and x + 160 <= 1600 - 4  # 顶上没地方，右边会出界


def test_previous_side_is_kept_when_about_as_good():
    block = [(400, 400, 300, 40, "left")]
    assert place_labels(block, [(200, 36)], (1600, 900))[0][0] == ABOVE
    assert place_labels(block, [(200, 36)], (1600, 900), previous=[BELOW])[0][0] == BELOW


def test_block_model_places_floating_labels():
    m = BlockModel()
    m.set_viewport(1600, 900)
    m.set_style("float", "", 1.0)
    base = dict(fontPx=30, align="left", fg="#fff", bg="#000", multiline=False, lineCount=1, source="s", final=True)
    m.sync([
        dict(id="a", x=150, y=170, w=190, h=48, text="新游戏", **base),
        dict(id="b", x=150, y=228, w=160, h=48, text="继续", **base),
    ])
    rows = {r["id"]: r for r in m._rows}
    assert rows["a"]["fside"] == ABOVE and rows["b"]["fside"] != ABOVE
    assert rows["a"]["fw"] >= 190
