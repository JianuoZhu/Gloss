"""界面与管线之间的胶水：暴露给 QML 的 Backend、悬浮层的数据模型、窗口和热键管理。"""

from __future__ import annotations

import copy
import ctypes
import math
import sys
import threading
import time

import psutil
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QAbstractNativeEventFilter,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from . import hotkeys, local_mt, win32
from . import hotkeys as hotkeys_mod  # App.__init__ 有个同名参数 hotkeys
from .config import Store, set_path
from .ocr import ENGINES
from .placement import place_labels
from .pipeline import Pipeline
from .translate.registry import BY_ID, ENGINES as TRANSLATE_ENGINES, VERIFIED_TEXT

UI_DIR = Path(__file__).parent / "ui"

SOURCE_LANGS = [
    ("auto", "自动检测"), ("ja", "日语"), ("en", "英语"), ("ko", "韩语"), ("zh", "中文"),
    ("ru", "俄语"), ("fr", "法语"), ("de", "德语"), ("es", "西班牙语"),
]
TARGET_LANGS = [("zh-CN", "简体中文"), ("zh-TW", "繁體中文"), ("en", "English"), ("ja", "日本語"), ("ko", "한국어")]

STANDBY_MS = 180_000  # 待命（只做临时翻译）这么久没再用，就把模型卸掉


def _options(pairs) -> list[dict]:
    return [{"value": v, "label": label} for v, label in pairs]


class BlockModel(QAbstractListModel):
    """悬浮层上的文本块。按 id 增量更新，这样没变的块不会重建、不会闪。"""

    ROLES = ["id", "bx", "by", "bw", "bh", "fontPx", "align", "fg", "bg", "multiline", "lineCount", "source", "text", "final",
             "leaving", "fside", "fx", "fw"]  # 最后三个是悬浮模式下标签放哪一侧、x 坐标、最大宽度
    _KEYMAP = {"bx": "x", "by": "y", "bw": "w", "bh": "h"}
    LEAVE_MS = 200

    boundsChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self._bounds = (0.0, 0.0, ())
        self._mode, self._font_family, self._font_scale = "inplace", "Microsoft YaHei UI", 1.0
        self._viewport = (0.0, 0.0)
        self._placing = False
        for sig in (self.rowsInserted, self.rowsRemoved, self.modelReset, self.dataChanged):
            sig.connect(self._update_bounds)

    def roleNames(self):
        return {Qt.UserRole + i: name.encode() for i, name in enumerate(self.ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        i = role - Qt.UserRole
        return self._rows[index.row()].get(self.ROLES[i]) if 0 <= i < len(self.ROLES) else None

    # 字幕条只显示最近出现的几句（同一批出现的算一起），并且要知道这几句原文占了哪一段高度，好躲开它
    SUBTITLE_MAX = 3

    def _update_bounds(self, *_) -> None:
        shown = [r for r in self._rows if r["text"] and not r["leaving"]]
        if shown:
            newest = max(r.get("_t", 0.0) for r in shown)
            recent = sorted((r for r in shown if newest - r.get("_t", 0.0) <= 1.5), key=lambda r: -r.get("_t", 0.0))
            shown = sorted(recent[: self.SUBTITLE_MAX], key=lambda r: (r["by"], r["bx"]))
        bounds = (
            min((r["by"] for r in shown), default=0.0),
            max((r["by"] + r["bh"] for r in shown), default=0.0),
            tuple(r["text"] for r in shown),
        )
        if bounds != self._bounds:
            self._bounds = bounds
            self.boundsChanged.emit()
        if self._mode == "float":
            self._place_floats()

    # ---- 悬浮模式：算每个译文标签放在原文的哪一侧 ----
    def set_style(self, mode: str, font_family: str, font_scale: float) -> None:
        self._mode, self._font_family, self._font_scale = mode, font_family or "Microsoft YaHei UI", font_scale or 1.0
        self._update_bounds()

    def set_viewport(self, w: float, h: float) -> None:
        self._viewport = (float(w), float(h))
        self._update_bounds()

    def _text_width(self, text: str, px: float) -> float:
        # 没有界面环境（单元测试）时按字符宽度估算。instance() 可能返回一个不带界面的 QCoreApplication，
        # 那种情况下去量字体会直接崩溃，所以要看类型
        if not isinstance(QGuiApplication.instance(), QGuiApplication):
            return sum(1.0 if ord(c) > 0x2E7F else 0.55 for c in text) * px
        font = QFont(self._font_family)
        font.setPixelSize(max(1, round(px)))
        font.setWeight(QFont.Weight.Medium)
        return QFontMetricsF(font).horizontalAdvance(text)

    def _place_floats(self) -> None:
        if self._placing:
            return  # 下面写回位置会再触发一次本函数
        self._placing = True
        try:
            rows = [i for i, r in enumerate(self._rows) if r["text"] and not r["leaving"]]
            blocks, sizes, widths = [], [], []
            for i in rows:
                r = self._rows[i]
                px = max(10.0, r["fontPx"] * self._font_scale * 0.86)  # 和 Overlay.qml 里标签的字号、内边距保持一致
                pad_h, pad_v = round(px * 0.55), round(px * 0.28)
                max_w = max(r["bw"], 14 * px)
                if self._viewport[0] > 0:
                    max_w = min(max_w, self._viewport[0] - 8)
                inner = max(40.0, max_w - 2 * pad_h)
                text_w = self._text_width(r["text"], px)
                lines = max(1, math.ceil(text_w / inner))
                blocks.append((r["bx"], r["by"], r["bw"], r["bh"], r["align"]))
                sizes.append((min(text_w, inner) + 2 * pad_h, lines * px * 1.45 + 2 * pad_v))
                widths.append(max_w)
            placed = place_labels(blocks, sizes, self._viewport, [self._rows[i].get("_side") for i in rows])
            for i, (side, x), max_w in zip(rows, placed, widths):
                self._rows[i]["_side"] = side
                self._set(i, fside=side, fx=x, fw=max_w)
        finally:
            self._placing = False

    @Property("QVariantList", notify=boundsChanged)
    def subtitleLines(self):
        return list(self._bounds[2])

    @Property(float, notify=boundsChanged)
    def minY(self):
        return self._bounds[0]

    @Property(float, notify=boundsChanged)
    def maxY(self):
        return self._bounds[1]

    @Property(int, notify=boundsChanged)
    def shownCount(self):
        return len(self._bounds[2])

    def _find(self, bid: str) -> int:
        return next((i for i, r in enumerate(self._rows) if r["id"] == bid), -1)

    def _set(self, row: int, **values) -> None:
        changed = []
        if values.get("text") and not self._rows[row].get("text"):
            self._rows[row]["_t"] = time.monotonic()  # 译文第一次出现的时间，字幕条按它判断"最近"
        for k, v in values.items():
            if self._rows[row].get(k) != v:
                self._rows[row][k] = v
                changed.append(Qt.UserRole + self.ROLES.index(k))
        if changed:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, changed)

    @Slot(list)
    def sync(self, views: list) -> None:
        incoming = {v["id"]: v for v in views}
        for row, r in enumerate(self._rows):
            v = incoming.pop(r["id"], None)
            if v is None:
                if not r["leaving"]:
                    self._set(row, leaving=True)
                    r["_gone_at"] = time.monotonic()
                continue
            values = {role: v[self._KEYMAP.get(role, role)] for role in ("bx", "by", "bw", "bh", "fontPx", "align", "multiline", "lineCount")}
            values["leaving"] = False
            # 流式译文可能比这次同步新，只在同步带来了定稿或本地还没有文字时才覆盖
            if v["text"] and (v["final"] or not r["text"]):
                values.update(text=v["text"], final=v["final"])
            self._set(row, **values)
        for v in incoming.values():
            row = {role: v.get(self._KEYMAP.get(role, role)) for role in self.ROLES}
            row["leaving"] = False
            row.update(fside=0, fx=row["bx"], fw=row["bw"])
            row["_t"] = time.monotonic() if row["text"] else 0.0
            self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
            self._rows.append(row)
            self.endInsertRows()
        if any(r["leaving"] for r in self._rows):
            QTimer.singleShot(self.LEAVE_MS + 30, self._purge)

    def _purge(self) -> None:
        now = time.monotonic()
        for row in range(len(self._rows) - 1, -1, -1):
            r = self._rows[row]
            if r["leaving"] and now - r.get("_gone_at", 0) >= self.LEAVE_MS / 1000:
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._rows[row]
                self.endRemoveRows()

    @Slot(str, str, bool)
    def update(self, bid: str, text: str, final: bool) -> None:
        row = self._find(bid)
        if row >= 0:
            self._set(row, text=text, final=final)

    def clear(self) -> None:
        self.beginResetModel()
        self._rows = []
        self.endResetModel()


class TermModel(QAbstractListModel):
    """当前预设的术语表。直接读写预设里的 glossary 列表。"""

    ROLES = ["src", "dst", "note"]
    edited = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._terms: list[dict] = []

    def bind(self, terms: list[dict]) -> None:
        self.beginResetModel()
        self._terms = terms
        self.endResetModel()

    def roleNames(self):
        return {Qt.UserRole + i: name.encode() for i, name in enumerate(self.ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._terms)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        return self._terms[index.row()].get(self.ROLES[role - Qt.UserRole], "")

    @Slot(str, str, str)
    def add(self, src: str, dst: str, note: str = "") -> None:
        if not src.strip():
            return
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._terms.insert(0, {"src": src.strip(), "dst": dst.strip(), "note": note.strip()})
        self.endInsertRows()
        self.edited.emit()

    @Slot(int, str, str)
    def setField(self, row: int, field: str, value: str) -> None:
        if 0 <= row < len(self._terms) and self._terms[row].get(field) != value:
            self._terms[row][field] = value
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [Qt.UserRole + self.ROLES.index(field)])
            self.edited.emit()

    @Slot(int)
    def remove(self, row: int) -> None:
        if 0 <= row < len(self._terms):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._terms[row]
            self.endRemoveRows()
            self.edited.emit()


class Backend(QObject):
    runningChanged = Signal()
    statusChanged = Signal()
    statsChanged = Signal()
    windowsChanged = Signal()
    targetChanged = Signal()
    profilesChanged = Signal()
    profileChanged = Signal()
    settingsChanged = Signal()
    overlayVisibleChanged = Signal()
    targetRectChanged = Signal(int, int, int, int)
    regionPickerRequested = Signal()
    captureModeChanged = Signal(str)
    localModelsChanged = Signal()
    installProgressChanged = Signal()
    hymtDevicesChanged = Signal()
    _installTick = Signal(str, float, str)  # 下载线程 -> 界面线程：模型、进度、当前文件
    _installDone = Signal(str, str)  # 模型、错误信息（空 = 成功）
    _devicesFound = Signal(list)
    usageChanged = Signal()
    themeChanged = Signal()
    standbyChanged = Signal()
    toastChanged = Signal()
    hotkeysChanged = Signal()  # 按键改了，要重新向系统注册
    hotkeyCapture = Signal(bool)  # 界面正在录入新的快捷键：这期间先把全局快捷键停掉
    snapPickerRequested = Signal()

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.blocks = BlockModel(self)
        self.terms = TermModel(self)
        self.terms.edited.connect(lambda: self._profile_touched("glossary"))
        self.profileChanged.connect(self._sync_overlay_style)
        self._pipeline: Pipeline | None = None
        self._cache: dict = {}
        self._running = False
        self._status = ("info", "待机")
        self._stats: dict = {}
        self._windows: list[dict] = []
        self._target: dict = {}
        self._overlay_visible = True
        self._fresh: str | None = None  # 刚为当前窗口自动建的预设；用户动过它或开始翻译之后才存盘
        self._stopping: list[Pipeline] = []  # 已经叫停、线程还在收尾的管线
        # 占用监测：每 2 秒量一次 Gloss 自己（含本地翻译模型的进程）用了多少 CPU 和内存
        self._me = psutil.Process()
        self._usage = {"cpu": 0.0, "cores": 0.0, "mem": 0.0}
        self._usage_mark = (time.perf_counter(), self._cpu_seconds())
        self._usage_timer = QTimer(self, interval=2000, timeout=self._measure_usage)
        self._usage_timer.start()
        self._toast_text = ""
        self._toast_timer = QTimer(self, singleShot=True, interval=2200, timeout=lambda: self._toast(""))
        self._standby_timer = QTimer(self, singleShot=True, interval=STANDBY_MS, timeout=self._standby_expired)
        self._hotkey_conflicts: set[str] = set()
        self._save_timer = QTimer(self, singleShot=True, interval=400, timeout=self._save)
        self._restart_timer = QTimer(self, singleShot=True, interval=500, timeout=self._restart)
        self._install = {"kind": "", "progress": 0.0, "file": "", "error": "", "failed": ""}
        self._devices: list[str] = []
        self._installTick.connect(self._on_install_tick)
        self._installDone.connect(self._on_install_done)
        self._devicesFound.connect(self._on_devices)
        self._probe_devices()
        self.terms.bind(self.store.profile()["glossary"])
        self._sync_overlay_style()
        self.refreshWindows()

    # ---- 只读常量 ----
    @Property("QVariantList", constant=True)
    def sourceLangs(self):
        return _options(SOURCE_LANGS)

    @Property("QVariantList", constant=True)
    def targetLangs(self):
        return _options(TARGET_LANGS)

    @Property("QVariantList", constant=True)
    def ocrEngines(self):
        return _options(ENGINES.items())

    @Property("QVariantList", constant=True)
    def engines(self):
        tags = {"real": "已实测", "docs": "", "memory": ""}
        return [
            {"value": e.id, "label": f"{e.group}  ·  {e.label}", "group": e.group, "verified": e.verified,
             "name": e.label.split("（")[0].strip(), "tag": tags[e.verified]}
            for e in TRANSLATE_ENGINES
        ]

    @Property("QVariantMap", notify=settingsChanged)
    def engine(self):
        """当前翻译引擎的说明和设置项，引擎页按它生成界面。"""
        tr = self.store.settings["translator"]
        e = BY_ID.get(tr.get("provider"), BY_ID["google"])
        values = tr.get(e.id, {})
        return {
            "id": e.id,
            "note": e.note,
            "caution": VERIFIED_TEXT[e.verified],
            "fields": [
                {"key": f.key, "label": f.label, "secret": f.secret, "placeholder": f.placeholder, "hint": f.hint,
                 "value": values.get(f.key, f.default)}
                for f in e.fields
            ],
        }

    # ---- 主题 ----
    @Property("QVariantList", constant=True)
    def themes(self):
        return [{"value": v, "label": label} for v, label in
                (("light", "浅色"), ("paper", "暖纸"), ("dark", "深色"), ("midnight", "墨蓝"), ("system", "跟随系统"))]

    @Property(str, notify=themeChanged)
    def themeName(self):
        """实际用哪套色板："跟随系统"时按 Windows 的应用模式取浅色或深色。"""
        name = self.store.settings.get("theme", "light")
        if name != "system":
            return name
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication) and app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return "dark"
        return "light"

    # ---- 快捷键 ----
    @Property("QVariantList", notify=hotkeysChanged)
    def hotkeys(self):
        bound = self.store.settings["hotkeys"]
        return [
            {"action": action, "label": label, "keys": bound.get(action, ""), "conflict": action in self._hotkey_conflicts}
            for action, label, _ in hotkeys.ACTIONS
        ]

    @Slot(str, int, int, result=bool)
    def setHotkey(self, action: str, key: int, modifiers: int) -> bool:
        """界面上录入了一个新按键。key=0 表示清除。组合不适合做全局快捷键、或者已经被别的动作占用时返回 False。"""
        if action not in hotkeys.DEFAULTS:
            return False
        combo = "" if key == 0 else hotkeys.from_qt(key, modifiers)
        if combo is None:
            return False
        bound = self.store.settings["hotkeys"]
        if combo and any(a != action and k == combo for a, k in bound.items()):
            return False
        bound[action] = combo
        self.store.save_settings()
        self.hotkeysChanged.emit()
        return True

    @Slot(str)
    def resetHotkey(self, action: str) -> None:
        if action in hotkeys.DEFAULTS:
            self.store.settings["hotkeys"][action] = hotkeys.DEFAULTS[action]
            self.store.save_settings()
            self.hotkeysChanged.emit()

    @Slot(bool)
    def captureHotkey(self, capturing: bool) -> None:
        self.hotkeyCapture.emit(capturing)

    def set_hotkey_conflicts(self, actions: set[str]) -> None:
        """哪些快捷键向系统注册失败了（多半是被别的程序占用）。"""
        if actions != self._hotkey_conflicts:
            self._hotkey_conflicts = set(actions)
            self.hotkeysChanged.emit()

    # ---- 游戏画面上的一行提示（按了快捷键之后告诉用户发生了什么） ----
    @Property(str, notify=toastChanged)
    def toast(self):
        return self._toast_text

    def _toast(self, text: str) -> None:
        self._toast_text = text
        if text:
            hwnd = self._target.get("hwnd", 0)
            if hwnd and win32.is_window(hwnd):  # 没在翻译时悬浮层还没摆到游戏上，先摆好
                self.targetRectChanged.emit(*win32.client_rect(hwnd))
            self._toast_timer.start()
        self.toastChanged.emit()

    # ---- 占用监测 ----
    def _processes(self) -> list[psutil.Process]:
        try:
            return [self._me, *self._me.children(recursive=True)]
        except psutil.Error:
            return [self._me]

    def _cpu_seconds(self) -> float:
        total = 0.0
        for p in self._processes():
            try:
                t = p.cpu_times()
                total += t.user + t.system
            except psutil.Error:
                pass  # 子进程刚好退出了
        return total

    def _measure_usage(self) -> None:
        now, cpu = time.perf_counter(), self._cpu_seconds()
        then, before = self._usage_mark
        self._usage_mark = (now, cpu)
        cores = max(0.0, cpu - before) / max(1e-3, now - then)
        mem = 0.0
        for p in self._processes():
            try:
                mem += p.memory_info().rss
            except psutil.Error:
                pass
        # cpu 是占整台机器的百分比（和任务管理器里看到的一致），cores 是相当于占了几个核
        self._usage = {"cpu": round(100 * cores / (psutil.cpu_count() or 1), 1), "cores": round(cores, 2), "mem": round(mem / 1e6)}
        self.usageChanged.emit()

    @Property("QVariantMap", notify=usageChanged)
    def usage(self):
        return self._usage

    @Property("QVariantList", constant=True)
    def fonts(self):
        families = sorted(QFontDatabase.families()) if isinstance(QGuiApplication.instance(), QGuiApplication) else []
        return [{"value": "", "label": "默认（微软雅黑）"}] + [{"value": f, "label": f} for f in families if not f.startswith("@")]

    # ---- 本地翻译模型 ----
    @Property("QVariantMap", notify=localModelsChanged)
    def localModels(self):
        return {
            kind: {"installed": local_mt.installed(kind), "label": local_mt.LABELS[kind],
                   "downloadMb": round(local_mt.download_size(kind) / 1e6)}
            for kind in local_mt.ASSETS
        }

    @Property("QVariantMap", notify=installProgressChanged)
    def installProgress(self):
        return self._install

    @Property("QVariantList", notify=hymtDevicesChanged)
    def hymtDevices(self):
        fixed = [{"value": "auto", "label": "自动（显卡空闲用显卡，被游戏占满时用 CPU）"}, {"value": "cpu", "label": "仅 CPU"}]
        return fixed + [{"value": d.split(":")[0], "label": d.split(": ", 1)[-1]} for d in self._devices]

    def _probe_devices(self) -> None:
        """问 llama.cpp 有哪些显卡可用。要起一个子进程，放到后台线程里做。"""
        if not local_mt.installed("hymt"):
            return
        from .translate.hymt import list_devices

        threading.Thread(target=lambda: self._devicesFound.emit(list_devices()), daemon=True).start()

    @Slot(list)
    def _on_devices(self, devices: list) -> None:
        self._devices = devices
        self.hymtDevicesChanged.emit()

    @Slot(str)
    def installLocalModel(self, kind: str) -> None:
        if self._install["kind"] or kind not in local_mt.ASSETS:
            return
        self._install = {"kind": kind, "progress": 0.0, "file": "", "error": "", "failed": ""}
        self.installProgressChanged.emit()

        def work() -> None:
            try:
                local_mt.install(kind, lambda p, name: self._installTick.emit(kind, p, name))
                self._installDone.emit(kind, "")
            except Exception as e:  # 下载线程里的任何错误都要报给界面，不能悄悄没了
                self._installDone.emit(kind, str(e))

        threading.Thread(target=work, name="gloss-install", daemon=True).start()

    @Slot(str, float, str)
    def _on_install_tick(self, kind: str, progress: float, name: str) -> None:
        self._install = {**self._install, "progress": progress, "file": name}
        self.installProgressChanged.emit()

    @Slot(str, str)
    def _on_install_done(self, kind: str, error: str) -> None:
        self._install = {"kind": "", "progress": 0.0, "file": "", "error": error, "failed": kind if error else ""}
        self.installProgressChanged.emit()
        self.localModelsChanged.emit()
        self._probe_devices()
        if not error and self._running:
            self._restart()

    # ---- 状态 ----
    @Property(bool, notify=runningChanged)
    def running(self):
        """正在连续翻译。"""
        return self._running

    @Property(bool, notify=standbyChanged)
    def standby(self):
        """模型已经加载、在等临时翻译的请求，但没有连续翻译。"""
        return self._pipeline is not None and not self._running

    @Property(str, notify=statusChanged)
    def statusLevel(self):
        return self._status[0]

    @Property(str, notify=statusChanged)
    def statusText(self):
        return self._status[1]

    @Property("QVariantMap", notify=statsChanged)
    def stats(self):
        return self._stats

    @Property(bool, notify=overlayVisibleChanged)
    def overlayVisible(self):
        return self._overlay_visible

    @Property("QVariantList", notify=windowsChanged)
    def windows(self):
        return self._windows

    @Property("QVariantMap", notify=targetChanged)
    def target(self):
        return self._target

    @Property("QVariantList", notify=profilesChanged)
    def profiles(self):
        return [{"value": pid, "label": p["name"]} for pid, p in self.store.profiles.items()]

    @Property("QVariantMap", notify=profileChanged)
    def profile(self):
        return self.store.profile()

    @Property("QVariantMap", notify=settingsChanged)
    def settings(self):
        return self.store.settings

    def _sync_overlay_style(self) -> None:
        d = self.store.profile()["display"]
        self.blocks.set_style(d.get("mode", "inplace"), d.get("font_family", ""), d.get("font_scale", 1.0))

    def _set_status(self, level: str, text: str) -> None:
        self._status = (level, text)
        self.statusChanged.emit()

    # ---- 目标窗口 ----
    @Slot()
    def refreshWindows(self) -> None:
        self._windows = [
            {**w, "label": f"{w['title']}  ·  {w['exe']}" if w["exe"] else w["title"]} for w in win32.list_windows()
        ]
        self.windowsChanged.emit()
        if self._target and not any(w["hwnd"] == self._target.get("hwnd") for w in self._windows):
            self._target = {}
            self.targetChanged.emit()

    @Slot(int)
    def selectWindow(self, hwnd: int) -> None:
        win = next((w for w in self._windows if w["hwnd"] == hwnd), None)
        if win is None or win == self._target:
            return
        self._target = win
        self.targetChanged.emit()
        self._enter_game(win)
        self._restart()

    def _enter_game(self, win: dict) -> None:
        """切到这个游戏自己的预设；它还没有预设就按默认预设新建一份。"""
        pid = self.store.match_profile(win["exe"], win["title"])
        if pid is None and win["exe"]:
            title = " ".join(win["title"].split())
            name = title if len(title) <= 32 else win["exe"].rsplit(".", 1)[0]
            pid = self.store.new_game_profile(name, win["exe"], save=False)
            self._drop_fresh()
            self._fresh = pid
            self.profilesChanged.emit()
        self.selectProfile(pid or "default")

    def _drop_fresh(self, keep: str | None = None) -> None:
        """自动建的预设如果一直没被用到（没改过、没开始翻译），换到别处时就丢掉，不留一堆空预设。"""
        if self._fresh and self._fresh != keep:
            self.store.profiles.pop(self._fresh, None)
            self._fresh = None
            self.profilesChanged.emit()

    # ---- 开始 / 停止 ----
    @Slot()
    def toggle(self) -> None:
        self.stop() if self._running else self.start()

    def _adopt_foreground(self) -> bool:
        """快捷键是在游戏里按的：如果前台窗口不是当前选中的那个，就改成翻译前台窗口。返回有没有可翻译的窗口。"""
        fg = win32.foreground_window()
        if fg and fg != self._target.get("hwnd"):
            self.refreshWindows()
            if any(w["hwnd"] == fg for w in self._windows):
                self.selectWindow(fg)
        hwnd = self._target.get("hwnd", 0)
        return bool(hwnd) and win32.is_window(hwnd)

    @Slot()
    def start(self) -> None:
        if self._running:
            return
        if not self._adopt_foreground():
            self._set_status("error", "先选择要翻译的游戏窗口")
            return
        self._restart_timer.stop()  # 现在读到的就是最新设置，之前排着的"稍后重启"作废，否则模型会被加载两遍
        self._standby_timer.stop()
        self._fresh = None  # 开始翻译了，这份预设就算正式用上了
        self._save()
        if self._pipeline is not None:
            self._pipeline.set_continuous(True)  # 待命中：模型已经在内存里，直接转成连续翻译
        else:
            self._spawn(continuous=True)
        self._running = True
        self.runningChanged.emit()
        self.standbyChanged.emit()

    def _spawn(self, continuous: bool) -> None:
        hwnd = self._target["hwnd"]
        profile = copy.deepcopy(self.store.profile())
        self._cache = self.store.load_cache(profile["id"])
        p = Pipeline(hwnd, copy.deepcopy(self.store.settings), profile, self._cache, continuous=continuous)
        p.snapshotDone.connect(self._on_snapshot, Qt.ConnectionType.QueuedConnection)
        # 管线在自己的线程里发信号；用排队连接保证下面这些槽都在界面线程执行
        q = Qt.ConnectionType.QueuedConnection
        p.blocksSynced.connect(self._on_blocks, q)
        p.blockUpdated.connect(self._on_block_text, q)
        p.geometryChanged.connect(self._on_geometry, q)
        p.statsChanged.connect(self._on_stats, q)
        p.statusChanged.connect(self._on_status, q)
        p.captureModeChanged.connect(self.captureModeChanged, q)
        p.stopped.connect(self._on_stopped, q)
        self._pipeline = p
        p.start()

    @Slot()
    def stop(self) -> None:
        if self._pipeline is None:
            return
        self._teardown()
        self._set_status("info", "待机")

    # ---- 临时翻译：按一下翻一次，不用开着连续翻译 ----
    def _snapshot(self, region: list | None, label: str) -> None:
        if self._pipeline is None:
            self._restart_timer.stop()
            self._spawn(continuous=False)
            self.standbyChanged.emit()
            self._toast(f"{label} · 正在加载模型…")
        else:
            self._toast(label)
        self._pipeline.request_snapshot(region, float(self.store.settings.get("quick", {}).get("hold_s", 10)))
        if not self._running:
            self._standby_timer.start()  # 一阵子不用就把模型卸掉

    @Slot()
    def quickFull(self) -> None:
        """临时翻译整个窗口。屏上还留着上一次的临时译文时，再按一次是清掉它。"""
        if not self._adopt_foreground():
            self._set_status("error", "没有可以翻译的窗口")
            return
        if self._pipeline is not None and self._pipeline.has_snapshot:
            self._pipeline.clear_snapshot()
            self._toast("已清除临时译文")
            return
        if self._running and self._scope() == "full":
            self._toast("已经在翻译整个窗口")
            return
        self._snapshot(None, "临时翻译整个窗口")

    @Slot()
    def quickRegion(self) -> None:
        """临时框选一块翻译：先让用户在游戏画面上拖一个框。"""
        if not self._adopt_foreground():
            self._set_status("error", "没有可以翻译的窗口")
            return
        self.snapPickerRequested.emit()

    @Slot(float, float, float, float)
    def snapRegion(self, x: float, y: float, w: float, h: float) -> None:
        self._snapshot([x, y, w, h], "临时翻译选中的区域")

    @Slot(int)
    def _on_snapshot(self, count: int) -> None:
        if self.sender() is self._pipeline and count == 0:
            self._toast("没有识别到要翻译的文字")

    def _standby_expired(self) -> None:
        if self._pipeline is not None and not self._running:
            self._teardown()
            self._set_status("info", "待机")

    # ---- 识别范围：整个窗口 / 固定区域 ----
    def _scope(self) -> str:
        """连续翻译实际识别的范围：选了固定区域但一个区域都没有时，等于整个窗口。"""
        profile = self.store.profile()
        return "regions" if profile.get("scope", "regions") == "regions" and profile.get("regions") else "full"

    @Slot(str)
    def setScope(self, scope: str) -> None:
        self.store.profile()["scope"] = scope
        self._fresh = None
        self.profileChanged.emit()
        self._save_timer.start()
        if self._pipeline is not None:
            self._pipeline.set_scope(scope)  # 正在跑的翻译直接换范围，不重启
        n = len(self.store.profile().get("regions", []))
        self._toast(f"识别范围：固定区域（{n} 个）" if self._scope() == "regions" else "识别范围：整个窗口")

    @Slot()
    def toggleScope(self) -> None:
        if self._scope() == "regions":
            self.setScope("full")
        elif self.store.profile().get("regions"):
            self.setScope("regions")
        else:
            self._toast("还没有固定区域，先框选")
            self.pickRegion()

    def _teardown(self) -> None:
        p, self._pipeline = self._pipeline, None
        if p is not None:
            p.stop()
            self.store.save_cache(p.profile["id"], p.cache)
            self._stopping.append(p)  # 留着引用，等它的线程收尾
        self.blocks.clear()
        self._standby_timer.stop()
        self._running = False
        self.runningChanged.emit()
        self.standbyChanged.emit()

    # 下面的槽只处理当前管线发来的信号；已经被换掉的旧管线发来的一律丢弃
    @Slot(list)
    def _on_blocks(self, views: list) -> None:
        if self.sender() is self._pipeline:
            self.blocks.sync(views)

    @Slot(str, str, bool)
    def _on_block_text(self, bid: str, text: str, final: bool) -> None:
        if self.sender() is self._pipeline:
            self.blocks.update(bid, text, final)

    @Slot(int, int, int, int)
    def _on_geometry(self, x: int, y: int, w: int, h: int) -> None:
        if self.sender() is self._pipeline:
            self.blocks.set_viewport(w, h)
            self.targetRectChanged.emit(x, y, w, h)

    @Slot(str, str)
    def _on_status(self, level: str, text: str) -> None:
        if self.sender() is self._pipeline:
            self._set_status(level, text)

    @Slot()
    def _on_stopped(self) -> None:
        """管线自己停了（出错或目标窗口关了）。保留它报的状态信息。"""
        if self.sender() is self._pipeline:
            self._teardown()

    @Slot(dict)
    def _on_stats(self, stats: dict) -> None:
        if self.sender() is self._pipeline:
            self._stats = stats
            self.statsChanged.emit()

    def _schedule_restart(self) -> None:
        """设置变了：有管线在跑才需要稍后重启；没在跑的话，下次启动自然会读到新设置。"""
        if self._pipeline is not None:
            self._restart_timer.start()

    def _restart(self) -> None:
        """设置变了，要重新加载模型。待命中的管线直接卸掉，下次临时翻译时会按新设置重建。"""
        if self._pipeline is None:
            return
        was_running = self._running
        self._teardown()
        if was_running:
            self.start()

    @Slot()
    def toggleOverlay(self) -> None:
        self._overlay_visible = not self._overlay_visible
        self.overlayVisibleChanged.emit()

    # ---- 预设 ----
    def _profile_touched(self, path: str) -> None:
        self._fresh = None  # 用户改过了，要存盘
        self.profileChanged.emit()
        self._save_timer.start()
        if not path.startswith("display.") and path != "name" and not path.startswith("match."):
            self._schedule_restart()  # 外观类改动悬浮层直接读，不用重启管线

    @Slot(str, "QVariant")
    def setProfile(self, path: str, value) -> None:
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        set_path(self.store.profile(), path, value)
        if path == "name":
            self.profilesChanged.emit()
        self._profile_touched(path)

    @Slot(str)
    def selectProfile(self, pid: str) -> None:
        if pid not in self.store.profiles or pid == self.store.settings.get("active_profile"):
            return
        self._save()
        self._drop_fresh(keep=pid)
        self.store.settings["active_profile"] = pid
        self.store.save_settings()
        self.terms.bind(self.store.profile()["glossary"])
        self.settingsChanged.emit()
        self.profileChanged.emit()
        self._schedule_restart()

    @Slot()
    def deleteProfile(self) -> None:
        pid = self.store.settings.get("active_profile")
        if pid == "default":
            return
        self._save_timer.stop()
        self._fresh = None
        self.store.delete_profile(pid)
        self.terms.bind(self.store.profile()["glossary"])
        self.profilesChanged.emit()
        self.settingsChanged.emit()
        self.profileChanged.emit()
        self._schedule_restart()

    # ---- 识别区域 ----
    @Slot()
    def pickRegion(self) -> None:
        if not self._target.get("hwnd") or not win32.is_window(self._target["hwnd"]):
            self._set_status("error", "先选择要翻译的游戏窗口")
            return
        self.regionPickerRequested.emit()

    @Slot("QVariantList")
    def setRegions(self, regions: list) -> None:
        """整体替换当前预设的识别区域（游戏里的区域编辑器每次松手都会调用）。"""
        if hasattr(regions, "toVariant"):
            regions = regions.toVariant()
        clean = []
        for r in regions:
            x, y, w, h = (float(v) for v in list(r)[:4])
            x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
            w, h = min(w, 1.0 - x), min(h, 1.0 - y)
            if w > 0.005 and h > 0.005:
                clean.append([round(x, 4), round(y, 4), round(w, 4), round(h, 4)])
        self.store.profile()["regions"] = clean
        self._fresh = None
        self.profileChanged.emit()
        self._save_timer.start()
        if self._pipeline is not None:
            self._pipeline.set_regions(clean)  # 正在跑的翻译直接换区域，不重启（重启要重新加载模型）

    @Slot(float, float, float, float)
    def addRegion(self, x: float, y: float, w: float, h: float) -> None:
        self.setRegions([*self.store.profile().get("regions", []), [x, y, w, h]])

    @Slot()
    def clearRegions(self) -> None:
        self.setRegions([])

    # ---- 设置 ----
    @Slot(str, "QVariant")
    def setSetting(self, path: str, value) -> None:
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        set_path(self.store.settings, path, value)
        self.settingsChanged.emit()
        self._save_timer.start()
        if path == "theme":
            self.themeChanged.emit()
        elif not path.startswith("quick."):  # 主题和"临时译文停留多久"都不用重新加载模型
            self._schedule_restart()

    def _save(self) -> None:
        pid = self.store.profile()["id"]
        if pid != self._fresh:  # 自动建的预设还没被用到就不存盘
            self.store.save_profile(pid)
            self.store.save_settings()

    def shutdown(self) -> None:
        if self._save_timer.isActive():
            self._save()
        if self._pipeline is not None:
            self._teardown()
        for p in self._stopping:  # 等它们把本地模型的服务进程关掉再退出
            p.join(3.0)
        self._stopping.clear()


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == win32.WM_HOTKEY:
                self._callback(int(msg.wParam))
                return True, 0
        return False, 0


class App:
    """组装整个应用：QML 引擎、三个窗口、热键。"""

    def __init__(self, store: Store | None = None, hotkeys: bool = True, overlay_on_top: bool = True) -> None:
        self._overlay_on_top = overlay_on_top  # 测试时设成 False，悬浮层压在最底下不打扰人
        QQuickWindow.setTextRenderType(QQuickWindow.TextRenderType.NativeTextRendering)
        self.qt = QGuiApplication.instance() or QGuiApplication(sys.argv)
        self.qt.setApplicationName("Gloss")
        try:  # 低于普通优先级：和游戏抢 CPU 的时候让着游戏
            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except psutil.Error:
            pass
        self.qt.setWindowIcon(QIcon(str(UI_DIR / "icon.svg")))
        font = QFont()
        font.setFamilies(["Segoe UI Variable Text", "Microsoft YaHei UI", "Segoe UI"])
        self.qt.setFont(font)

        self.backend = Backend(store or Store())
        self.qt.styleHints().colorSchemeChanged.connect(lambda *_: self.backend.themeChanged.emit())  # 系统切了浅色 / 深色
        self.engine = QQmlApplicationEngine()
        self.engine.addImportPath(str(UI_DIR))
        ctx = self.engine.rootContext()
        ctx.setContextProperty("backend", self.backend)
        ctx.setContextProperty("blockModel", self.backend.blocks)
        ctx.setContextProperty("termModel", self.backend.terms)
        for name in ("Main.qml", "Overlay.qml", "RegionPicker.qml", "SnapPicker.qml"):
            self.engine.load(QUrl.fromLocalFile(str(UI_DIR / name)))
        roots = {o.objectName(): o for o in self.engine.rootObjects()}
        if set(roots) != {"main", "overlay", "picker", "snap"}:
            raise RuntimeError("界面加载失败（QML 有错误，见上方输出）")
        self.main, self.overlay, self.picker, self.snap = roots["main"], roots["overlay"], roots["picker"], roots["snap"]

        win32.style_app_window(int(self.main.winId()))
        self.backend.captureModeChanged.connect(self._on_capture_mode)
        self.backend.targetRectChanged.connect(self._place_overlay)
        self.backend.regionPickerRequested.connect(self._show_picker)
        self.backend.snapPickerRequested.connect(self._show_snap)
        self.qt.aboutToQuit.connect(self._quit)

        self._filter = None
        self._hotkey_ids: dict[int, str] = {}  # 向系统注册时用的编号 -> 动作
        if hotkeys:
            self._filter = _HotkeyFilter(self._on_hotkey)
            self.qt.installNativeEventFilter(self._filter)
            self._register_hotkeys()
            self.backend.hotkeysChanged.connect(self._register_hotkeys)
            # 界面在录入新按键时先把全局快捷键停掉，否则按下已有的组合会直接触发动作，录不进去
            self.backend.hotkeyCapture.connect(lambda capturing: self._unregister_hotkeys() if capturing else self._register_hotkeys())

    def _unregister_hotkeys(self) -> None:
        hwnd = int(self.main.winId())
        for hid in self._hotkey_ids:
            win32.unregister_hotkey(hwnd, hid)
        self._hotkey_ids = {}

    def _register_hotkeys(self) -> None:
        """按设置向系统注册全局快捷键。注册不上的（多半被别的程序占了）记下来，界面上会标出来。"""
        self._unregister_hotkeys()
        hwnd = int(self.main.winId())
        failed = set()
        for hid, item in enumerate(self.backend.hotkeys, start=1):
            parsed = hotkeys_mod.parse(item["keys"])
            if parsed is None:
                continue  # 没设这个快捷键
            if win32.register_hotkey(hwnd, hid, *parsed):
                self._hotkey_ids[hid] = item["action"]
            else:
                failed.add(item["action"])
        self.backend.set_hotkey_conflicts(failed)

    def _on_capture_mode(self, mode: str) -> None:
        # 抓屏幕区域时，悬浮层必须从截屏里排除，否则译文盖住原文，下一轮就识别不到原文了。
        # 窗口捕获本来就拿不到悬浮层，不用排除——这样录屏和截图软件还能拍到译文。
        win32.exclude_from_capture(int(self.overlay.winId()), mode == "screen")

    def _place_overlay(self, x: int, y: int, w: int, h: int) -> None:
        win32.move_window(int(self.overlay.winId()), x, y, w, h, topmost=self._overlay_on_top)

    def _show_picker(self) -> None:
        if self.picker.property("visible"):  # 再按一次快捷键就是收起
            self.picker.setProperty("visible", False)
            return
        rect = win32.client_rect(self.backend.target["hwnd"])
        self.picker.setProperty("visible", True)
        win32.move_window(int(self.picker.winId()), *rect)
        self.picker.requestActivate()

    def _show_snap(self) -> None:
        rect = win32.client_rect(self.backend.target["hwnd"])
        self.snap.setProperty("visible", True)
        win32.move_window(int(self.snap.winId()), *rect)
        self.snap.requestActivate()

    def _on_hotkey(self, hid: int) -> None:
        b = self.backend
        actions = {
            "toggle": b.toggle, "overlay": b.toggleOverlay, "regions": b.pickRegion,
            "snap_full": b.quickFull, "snap_region": b.quickRegion, "scope": b.toggleScope,
        }
        action = self._hotkey_ids.get(hid)
        if action in actions:
            actions[action]()

    def _quit(self) -> None:
        self._unregister_hotkeys()
        self.backend.shutdown()

    def run(self) -> int:
        return self.qt.exec()
