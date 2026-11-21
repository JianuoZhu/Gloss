"""本地翻译模型的文件管理：放在哪、装没装、怎么下载。

模型和运行库都放在 %LOCALAPPDATA%\\Gloss\\local-mt，不进项目目录。
下载地址和校验值写死在这里：只从腾讯、llama.cpp 的官方仓库拿文件，并核对 SHA-256。
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

LOCAL_DIR = Path(os.environ.get("GLOSS_LOCAL_MT") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Gloss" / "local-mt")

LLAMA_DIR = LOCAL_DIR / "llama"
LLAMA_SERVER = LLAMA_DIR / "llama-server.exe"
HYMT_MODEL = LOCAL_DIR / "models" / "Hy-MT2-1.8B-Q4_K_M.gguf"
NLLB_DIR = LOCAL_DIR / "nllb-200-distilled-600M-ct2-int8"


@dataclass(frozen=True)
class Asset:
    url: str
    path: Path  # 下载到哪
    size: int  # 字节，用来算进度
    sha256: str = ""
    unzip_to: Path | None = None  # 是压缩包的话解到哪


_HF = "https://huggingface.co"
ASSETS: dict[str, list[Asset]] = {
    # 腾讯混元翻译模型 Hy-MT2 1.8B（Apache-2.0）+ 运行它的 llama.cpp（MIT，Vulkan 版，任何显卡都能用）
    "hymt": [
        Asset(
            "https://github.com/ggml-org/llama.cpp/releases/download/b12556/llama-b12556-bin-win-vulkan-x64.zip",
            LOCAL_DIR / "llama-dl" / "llama-b12556-bin-win-vulkan-x64.zip",
            38_700_000,
            "73f3346fbbad14db8f5a5b35c4e9dbae7debf306309bfc77aca4a17096cb2f93",
            LLAMA_DIR,
        ),
        Asset(
            f"{_HF}/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf",
            HYMT_MODEL,
            1_133_080_000,
            "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699",
        ),
    ],
    # Meta NLLB-200 蒸馏版 600M 的 CTranslate2 int8 转换（CC-BY-NC-4.0，禁止商用）
    "nllb": [
        Asset(f"{_HF}/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main/config.json", NLLB_DIR / "config.json", 100),
        Asset(
            f"{_HF}/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main/shared_vocabulary.txt",
            NLLB_DIR / "shared_vocabulary.txt",
            2_570_000,
        ),
        Asset(
            f"{_HF}/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main/sentencepiece.bpe.model",
            NLLB_DIR / "sentencepiece.bpe.model",
            4_850_000,
            "14bb8dfb35c0ffdea7bc01e56cea38b9e3d5efcdcb9c251d6b40538e1aab555a",
        ),
        Asset(
            f"{_HF}/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main/model.bin",
            NLLB_DIR / "model.bin",
            622_600_000,
            "ed1beaf75134de7505315a5223162f56acff397eff6b50638a500d3936fe707b",
        ),
    ],
}

LABELS = {"hymt": "混元 Hy-MT2 1.8B", "nllb": "NLLB-200 600M"}


def installed(kind: str) -> bool:
    if kind == "hymt":
        return LLAMA_SERVER.exists() and HYMT_MODEL.exists()
    if kind == "nllb":
        return all((NLLB_DIR / n).exists() for n in ("model.bin", "config.json", "shared_vocabulary.txt", "sentencepiece.bpe.model"))
    return False


def download_size(kind: str) -> int:
    return sum(a.size for a in ASSETS[kind] if not _present(a))


def _present(asset: Asset) -> bool:
    if asset.unzip_to is not None:
        return asset.unzip_to.exists() and any(asset.unzip_to.iterdir())
    return asset.path.exists()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install(kind: str, progress: Callable[[float, str], None] | None = None) -> None:
    """下载这个模型还缺的文件。progress(0~1, 当前文件名)。出错抛 RuntimeError，消息可直接给用户看。"""
    todo = [a for a in ASSETS[kind] if not _present(a)]
    total = sum(a.size for a in todo) or 1
    done = 0
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        for asset in todo:
            asset.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = asset.path.with_name(asset.path.name + ".part")
            try:
                with client.stream("GET", asset.url) as resp:
                    resp.raise_for_status()
                    with tmp.open("wb") as f:
                        for chunk in resp.iter_bytes(1 << 20):
                            f.write(chunk)
                            done += len(chunk)
                            if progress:
                                progress(min(0.99, done / total), asset.path.name)
            except httpx.HTTPError as e:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"下载 {asset.path.name} 失败：{e}") from e
            if asset.sha256 and _sha256(tmp) != asset.sha256:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"{asset.path.name} 校验失败，文件可能不完整，请重试。")
            tmp.replace(asset.path)
            if asset.unzip_to is not None:
                asset.unzip_to.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(asset.path) as z:
                    z.extractall(asset.unzip_to)
    if progress:
        progress(1.0, "")
