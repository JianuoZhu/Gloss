"""截屏。两种方式，接口相同：grab() 返回目标窗口客户区的 BGR 图像。

- WindowCapturer：Windows Graphics Capture，直接拿窗口自己的画面。被别的窗口挡住也没关系，
  画面里也不会有 Gloss 的悬浮层。默认用它。
- ScreenCapturer：抓屏幕上窗口所在的那块区域。兼容性最好，但窗口被挡住时会抓到挡它的东西。
"""

from __future__ import annotations

import threading
import time

import cv2
import mss
import numpy as np

from . import win32


class CaptureUnavailable(RuntimeError):
    pass


class ScreenCapturer:
    mode = "screen"

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        # mss 的句柄是线程相关的，必须在使用它的线程里创建
        self._sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()  # 新版 mss 把入口改名成了 MSS

    def grab(self) -> np.ndarray | None:
        x, y, w, h = win32.client_rect(self.hwnd)
        if w <= 0 or h <= 0:
            return None
        shot = self._sct.grab({"left": x, "top": y, "width": w, "height": h})
        return cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)

    def close(self) -> None:
        self._sct.close()


class WindowCapturer:
    mode = "window"

    def __init__(self, hwnd: int, interval_ms: int = 100, timeout: float = 1.5) -> None:
        from windows_capture import WindowsCapture

        self.hwnd = hwnd
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        try:
            capture = WindowsCapture(
                cursor_capture=False,
                draw_border=False,
                minimum_update_interval=interval_ms,
                window_hwnd=hwnd,
            )
        except Exception as e:
            raise CaptureUnavailable(f"无法捕获该窗口：{e}") from e

        # 这个库按函数名识别回调，名字不能改
        @capture.event
        def on_frame_arrived(frame, control):
            # frame_buffer 只在回调期间有效，必须拷贝出来。每一帧都要拷，所以帧率和拷法都影响占用：
            # 文字变化用不着每秒 25 帧，10 帧足够；cvtColor 去 alpha 比 numpy 切片快一倍多（2560×1440 下 3.7 ms 对 8.9 ms）
            image = cv2.cvtColor(frame.frame_buffer, cv2.COLOR_BGRA2BGR)
            with self._lock:
                self._frame = image

        @capture.event
        def on_closed():
            pass

        self._control = capture.start_free_threaded()
        deadline = time.monotonic() + timeout
        while self._frame is None and time.monotonic() < deadline:
            time.sleep(0.02)
        if self._frame is None:
            self.close()
            raise CaptureUnavailable("窗口捕获没有返回画面")

    def grab(self) -> np.ndarray | None:
        with self._lock:
            frame = self._frame
        if frame is None:
            return None
        # 捕获到的是整个窗口（含标题栏和边框），裁出客户区
        cx, cy, cw, ch = win32.client_rect(self.hwnd)
        wx, wy, _, _ = win32.frame_bounds(self.hwnd)
        ox, oy = max(0, cx - wx), max(0, cy - wy)
        crop = frame[oy : oy + ch, ox : ox + cw]
        return crop if crop.shape[0] >= 8 and crop.shape[1] >= 8 else None

    def close(self) -> None:
        try:
            self._control.stop()
        except Exception:
            pass  # 捕获线程可能已经随窗口关闭而结束


def create_capturer(hwnd: int, mode: str = "window"):
    """按设置创建捕获器；窗口捕获不可用时退回屏幕区域捕获。"""
    if mode == "window":
        try:
            return WindowCapturer(hwnd)
        except (CaptureUnavailable, ImportError):
            pass
    return ScreenCapturer(hwnd)
