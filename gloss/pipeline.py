"""实时管线：截屏 → 判断画面变化 → OCR → 分块 → 翻译 → 通知界面。

省时间的地方：
- 画面没变就什么都不做；文字还在变（打字机效果）就等它停下来再识别；
- 画面只变了一小块时只识别那一块（对话框换了一句话，不用重新识别整个屏幕）；
- 文字和上次一样的块沿用原来的译文，不重新请求；
- 一次 OCR 里的新文本合并成一个翻译请求，流式返回。
"""

from __future__ import annotations

import difflib
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal

from . import win32
from .capture import create_capturer
from .layout import group_lines, normalize, sample_colors, worth_translating
from .ocr import OcrUnavailable, create_engine
from .translate import Term, TranslateContext, TranslateError, create_translator, translator_signature
from .types import Block, TextLine

_DIFF_THRESHOLD = 14  # 缩略图上灰度差超过它算"这个像素变了"
_CHANGED_RATIO = 0.0015  # 变了的像素超过这个比例算"画面变了"
_SMALL_DIV = 6  # 缩略图相对原图的缩小倍数
_IDLE_POLL = 0.2  # 画面静止超过 _IDLE_AFTER 秒后，降到这个轮询间隔
_IDLE_AFTER = 2.0
_FORCE_MAX = 2.0  # 画面一直在动、文字又没变时，强制识别的间隔最多拉到这么长；再长的话新出现的文字要等太久
_GROW_DEBOUNCE = 0.35  # 文字还在变长（打字机效果）时，停下来这么久才请求翻译


@dataclass
class _Roi:
    """一个识别区域的状态。坐标是画面内的像素。"""

    x: int
    y: int
    w: int
    h: int
    prev: np.ndarray | None = None  # 上一帧的缩略图
    ocr_small: np.ndarray | None = None  # 上次 OCR 时的缩略图
    lines: list[TextLine] = field(default_factory=list)
    changing: bool = True
    change_start: float = 0.0
    last_change: float = 0.0
    last_ocr: float = 0.0
    force_every: float = 0.0  # 画面一直在动时隔多久强制识别一次；连续几次文字都没变就逐步拉长
    signature: tuple = ()  # 上次识别到的文字，用来判断"文字变没变"


def _iou(a: Block, b: Block) -> float:
    ix = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    inter = ix * iy
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def _continues(old: Block, old_key: str, new: Block, new_key: str) -> bool:
    """new 是不是 old 那一行（段）继续打字打出来的：起点相同，文本是前缀关系。"""
    if abs(old.x - new.x) > 12 or abs(old.y - new.y) > 12:
        return False
    return new_key.startswith(old_key) or old_key.startswith(new_key)


class Pipeline(QObject):
    blocksSynced = Signal(list)  # 当前所有块的完整状态（list[dict]）
    blockUpdated = Signal(str, str, bool)  # 块 id、译文、是否完成（流式更新）
    geometryChanged = Signal(int, int, int, int)  # 目标窗口客户区的屏幕位置
    statsChanged = Signal(dict)
    statusChanged = Signal(str, str)  # 级别 info|ok|error，消息
    captureModeChanged = Signal(str)  # window | screen
    snapshotDone = Signal(int)  # 一次临时翻译识别到了几块文字
    stopped = Signal()

    def __init__(self, hwnd: int, settings: dict, profile: dict, cache: dict | None = None, continuous: bool = True) -> None:
        super().__init__()
        self.hwnd = hwnd
        # continuous=False 是"待命"：模型加载好等着，不主动识别，只响应临时翻译的请求
        self.continuous = continuous
        self._snap_request: tuple | None = None  # (区域或 None, 停留秒数)
        self._snap_blocks: dict[str, Block] = {}  # 临时翻译出来的块，到时间就清掉
        self._snap_until = 0.0
        self.settings = settings
        self.profile = profile
        self.cache: dict = cache if cache is not None else {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gloss-tr")
        self._lock = threading.Lock()
        self._blocks: dict[str, Block] = {}  # 规范化原文 -> 块
        self._history: list[tuple[str, str]] = []
        self._retry_at = 0.0
        self._deferred_at = 0.0  # 有块在等"文字停下来"时，最早该发请求的时间
        self._regions_version = 0
        # 各环节累计耗时（秒）和次数，给占用监测用
        self.profile_totals = {"capture": 0.0, "diff": 0.0, "ocr": 0.0, "blocks": 0.0, "n_loops": 0, "n_ocr": 0}
        self._ok_text = "翻译中"  # 一切正常时状态栏显示的话；翻译后端有话要说时会接在后面
        self._engine = None
        self._translator = None
        self._stats: dict = {}

        tr = settings.get("translator", {})
        glossary = profile.get("glossary", [])
        self._terms = [Term(t.get("src", ""), t.get("dst", ""), t.get("note", "")) for t in glossary if t.get("src")]
        gloss_sig = hash(tuple((t.src, t.dst) for t in self._terms)) & 0xFFFFFF
        self._cache_prefix = f"{translator_signature(tr)}|{profile.get('target_lang')}|{gloss_sig:x}|"
        self._ignore = []
        for pat in profile.get("filter", {}).get("ignore", []):
            try:
                self._ignore.append(re.compile(pat))
            except re.error:
                pass

    # ---- 生命周期 ----
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="gloss-pipeline", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def set_regions(self, regions: list) -> None:
        """运行中改识别区域：不用重启管线（重启要重新加载模型）。"""
        self.profile["regions"] = [list(r) for r in regions]
        self._regions_version += 1

    def set_scope(self, scope: str) -> None:
        """运行中切换识别范围：regions 只识别固定区域，full 识别整个窗口。"""
        self.profile["scope"] = scope
        self._regions_version += 1

    def set_continuous(self, on: bool) -> None:
        """在"连续翻译"和"待命"之间切换，模型留在内存里不用重新加载。"""
        self.continuous = on
        self._regions_version += 1  # 让主循环重建各区域的状态，恢复连续翻译时从头识别一遍
        self.statusChanged.emit("ok", self._status_text())

    def request_snapshot(self, region: list | None = None, hold: float = 10.0) -> None:
        """临时翻译一次：region 是相对窗口的 [x, y, w, h]，None 表示整个窗口。译文停留 hold 秒（0 = 不自动消失）。"""
        with self._lock:
            self._snap_request = (region, hold)

    def clear_snapshot(self) -> None:
        with self._lock:
            if not self._snap_blocks:
                return
            self._snap_blocks = {}
            views = self._views_locked()
        self.blocksSynced.emit(views)

    @property
    def has_snapshot(self) -> bool:
        return bool(self._snap_blocks) or self._snap_request is not None

    def _status_text(self) -> str:
        return self._ok_text if self.continuous else "快捷翻译待命"

    def _views_locked(self) -> list[dict]:
        blocks = [*self._blocks.values(), *self._snap_blocks.values()]
        return [b.to_view() for b in blocks if not b.extra.get("skip")]

    def _live(self, key: str, block: Block) -> bool:
        """这个块还在不在屏上（被新的块替换掉、或者临时译文已经清掉的，就不用再往界面上写了）。"""
        return self._blocks.get(key) is block or self._snap_blocks.get(key) is block

    def join(self, timeout: float = 3.0) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ---- 主循环 ----
    def _run(self) -> None:
        try:
            self._setup()
            self._loop()
        except (OcrUnavailable, TranslateError) as e:
            self.statusChanged.emit("error", str(e))
        except Exception as e:  # 管线线程不能悄悄死掉，把原因报给界面
            self.statusChanged.emit("error", f"管线异常：{type(e).__name__}: {e}")
        finally:
            if hasattr(self._translator, "close"):
                self._translator.close()  # 本地翻译模型的服务进程随之退出，释放内存和显存
            self.blocksSynced.emit([])
            self.stopped.emit()

    def _setup(self) -> None:
        self.statusChanged.emit("info", "正在加载模型…")
        cv2.setNumThreads(2)  # OpenCV 默认用上所有核，在轮询里反复起落一大群线程，本身就要吃半个核
        ocr = self.settings.get("ocr", {})
        name = ocr.get("engine", "rapid")
        opts = {}
        if name == "rapid":
            opts = dict(model=ocr.get("model", "balanced"), det_side=ocr.get("det_side", 1280), use_gpu=ocr.get("use_gpu", False),
                        threads=ocr.get("threads", 4))
        self._engine = create_engine(name, self.profile.get("source_lang", "auto"), **opts)
        self._translator = create_translator(self.settings.get("translator", {}))
        notice = getattr(self._translator, "notice", "")
        if notice:
            self._ok_text = f"翻译中 · {notice}"
        self._engine.recognize(np.zeros((64, 256, 3), np.uint8))  # 预热，免得第一帧特别慢
        self.statusChanged.emit("ok", self._status_text())

    def _rois(self, w: int, h: int) -> list[_Roi]:
        fixed = self.profile.get("regions") if self.profile.get("scope", "regions") == "regions" else None
        regions = fixed or [[0, 0, 1, 1]]
        rois = []
        for rx, ry, rw, rh in regions:
            x, y = int(max(0, rx) * w), int(max(0, ry) * h)
            rois.append(_Roi(x, y, max(8, min(w - x, int(rw * w))), max(8, min(h - y, int(rh * h)))))
        return rois

    def _loop(self) -> None:
        cfg = self.settings.get("pipeline", {})
        poll = cfg.get("poll_ms", 80) / 1000
        settle = cfg.get("settle_ms", 140) / 1000
        max_wait = cfg.get("max_wait_ms", 1000) / 1000
        prof = self.profile_totals
        regions_version = self._regions_version
        last_activity = time.perf_counter()
        capturer = create_capturer(self.hwnd, self.settings.get("capture", {}).get("mode", "window"))
        self.captureModeChanged.emit(capturer.mode)
        rois: list[_Roi] = []
        last_rect = None
        last_size = None
        try:
            while not self._stop.is_set():
                t_loop = time.perf_counter()
                if not win32.is_window(self.hwnd):
                    self.statusChanged.emit("error", "目标窗口已关闭")
                    return
                rect = win32.client_rect(self.hwnd)
                if win32.is_minimized(self.hwnd) or rect[2] < 32 or rect[3] < 32:
                    if self._blocks:
                        self._blocks = {}
                        self.blocksSynced.emit([])
                    last_rect = None
                    self._stop.wait(0.3)
                    continue
                if rect != last_rect:
                    self.geometryChanged.emit(*rect)
                    last_rect = rect

                t0 = time.perf_counter()
                frame = capturer.grab()
                if frame is None:
                    self._stop.wait(poll)
                    continue
                capture_ms = (time.perf_counter() - t0) * 1000
                prof["capture"] += capture_ms / 1000
                prof["n_loops"] += 1
                if frame.shape[:2] != last_size or regions_version != self._regions_version:
                    last_size, regions_version = frame.shape[:2], self._regions_version
                    rois = self._rois(frame.shape[1], frame.shape[0])

                # 临时翻译：有请求就处理一次；到时间了就把临时译文清掉
                with self._lock:
                    request, self._snap_request = self._snap_request, None
                if request is not None:
                    self._do_snapshot(frame, *request)
                elif self._snap_blocks and time.perf_counter() >= self._snap_until:
                    self.clear_snapshot()
                if not self.continuous:
                    if self._blocks:  # 刚从连续翻译切到待命：把连续翻译的译文撤掉
                        with self._lock:
                            self._blocks = {}
                            views = self._views_locked()
                        self.blocksSynced.emit(views)
                    self._stop.wait(0.1)
                    continue

                now = time.perf_counter()
                ran, stable, ocr_ms = False, True, 0.0
                for roi in rois:
                    crop = frame[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w]
                    # 判断画面变没变只需要一张很小的灰度图。隔几个像素取一个点再模糊一下，比缩放整张大图省一个数量级
                    # （2560×1440 下每次 0.7 ms 对 3.5 ms，而且不会拉起 OpenCV 的一大群线程）
                    small = cv2.blur(cv2.cvtColor(np.ascontiguousarray(crop[::_SMALL_DIV, ::_SMALL_DIV]), cv2.COLOR_BGR2GRAY), (3, 3))
                    first = roi.prev is None or roi.prev.shape != small.shape
                    if not first:
                        changed = (cv2.absdiff(small, roi.prev) > _DIFF_THRESHOLD).mean() > _CHANGED_RATIO
                        if changed:
                            if not roi.changing:
                                roi.changing, roi.change_start = True, now
                            roi.last_change = last_activity = now
                    roi.prev = small
                    if first:
                        roi.changing = True
                    if not roi.changing:
                        continue
                    settled = first or now - roi.last_change >= settle
                    overdue = now - max(roi.change_start, roi.last_ocr) >= (roi.force_every or max_wait)
                    if settled or overdue:
                        t1 = time.perf_counter()
                        self._ocr_roi(roi, crop, small)
                        ocr_ms += (time.perf_counter() - t1) * 1000
                        roi.last_ocr = time.perf_counter()
                        ran = True
                        signature = tuple(sorted(ln.text for ln in roi.lines))
                        if settled:
                            roi.changing, roi.force_every = False, max_wait
                        else:
                            stable = False
                            # 画面一直在动（3D 场景）而文字没变：没必要一直高频识别，逐步拉长间隔；文字一变就恢复
                            same = signature == roi.signature
                            roi.force_every = min(_FORCE_MAX, (roi.force_every or max_wait) * 1.5) if same else max_wait
                        roi.signature = signature
                prof["diff"] += time.perf_counter() - now - ocr_ms / 1000
                prof["ocr"] += ocr_ms / 1000

                if ran:
                    t2 = time.perf_counter()
                    self._update_blocks(frame, rois, stable)
                    prof["blocks"] += time.perf_counter() - t2
                    prof["n_ocr"] += 1
                    self._stats.update(captureMs=round(capture_ms, 1), ocrMs=round(ocr_ms, 1))
                    self.statsChanged.emit(dict(self._stats))
                elif self._deferred_at and time.perf_counter() >= self._deferred_at:
                    self._dispatch(stable=True)
                # 画面静止了一阵子就放慢轮询；一有动静马上恢复
                idle = time.perf_counter() - last_activity > _IDLE_AFTER and not self._deferred_at
                self._stop.wait(max(0.005, (max(poll, _IDLE_POLL) if idle else poll) - (time.perf_counter() - t_loop)))
        finally:
            capturer.close()

    # ---- OCR ----
    def _ocr_roi(self, roi: _Roi, crop: np.ndarray, small: np.ndarray) -> None:
        """识别一个区域。可能的话只识别相对上次 OCR 变了的那一块。"""
        dirty = None
        if roi.ocr_small is not None and roi.ocr_small.shape == small.shape:
            mask = cv2.absdiff(small, roi.ocr_small) > _DIFF_THRESHOLD
            if not mask.any():
                return
            ys, xs = np.nonzero(mask)
            fx, fy = roi.w / small.shape[1], roi.h / small.shape[0]
            pad = 20
            x0, y0 = xs.min() * fx - pad, ys.min() * fy - pad
            x1, y1 = (xs.max() + 1) * fx + pad, (ys.max() + 1) * fy + pad
            # 脏区要完整包住和它相交的旧文本行，否则会把一行字切成两半
            for _ in range(2):
                for ln in roi.lines:
                    lx, ly = ln.x - roi.x, ln.y - roi.y
                    if lx < x1 and lx + ln.w > x0 and ly < y1 and ly + ln.h > y0:
                        x0, y0 = min(x0, lx - 8), min(y0, ly - 8)
                        x1, y1 = max(x1, lx + ln.w + 8), max(y1, ly + ln.h + 8)
            x0, y0 = int(max(0, x0)), int(max(0, y0))
            x1, y1 = int(min(roi.w, x1)), int(min(roi.h, y1))
            if (x1 - x0) * (y1 - y0) < 0.6 * roi.w * roi.h and x1 - x0 >= 32 and y1 - y0 >= 24:
                dirty = (x0, y0, x1, y1)
        roi.ocr_small = small

        if dirty is None:
            found = self._engine.recognize(crop, (roi.x, roi.y))
            ox, oy = roi.x, roi.y
            kept: list[TextLine] = []
        else:
            x0, y0, x1, y1 = dirty
            found = self._engine.recognize(np.ascontiguousarray(crop[y0:y1, x0:x1]), (roi.x + x0, roi.y + y0))
            ox, oy = roi.x + x0, roi.y + y0
            kept = [
                ln for ln in roi.lines
                if not (ln.x - roi.x < x1 and ln.right - roi.x > x0 and ln.y - roi.y < y1 and ln.bottom - roi.y > y0)
            ]
        for ln in found:
            ln.x += ox
            ln.y += oy
        roi.lines = kept + found

    # ---- 临时翻译 ----
    def _do_snapshot(self, frame: np.ndarray, region: list | None, hold: float) -> None:
        """把当前画面（或其中一块）识别、翻译一次。结果和连续翻译的块一起显示，停留 hold 秒。"""
        t0 = time.perf_counter()
        fh, fw = frame.shape[:2]
        if region:
            x0, y0 = int(max(0.0, region[0]) * fw), int(max(0.0, region[1]) * fh)
            x1, y1 = min(fw, x0 + max(16, int(region[2] * fw))), min(fh, y0 + max(16, int(region[3] * fh)))
        else:
            x0, y0, x1, y1 = 0, 0, fw, fh
        lines = self._engine.recognize(np.ascontiguousarray(frame[y0:y1, x0:x1]), (x0, y0))
        for ln in lines:
            ln.x += x0
            ln.y += y0
        flt = self.profile.get("filter", {})
        min_conf, min_h = flt.get("min_conf", 0.6), flt.get("min_height", 14)
        src, tgt = self.profile.get("source_lang", "auto"), self.profile.get("target_lang", "zh-CN")
        kept = [ln for ln in lines if ln.conf >= min_conf and ln.h >= min_h and not any(p.search(ln.text) for p in self._ignore)]

        snap: dict[str, Block] = {}
        pending: list[tuple[str, Block]] = []
        with self._lock:
            for b in group_lines(kept, getattr(self._engine, "font_factor", 0.8)):
                if not worth_translating(b.text, src, tgt):
                    continue
                key = normalize(b.text)
                if key in self._blocks or key in snap:
                    continue  # 连续翻译已经在显示这一块了
                b.id = "s" + uuid.uuid4().hex[:9]
                b.fg, b.bg = sample_colors(frame, b.x, b.y, b.w, b.h)
                cached = self.cache.get(self._cache_prefix + key)
                if cached is not None:
                    b.translation, b.final = cached, True
                else:
                    b.extra["requested"] = True
                    pending.append((key, b))
                snap[key] = b
            self._snap_blocks = snap
            self._snap_until = time.perf_counter() + hold if hold > 0 else float("inf")
            views = self._views_locked()
        self.blocksSynced.emit(views)
        self._stats.update(ocrMs=round((time.perf_counter() - t0) * 1000, 1), blocks=len(views))
        self.statsChanged.emit(dict(self._stats))
        self.snapshotDone.emit(len(snap))
        if pending:
            self._pool.submit(self._translate_job, pending)

    # ---- 块的维护 ----
    def _update_blocks(self, frame: np.ndarray, rois: list[_Roi], stable: bool) -> None:
        flt = self.profile.get("filter", {})
        min_conf, min_h = flt.get("min_conf", 0.6), flt.get("min_height", 14)
        src, tgt = self.profile.get("source_lang", "auto"), self.profile.get("target_lang", "zh-CN")
        lines = [
            ln for roi in rois for ln in roi.lines
            if ln.conf >= min_conf and ln.h >= min_h and not any(p.search(ln.text) for p in self._ignore)
        ]
        found = group_lines(lines, getattr(self._engine, "font_factor", 0.8))

        now = time.perf_counter()
        with self._lock:
            new: dict[str, Block] = {}
            unmatched = dict(self._blocks)
            for b in found:
                if not worth_translating(b.text, src, tgt):
                    continue
                key = normalize(b.text)
                prev = unmatched.pop(key, None)
                if prev is None:
                    # OCR 对同一行字的结果会有一两个字的抖动：位置重合、长度几乎一样、文本很像，就当成同一块
                    for k, cand in unmatched.items():
                        if (
                            abs(len(k) - len(key)) <= max(1, len(key) // 12)
                            and _iou(b, cand) > 0.5
                            and difflib.SequenceMatcher(None, key, k).ratio() > 0.85
                        ):
                            prev, key = unmatched.pop(k), k
                            break
                if prev is not None:
                    moved = abs(prev.x - b.x) > 3 or abs(prev.y - b.y) > 3 or abs(prev.w - b.w) > 6
                    if moved:
                        prev.x, prev.y, prev.w, prev.h = b.x, b.y, b.w, b.h
                        prev.font_px, prev.align, prev.lines = b.font_px, b.align, b.lines
                    prev.seen += 1
                    prev.missed = 0
                    new[key] = prev
                    continue

                grown = next((k for k, cand in unmatched.items() if _continues(cand, k, b, key)), None)
                if grown is not None:
                    # 打字机效果：同一位置的文字变长了。沿用原来的块（界面上不闪），先留着旧译文，
                    # 等文字停下来一小会儿再请求新译文——否则一句话会被翻译好几次
                    old = unmatched.pop(grown)
                    b.id, b.fg, b.bg = old.id, old.fg, old.bg
                    b.translation = old.translation
                    b.extra["ready_at"] = now + _GROW_DEBOUNCE
                else:
                    b.id = uuid.uuid4().hex[:10]
                    b.fg, b.bg = sample_colors(frame, b.x, b.y, b.w, b.h)
                cached = self.cache.get(self._cache_prefix + key)
                if cached is not None:
                    b.translation, b.final = cached, True
                new[key] = b
            if not stable:
                # 画面一直在动时偶尔会漏识别一次，多留一轮再删，免得译文闪烁
                for k, b in unmatched.items():
                    if b.missed < 1 and k not in new:
                        b.missed += 1
                        new[k] = b
            self._blocks = new
            views = self._views_locked()

        self.blocksSynced.emit(views)
        self._stats["blocks"] = len(views)
        self._dispatch(stable)

    def _dispatch(self, stable: bool) -> None:
        """把可以翻译的新块合成一个请求发出去；还在变长的块先记下时间，到点再发。"""
        now = time.perf_counter()
        self._deferred_at = 0.0
        with self._lock:
            pending = []
            for key, b in self._blocks.items():
                if b.final or b.extra.get("requested") or now < self._retry_at:
                    continue
                if not (stable or b.seen >= 2):
                    continue  # 画面一直在动时，要连续两轮都识别到才算数，过滤掉一闪而过的误识别
                ready_at = b.extra.get("ready_at", 0.0)
                if now < ready_at:
                    self._deferred_at = min(self._deferred_at or ready_at, ready_at)
                    continue
                b.extra["requested"] = True
                pending.append((key, b))
        if pending:
            self._pool.submit(self._translate_job, pending)

    # ---- 翻译 ----
    def _translate_job(self, pending: list[tuple[str, Block]]) -> None:
        items = [b.text for _, b in pending]
        t0 = time.perf_counter()
        first_ms = [0.0]

        def on_partial(i: int, text: str, final: bool) -> None:
            if not first_ms[0]:
                first_ms[0] = (time.perf_counter() - t0) * 1000
            # 是否"完成"等整批回来后统一定（要判断译文是否和原文相同），这里一律按进行中显示
            key, b = pending[i]
            b.translation = text
            if self._live(key, b):  # 这个块已经被替换掉的话（文字又变长了），就别往界面上写了
                self.blockUpdated.emit(b.id, text, False)

        with self._lock:
            history = list(self._history)
        ctx = TranslateContext(
            source_lang=self.profile.get("source_lang", "auto"),
            target_lang=self.profile.get("target_lang", "zh-CN"),
            glossary=self._terms,
            game_hint=self.profile.get("prompt", ""),
            history=history,
        )
        try:
            results = self._translator.translate(items, ctx, on_partial)
        except TranslateError as e:
            with self._lock:
                for _, b in pending:
                    b.extra["requested"] = False
                self._retry_at = time.perf_counter() + 3.0
                self._deferred_at = self._retry_at  # 画面不变也要在 3 秒后重试
            self.statusChanged.emit("error", str(e))
            return
        except Exception as e:
            if not self._stop.is_set():
                self.statusChanged.emit("error", f"翻译出错：{type(e).__name__}: {e}")
            return

        total_ms = (time.perf_counter() - t0) * 1000
        resync = False
        with self._lock:
            for (key, b), text in zip(pending, results):
                text = text.strip()
                if not text:
                    b.extra["requested"] = False  # 模型漏了这一条，下一轮再要
                    continue
                self.cache[self._cache_prefix + key] = text
                b.translation, b.final = text, True
                if normalize(text) == key:
                    b.extra["skip"] = True  # 译文和原文一样，没必要盖一层
                    resync = True
                elif len(b.text) >= 8:
                    self._history.append((b.text, text))
            self._history = self._history[-8:]
            views = self._views_locked() if resync else None
        for (key, b), text in zip(pending, results):
            if text.strip() and not b.extra.get("skip") and self._live(key, b):
                self.blockUpdated.emit(b.id, text.strip(), True)
        if views is not None:
            self.blocksSynced.emit(views)
        self._stats.update(firstTokenMs=round(first_ms[0] or total_ms), translateMs=round(total_ms))
        self.statsChanged.emit(dict(self._stats))
        self.statusChanged.emit("ok", self._status_text())
