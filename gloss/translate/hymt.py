"""腾讯混元翻译模型 Hy-MT2（1.8B），通过随 Gloss 管理的 llama.cpp 服务进程在本机运行。

它是专门做翻译的模型：一次翻一段文本，原生支持术语表和背景信息，不需要也不适合通用聊天式的提示词。
服务进程只在翻译进行时存在，停止翻译就退出、释放内存；Gloss 异常退出时它也会被系统一并结束。
"""

from __future__ import annotations

import ctypes
import json
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path

import httpx

from ..local_mt import HYMT_MODEL, LLAMA_SERVER, LOCAL_DIR, installed
from .base import PartialCallback, TranslateContext, TranslateError, relevant_terms

# 提示词里要用语言的全称：中文提示词用中文名，英文提示词用英文名（模型说明里的要求）
_ZH_NAMES = {"zh-CN": "中文", "zh": "中文", "zh-TW": "繁体中文", "en": "英语", "ja": "日语", "ko": "韩语",
             "ru": "俄语", "fr": "法语", "de": "德语", "es": "西班牙语"}
_EN_NAMES = {"zh-CN": "Chinese", "zh": "Chinese", "zh-TW": "Traditional Chinese", "en": "English", "ja": "Japanese",
             "ko": "Korean", "ru": "Russian", "fr": "French", "de": "German", "es": "Spanish"}

# 模型说明推荐的采样参数
_SAMPLING = {"temperature": 0.7, "top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05}
_SLOTS = 4  # 同时翻译的条数
_CTX_PER_SLOT = 1024  # 每条请求的上下文长度；游戏里的一段文字远用不完，调小是为了省显存（实测 2048 时多占约 260 MB）
_MIN_CONTEXT_CHARS = 12
_AUTO_CPU_THREADS = 6  # 自动退到 CPU 时用几个线程：实测 6 线程单句约 0.4 秒，再多收益不大、还和游戏抢 CPU


def build_prompt(text: str, ctx: TranslateContext) -> str:
    """按 Hy-MT2 的官方模板拼提示词。有命中的术语用术语模板，否则有背景信息就用背景模板。"""
    text = " ".join(text.split())
    terms = relevant_terms(ctx.glossary, [text])
    # 背景信息只给够长的句子用：短标签（人名、菜单项）配上背景，模型会把背景里的话也译出来
    background = _background(ctx, text) if len(text) >= _MIN_CONTEXT_CHARS else ""
    if ctx.target_lang.startswith("zh"):
        target = _ZH_NAMES.get(ctx.target_lang, "中文")
        ask = f"将以下文本翻译为{target}，注意只需要输出翻译后的结果，不要额外解释：\n\n{text}"
        if terms:
            rows = "\n".join(f"{t.src} 翻译成 {t.dst}" for t in terms)
            return f"参考下面的翻译：\n{rows}\n\n{ask}"
        if background:
            return f"【背景信息】\n{background}\n\n请结合背景信息将以下文本翻译为{target}。\n\n【待翻译文本】\n{text}"
        return ask
    target = _EN_NAMES.get(ctx.target_lang, ctx.target_lang)
    if terms:
        rows = "\n".join(f"{t.src} translates to {t.dst}" for t in terms)
        return (
            f"Reference the following translations:\n{rows}\n\nTranslate the following text into {target}. "
            f"Note that you must ONLY output the translated result without any additional explanation:\n\n{text}"
        )
    if background:
        return (
            f"[Background Information]\n{background}\n\nPlease translate the following text into {target}, "
            f"taking the provided background information into consideration.\n\n[Source Text]\n{text}"
        )
    return (
        f"Translate the following text into {target}. Note that you should only output the translated result "
        f"without any additional explanation:\n\n{text}"
    )


def _background(ctx: TranslateContext, text: str) -> str:
    parts = []
    if ctx.game_hint.strip():
        parts.append(ctx.game_hint.strip())
    earlier = [src for src, _ in ctx.history[-3:] if src != text]
    if earlier:
        parts.append("前文：\n" + "\n".join(earlier))
    return "\n".join(parts)


def gpu_is_busy() -> bool | None:
    """独立显卡是不是正被游戏占着。查不到（不是 NVIDIA 显卡，或没有驱动自带的工具）时返回 None。

    实测：显卡空闲时模型跑在显卡上单句约 85 ms；游戏把显卡占到 98% 时掉到约 1 秒，反而不如 CPU（约 0.4 秒）。
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
        util, total, used = (float(v) for v in out.strip().splitlines()[0].split(","))
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None
    return util >= 60 or total - used < 2200  # 占用率高，或者剩下的显存放不下模型（约 1.4 GB，留些余量）


def resolve_device(device: str, threads: int, busy: bool | None) -> tuple[str, int, str]:
    """把"自动"落实成具体设备。返回 (设备, 线程数, 要告诉用户的话)。"""
    if device == "auto" and busy:
        return "cpu", threads or _AUTO_CPU_THREADS, "显卡正被游戏占用，翻译模型改用 CPU"
    return device, threads, ""


def list_devices() -> list[str]:
    """llama.cpp 能用的显卡，形如 ["Vulkan0: NVIDIA GeForce RTX ...", ...]。"""
    if not LLAMA_SERVER.exists():
        return []
    try:
        out = subprocess.run(
            [str(LLAMA_SERVER), "--list-devices"], capture_output=True, text=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip().split(" (")[0] for line in out.splitlines() if line.strip().startswith("Vulkan")]


def _kill_with_parent(proc: subprocess.Popen) -> None:
    """把子进程放进一个"句柄关闭即结束"的作业对象里：Gloss 不管怎么退出，服务进程都不会留下来。"""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("Basic", BasicLimits), ("Io", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    info = ExtendedLimits()
    info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = ExtendedLimitInformation
    k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle)))
    proc._gloss_job = job  # 句柄跟着进程对象活着；本进程一结束句柄就关，子进程随之结束


class LlamaServer:
    """一个 llama-server 子进程。device: "auto"（第一块显卡）、"cpu"、或 "Vulkan1" 这样的设备名。"""

    def __init__(self, model: Path, device: str = "auto", threads: int = 0) -> None:
        self.model, self.device, self.threads = model, device, threads
        self.port = 0
        self._proc: subprocess.Popen | None = None
        self._log = LOCAL_DIR / "llama-server.log"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def pid(self) -> int:
        return self._proc.pid if self._proc else 0

    def start(self, timeout: float = 60.0) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        cmd = [str(LLAMA_SERVER), "-m", str(self.model), "--host", "127.0.0.1", "--port", str(self.port),
               "-c", str(_CTX_PER_SLOT * _SLOTS), "-np", str(_SLOTS), "--offline"]
        if self.device == "cpu":
            cmd += ["-dev", "none", "-ngl", "0"]
        else:
            cmd += ["-ngl", "99"]
            if self.device != "auto":
                cmd += ["-dev", self.device]
        if self.threads:
            cmd += ["-t", str(self.threads)]
        log = self._log.open("w", encoding="utf-8", errors="replace")
        self._proc = subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(LLAMA_SERVER.parent),
            # 低于普通优先级：和游戏抢 CPU 时让着游戏
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS,
        )
        _kill_with_parent(self._proc)
        deadline = time.monotonic() + timeout
        with httpx.Client(timeout=2.0) as client:
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    raise TranslateError(f"本地翻译模型启动失败（见 {self._log}）。")
                try:
                    if client.get(f"{self.url}/health").status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
        self.stop()
        raise TranslateError("本地翻译模型加载超时。")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None


class HyMTTranslator:
    name = "hymt"

    def __init__(self, device: str = "auto", threads: int = 0) -> None:
        if not installed("hymt"):
            raise TranslateError("还没有下载混元翻译模型：到「引擎」页点「下载」。")
        device, threads, self.notice = resolve_device(device, threads, gpu_is_busy() if device == "auto" else None)
        self.server = LlamaServer(HYMT_MODEL, device, threads)
        self.server.start()
        self._client = httpx.Client(base_url=self.server.url, timeout=httpx.Timeout(30.0, connect=3.0))
        self._pool = ThreadPoolExecutor(max_workers=_SLOTS, thread_name_prefix="gloss-hymt")
        self._warm_up()

    def _warm_up(self) -> None:
        """显卡后端第一次遇到更大的批次时要花几秒准备（实测 2–4 秒）。启动时用一批够长的请求把这笔开销付掉，
        之后正常的翻译请求就不会再撞上它。"""
        filler = "这是一段用来预热的文字，内容本身没有意义。" * 24
        body = {"messages": [{"role": "user", "content": f"将以下文本翻译为英语：\n\n{filler}"}], "max_tokens": 8, **_SAMPLING}
        try:
            list(self._pool.map(lambda _: self._client.post("/v1/chat/completions", json=body), range(_SLOTS)))
        except httpx.HTTPError:
            pass  # 预热失败不影响使用，只是第一批会慢

    def _one(self, i: int, text: str, ctx: TranslateContext, on_partial: PartialCallback | None) -> str:
        body = {
            "messages": [{"role": "user", "content": build_prompt(text, ctx)}],
            "stream": True,
            "max_tokens": min(400, 64 + 3 * len(text)),
            **_SAMPLING,
        }
        out = ""
        with self._client.stream("POST", "/v1/chat/completions", json=body) as resp:
            if resp.status_code >= 400:
                raise TranslateError(f"本地翻译模型返回 {resp.status_code}：{resp.read().decode('utf-8', 'replace')[:200]}")
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    piece = json.loads(data)["choices"][0].get("delta", {}).get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if piece:
                    out += piece
                    if on_partial:
                        on_partial(i, out.strip(), False)
        return " ".join(out.split())  # 一段译文只占一行

    def translate(self, items: list[str], ctx: TranslateContext, on_partial: PartialCallback | None = None) -> list[str]:
        try:
            return list(self._pool.map(lambda pair: self._one(pair[0], pair[1], ctx, on_partial), enumerate(items)))
        except httpx.HTTPError as e:
            raise TranslateError(f"本地翻译模型没有响应：{e}") from e

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._client.close()
        self.server.stop()
