"""翻译后端的延迟和资源占用实测。

用法：python tests/bench_translate.py <输出.json> [后端 ...]
后端名：google nllb hymt hymt-cpu4 hymt-cpu6 hymt-cpu hymt-igpu claude openai
  - claude 需要环境变量 ANTHROPIC_API_KEY
  - openai 需要环境变量 GLOSS_BENCH_OPENAI_URL、GLOSS_BENCH_OPENAI_MODEL（可选 GLOSS_BENCH_OPENAI_KEY）
不给后端名就测所有当前可用的。会联网调用在线接口。

每个场景跑若干轮，每轮换不同的句子（避免命中缓存），报告中位数和最差值：
  ui      一条菜单文字（英文）
  line    一句日文对话
  term    一句日文对话 + 术语表
  batch8  一屏 8 条混合文本（刚进游戏、整屏都要翻的情况）
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time

import psutil

from gloss.translate import create_translator
from gloss.translate.base import Term, TranslateContext, TranslateError

UI = ["Quit to Desktop", "Load Game", "Graphics Settings", "Inventory", "Save and Exit", "Key Bindings"]
LINES = [
    "わかった。装備を整えてからすぐに向かうよ。",
    "この先の遺跡には、古代の魔導兵器が眠っていると聞いたわ。",
    "準備ができたら、北の門で待ち合わせましょう。",
    "あの塔の頂上まで登れば、村全体を見渡せるはずだ。",
    "悪いけど、今は君に構っている暇はないんだ。",
    "まさか、こんなところで再会するとは思わなかったよ。",
]
TERM_LINES = [
    "アリシア、魔導兵器の封印はもう解けかけている。",
    "レオンは昨夜から魔導兵器の調査に出ているわ。",
    "アリシアとレオンなら、きっとやり遂げてくれる。",
    "魔導兵器を動かせるのは、アリシアだけだ。",
    "レオン、アリシアを頼んだぞ。",
    "あの魔導兵器はアリシアの一族が造ったものよ。",
]
BATCH = ["New Game", "Continue", "Settings", "Quit to Desktop", "Main Quest",
         "Find the ancient relic hidden beneath the northern ruins.", "アリシア", "この先は危険だ。引き返したほうがいい。"]
GLOSSARY = [Term("アリシア", "艾莉西亚"), Term("レオン", "莱昂"), Term("魔導兵器", "魔导兵器")]
PLAIN = TranslateContext(source_lang="auto", target_lang="zh-CN")
WITH_TERMS = TranslateContext(source_lang="auto", target_lang="zh-CN", glossary=GLOSSARY)
ROUNDS = 6

CONFIGS = {
    "google": {"provider": "google"},
    "nllb": {"provider": "nllb"},
    "hymt": {"provider": "hymt", "hymt": {"device": "auto"}},
    "hymt-cpu4": {"provider": "hymt", "hymt": {"device": "cpu", "threads": 4}},
    "hymt-cpu6": {"provider": "hymt", "hymt": {"device": "cpu", "threads": 6}},
    "hymt-cpu": {"provider": "hymt", "hymt": {"device": "cpu"}},  # 不限线程
    "hymt-igpu": {"provider": "hymt", "hymt": {"device": "Vulkan1"}},
    "claude": {"provider": "claude", "claude": {"model": os.environ.get("GLOSS_BENCH_CLAUDE_MODEL", "claude-opus-5-5"), "effort": "low"}},
    "openai": {"provider": "openai_compat", "openai_compat": {
        "base_url": os.environ.get("GLOSS_BENCH_OPENAI_URL", ""), "model": os.environ.get("GLOSS_BENCH_OPENAI_MODEL", ""),
        "api_key": os.environ.get("GLOSS_BENCH_OPENAI_KEY", "")}},
}


def available(name: str) -> bool:
    if name == "claude":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if name == "openai":
        return bool(os.environ.get("GLOSS_BENCH_OPENAI_URL") and os.environ.get("GLOSS_BENCH_OPENAI_MODEL"))
    return True


def gpu_used_mb() -> float | None:
    """NVIDIA 显卡当前已用显存（整卡，不分进程；Windows 上按进程查不到）。"""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return float(out.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def cpu_seconds(proc: psutil.Process) -> float:
    t = proc.cpu_times()
    return t.user + t.system


def run(name: str) -> dict:
    me = psutil.Process()
    rss0, gpu0 = me.memory_info().rss, gpu_used_mb()
    t0 = time.perf_counter()
    tr = create_translator(CONFIGS[name])
    row: dict = {"backend": name, "init_s": round(time.perf_counter() - t0, 2)}
    server = psutil.Process(tr.server.pid) if hasattr(tr, "server") else None
    try:
        tr.translate(["Hello there, traveler."], PLAIN)  # 建立连接 / 拿令牌，不计入
        time.sleep(0.3)
        # 服务进程按独占内存算：映射进来的模型文件页面系统随时可以回收，另列一栏
        row["ram_mb"] = round(((server.memory_full_info().uss if server else 0) + me.memory_info().rss - rss0) / 1e6)
        row["mapped_mb"] = round((server.memory_info().rss - server.memory_full_info().uss) / 1e6) if server else 0
        gpu1 = gpu_used_mb()
        row["vram_mb"] = round(gpu1 - gpu0) if gpu0 is not None and gpu1 is not None else None

        cpu0, wall0 = cpu_seconds(me) + (cpu_seconds(server) if server else 0), time.perf_counter()
        samples: dict[str, list] = {}
        for label, pool, ctx in (("ui", UI, PLAIN), ("line", LINES, PLAIN), ("term", TERM_LINES, WITH_TERMS)):
            firsts, totals, outs = [], [], []
            for i in range(ROUNDS):
                first: list[float] = []
                t = time.perf_counter()
                res = tr.translate([pool[i % len(pool)]], ctx, lambda *_: first.append(time.perf_counter() - t) if not first else None)
                totals.append((time.perf_counter() - t) * 1000)
                firsts.append((first[0] if first else time.perf_counter() - t) * 1000)
                outs.append(res[0])
            samples[label] = outs
            row[f"{label}_first_ms"] = round(statistics.median(firsts))
            row[f"{label}_ms"] = round(statistics.median(totals))
            row[f"{label}_max_ms"] = round(max(totals))
        totals = []
        for i in range(3):
            items = [f"{s} " if i else s for s in BATCH]  # 末尾加空格，让在线接口不命中上一轮的缓存
            t = time.perf_counter()
            res = tr.translate(items, WITH_TERMS)
            totals.append((time.perf_counter() - t) * 1000)
        samples["batch8"] = res
        row["batch8_ms"] = round(statistics.median(totals))
        row["batch8_max_ms"] = round(max(totals))
        wall = time.perf_counter() - wall0
        cpu = cpu_seconds(me) + (cpu_seconds(server) if server else 0) - cpu0
        row["cpu_core_pct"] = round(100 * cpu / wall)  # 测试期间平均占用多少个核的百分比（100 = 一个核跑满）
        row["samples"] = samples
    finally:
        if hasattr(tr, "close"):
            tr.close()
    return row


def main() -> None:
    out_path = sys.argv[1]
    names = sys.argv[2:] or [n for n in CONFIGS if available(n)]
    rows = []
    for name in names:
        if not available(name):
            rows.append({"backend": name, "skipped": "缺少密钥或地址（见脚本开头的说明）"})
            continue
        try:
            rows.append(run(name))
        except TranslateError as e:
            rows.append({"backend": name, "error": str(e)})
        time.sleep(1.0)
        json.dump(rows, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    cols = ["backend", "init_s", "ui_ms", "line_first_ms", "line_ms", "line_max_ms", "term_ms", "batch8_ms", "batch8_max_ms", "ram_mb", "mapped_mb", "vram_mb", "cpu_core_pct"]
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join(str(r.get(c, "-")) for c in cols) + (f"   [{'error' if 'error' in r else 'skipped'}]" if "error" in r or "skipped" in r else ""))


if __name__ == "__main__":
    main()
