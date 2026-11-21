"""量 Gloss 管线自己的占用：对着一个画面不停在动的假游戏跑一段时间，看吃了多少 CPU。

用法：python tests/bench_pipeline.py [秒数=20] [宽=2560] [高=1440] [--still] [--regions] [--screen]
  --still    背景不动（对比用：视觉小说这类画面基本静止的游戏）
  --regions  只识别底部对话框，而不是整个窗口
  --screen   用屏幕区域捕获而不是窗口捕获

翻译用一个立刻返回的假后端，所以量到的只是截屏 + 变化检测 + OCR + 分块的开销。
输出里的"核"指平均占用了几个 CPU 核（1.00 = 一个核跑满）。
"""

from __future__ import annotations

import copy
import subprocess
import sys
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QCoreApplication, QTimer

from gloss import pipeline as pipeline_mod
from gloss import win32
from gloss.config import DEFAULT_PROFILE, DEFAULT_SETTINGS

HERE = Path(__file__).parent


class NullTranslator:
    def translate(self, items, ctx, on_partial=None):
        return [f"[{t}]" for t in items]


def main() -> None:
    nums = [int(a) for a in sys.argv[1:] if a.isdigit()]
    seconds, w, h = (nums + [20, 2560, 1440])[:3] if len(nums) < 3 else nums[:3]
    if len(nums) == 1:
        seconds, w, h = nums[0], 2560, 1440
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))
    app = QCoreApplication(sys.argv)
    args = [sys.executable, str(HERE / "fake_game.py"), str(w), str(h), "--background"]
    if "--still" not in flags:
        args.append("--animate")
    game = subprocess.Popen(args)
    try:
        win, end = None, time.time() + 15
        while win is None and time.time() < end:
            win = next((x for x in win32.list_windows() if x["title"] == "Gloss Test Game"), None)
            time.sleep(0.2)
        settings, profile = copy.deepcopy(DEFAULT_SETTINGS), copy.deepcopy(DEFAULT_PROFILE)
        settings["capture"]["mode"] = "screen" if "--screen" in flags else "window"
        if "--regions" in flags:
            profile["regions"] = [[0.05, 0.66, 0.9, 0.32]]
        pipeline_mod.create_translator = lambda cfg: NullTranslator()
        p = pipeline_mod.Pipeline(win["hwnd"], settings, profile)
        stats: dict = {}
        passes = [0]

        def on_stats(s: dict) -> None:
            stats.update(s)
            passes[0] += 1

        p.statsChanged.connect(on_stats)
        me = psutil.Process()
        marks: dict = {}

        def begin() -> None:  # 等模型加载完再开始计
            marks.update(cpu=sum(me.cpu_times()[:2]), t=time.perf_counter(), passes=passes[0], prof=dict(getattr(p, "profile_totals", {})))

        def finish() -> None:
            wall = time.perf_counter() - marks["t"]
            cores = (sum(me.cpu_times()[:2]) - marks["cpu"]) / wall
            n = passes[0] - marks["passes"]
            print(f"{w}x{h} {'still' if '--still' in flags else 'moving'} {'regions' if '--regions' in flags else 'full'} "
                  f"{settings['capture']['mode']}: {cores:.2f} 核, OCR {n / wall:.1f} 次/秒, 最近一次 OCR {stats.get('ocrMs', 0):.0f} ms, "
                  f"内存 {me.memory_info().rss / 1e6:.0f} MB, 文本块 {stats.get('blocks', 0)}")
            prof = getattr(p, "profile_totals", None)
            if prof:
                parts = {k: prof[k] - marks["prof"].get(k, 0) for k in prof}
                print("   各环节占用（毫秒/秒）: " + ", ".join(f"{k} {1000 * v / wall:.0f}" for k, v in parts.items() if not k.startswith("n_"))
                      + " | 次数/秒: " + ", ".join(f"{k[2:]} {v / wall:.1f}" for k, v in parts.items() if k.startswith("n_")))
            p.stop()
            p.join(3)
            app.quit()

        p.start()
        QTimer.singleShot(6000, begin)
        QTimer.singleShot(6000 + seconds * 1000, finish)
        app.exec()
    finally:
        game.kill()


if __name__ == "__main__":
    main()
