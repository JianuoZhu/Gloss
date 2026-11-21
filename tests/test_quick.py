"""快捷键、临时翻译、待命模式、识别范围切换。"""

from __future__ import annotations

import copy
import time
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

from gloss import app as app_mod
from gloss import hotkeys
from gloss import pipeline as pipeline_mod
from gloss.app import Backend
from gloss.config import DEFAULT_PROFILE, DEFAULT_SETTINGS, Store
from gloss.pipeline import Pipeline
from gloss.types import TextLine

APP = QCoreApplication.instance() or QCoreApplication([])
GAME = {"hwnd": 101, "title": "Tales of Something", "exe": "tales.exe", "w": 1280, "h": 720, "label": "A"}

# Qt 的按键码和修饰键位
CTRL, ALT, SHIFT = 0x04000000, 0x08000000, 0x02000000
KEY_T, KEY_F9, KEY_G = 0x54, 0x01000038, 0x47


# ---------------------------------------------------------------- 快捷键的换算
def test_hotkey_parse_and_format():
    assert hotkeys.parse("Ctrl+Alt+T") == (0x2 | 0x1, 0x54)
    assert hotkeys.parse("F9") == (0, 0x78)
    assert hotkeys.parse("Ctrl+Shift+`") == (0x2 | 0x4, 0xC0)
    assert hotkeys.parse("") is None and hotkeys.parse("Ctrl+Banana") is None
    assert hotkeys.from_qt(KEY_T, CTRL | ALT) == "Ctrl+Alt+T"
    assert hotkeys.from_qt(KEY_F9, 0) == "F9"  # 功能键可以单独用
    assert hotkeys.from_qt(KEY_T, 0) is None  # 单独一个字母会把打字全截走
    assert hotkeys.from_qt(KEY_T, SHIFT) is None
    for action, _, default in hotkeys.ACTIONS:
        assert hotkeys.parse(default) is not None, action
    assert len({keys for _, _, keys in hotkeys.ACTIONS}) == len(hotkeys.ACTIONS)  # 默认按键互不重复


# ---------------------------------------------------------------- Backend
class FakePipeline:
    made: list = []

    def __init__(self, hwnd, settings, profile, cache, continuous=True):
        self.profile, self.cache, self.continuous = profile, cache, continuous
        self.snaps, self.scopes, self.has_snapshot, self.cleared = [], [], False, 0
        for name in ("blocksSynced", "blockUpdated", "geometryChanged", "statsChanged", "statusChanged",
                     "captureModeChanged", "stopped", "snapshotDone"):
            setattr(self, name, SimpleNamespace(connect=lambda *a, **k: None))
        FakePipeline.made.append(self)

    def start(self): ...
    def stop(self): ...
    def join(self, timeout=0): ...
    def set_regions(self, regions): ...

    def set_continuous(self, on):
        self.continuous = on

    def set_scope(self, scope):
        self.scopes.append(scope)

    def request_snapshot(self, region, hold):
        self.snaps.append((region, hold))
        self.has_snapshot = True

    def clear_snapshot(self):
        self.has_snapshot = False
        self.cleared += 1


@pytest.fixture
def backend(tmp_path, monkeypatch):
    FakePipeline.made = []
    monkeypatch.setattr(app_mod, "Pipeline", FakePipeline)
    monkeypatch.setattr(app_mod.win32, "is_window", lambda hwnd: True)
    monkeypatch.setattr(app_mod.win32, "foreground_window", lambda: 0)
    monkeypatch.setattr(app_mod.win32, "client_rect", lambda hwnd: (0, 0, 1280, 720))
    b = Backend(Store(tmp_path))
    b._windows = [GAME]
    b.selectWindow(101)
    yield b
    b.shutdown()


def test_quick_translate_loads_models_once_and_stays_on_standby(backend):
    b = backend
    b.quickFull()
    (p,) = FakePipeline.made
    assert p.continuous is False and p.snaps == [(None, 10.0)]
    assert b.standby and not b.running
    assert "临时翻译整个窗口" in b.toast

    p.has_snapshot = False  # 译文到时间消失了
    b.snapRegion(0.1, 0.2, 0.3, 0.4)  # 再来一次：不重新加载模型
    assert len(FakePipeline.made) == 1 and p.snaps[-1] == ([0.1, 0.2, 0.3, 0.4], 10.0)


def test_pressing_quick_translate_again_clears_it(backend):
    backend.quickFull()
    backend.quickFull()
    (p,) = FakePipeline.made
    assert p.cleared == 1 and len(p.snaps) == 1


def test_start_from_standby_reuses_the_loaded_pipeline(backend):
    b = backend
    b.quickFull()
    b.start()
    (p,) = FakePipeline.made  # 没有新建管线
    assert p.continuous is True and b.running and not b.standby
    b.stop()
    assert not b.running and not b.standby


def test_standby_unloads_after_a_while_but_not_while_translating(backend):
    b = backend
    b.quickFull()
    b._standby_expired()
    assert not b.standby and b._pipeline is None
    b.start()
    b._standby_expired()  # 连续翻译时不卸
    assert b.running


def test_hold_time_comes_from_settings(backend):
    backend.setSetting("quick.hold_s", 0)
    assert not backend._restart_timer.isActive()  # 改这个不用重新加载模型
    backend.quickFull()
    assert FakePipeline.made[0].snaps == [(None, 0.0)]


def test_scope_toggle(backend):
    b = backend
    asked = []
    b.regionPickerRequested.connect(lambda: asked.append(1))
    b.toggleScope()  # 还没有固定区域：直接打开区域编辑器
    assert asked == [1] and "先框选" in b.toast

    b.setRegions([[0.1, 0.6, 0.8, 0.3]])
    b.start()
    p = FakePipeline.made[0]
    b.toggleScope()
    assert b.profile["scope"] == "full" and p.scopes == ["full"] and "整个窗口" in b.toast
    assert b.profile["regions"] == [[0.1, 0.6, 0.8, 0.3]]  # 区域留着，没删
    b.toggleScope()
    assert b.profile["scope"] == "regions" and p.scopes == ["full", "regions"] and "固定区域（1 个）" in b.toast
    assert len(FakePipeline.made) == 1  # 全程没有重启


def test_quick_full_is_a_noop_when_already_translating_the_whole_window(backend):
    backend.start()
    backend.quickFull()
    assert FakePipeline.made[0].snaps == [] and "已经在翻译整个窗口" in backend.toast


def test_hotkeys_can_be_rebound_and_are_saved(backend, tmp_path):
    b = backend
    changed = []
    b.hotkeysChanged.connect(lambda: changed.append(1))
    assert b.setHotkey("snap_full", KEY_F9, 0) and b.hotkeys[3]["keys"] == "F9"
    assert not b.setHotkey("snap_region", KEY_F9, 0)  # 已经被上一个动作用了
    assert not b.setHotkey("toggle", KEY_G, 0)  # 不适合做全局快捷键
    assert b.setHotkey("overlay", 0, 0) and b.hotkeys[1]["keys"] == ""  # 清除
    assert len(changed) == 2
    assert Store(tmp_path).settings["hotkeys"]["snap_full"] == "F9"
    b.resetHotkey("snap_full")
    assert b.hotkeys[3]["keys"] == "Ctrl+Alt+F"
    b.set_hotkey_conflicts({"toggle"})
    assert b.hotkeys[0]["conflict"] is True


# ---------------------------------------------------------------- 管线
class FakeEngine:
    font_factor = 0.7

    def __init__(self, lines):
        self.lines, self.calls = lines, []

    def recognize(self, bgr, origin=(0, 0)):
        self.calls.append((bgr.shape[:2], origin))
        return [copy.copy(ln) for ln in self.lines]


class FakeTranslator:
    def translate(self, items, ctx, on_partial=None):
        return [f"译:{t}" for t in items]


def make_pipeline(lines, **profile_over):
    profile = copy.deepcopy(DEFAULT_PROFILE)
    profile.update(profile_over)
    p = Pipeline(0, copy.deepcopy(DEFAULT_SETTINGS), profile, continuous=False)
    p._engine, p._translator = FakeEngine(lines), FakeTranslator()
    synced = []
    p.blocksSynced.connect(synced.append)
    return p, synced


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        APP.processEvents()
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError("等待超时")


FRAME = np.zeros((900, 1600, 3), np.uint8)


def test_scope_decides_which_regions_are_recognized():
    p, _ = make_pipeline([], regions=[[0.1, 0.6, 0.8, 0.3]])
    assert [(r.x, r.y, r.w, r.h) for r in p._rois(1600, 900)] == [(160, 540, 1280, 270)]
    p.set_scope("full")
    assert [(r.x, r.y, r.w, r.h) for r in p._rois(1600, 900)] == [(0, 0, 1600, 900)]
    p.set_scope("regions")
    p.set_regions([])  # 选了固定区域但一个都没有：等于整个窗口
    assert len(p._rois(1600, 900)) == 1 and p._rois(1600, 900)[0].w == 1600


def test_snapshot_translates_once_and_expires():
    p, synced = make_pipeline([TextLine("Quit to Desktop", 20, 10, 270, 48, 0.99)])
    counts = []
    p.snapshotDone.connect(counts.append)
    p._do_snapshot(FRAME, [0.5, 0.5, 0.25, 0.2], 10.0)
    assert p._engine.calls == [((180, 400), (800, 450))]  # 只识别框出来的那一块
    wait_for(lambda: counts == [1])
    (view,) = synced[-1]
    assert view["id"].startswith("s") and (view["x"], view["y"]) == (820, 460)  # 坐标换回了整个画面
    wait_for(lambda: all(b.final for b in p._snap_blocks.values()))
    assert next(iter(p._snap_blocks.values())).translation == "译:Quit to Desktop"
    assert p.has_snapshot

    p.clear_snapshot()
    assert synced[-1] == [] and not p.has_snapshot


def test_snapshot_does_not_duplicate_what_continuous_translation_already_shows():
    p, synced = make_pipeline([TextLine("Quit to Desktop", 20, 10, 270, 48, 0.99)])
    p._do_snapshot(FRAME, None, 10.0)
    first = dict(p._snap_blocks)
    p._blocks, p._snap_blocks = first, {}  # 假装这一块现在由连续翻译显示着
    p._do_snapshot(FRAME, None, 10.0)
    assert p._snap_blocks == {} and len(synced[-1]) == 1
