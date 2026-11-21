"""把 Gloss 打包成一个可以直接运行的文件夹，并压成 zip。

用法（在项目根目录）：
    uv run python packaging/build.py

产物：
    dist/Gloss/Gloss.exe              解压即用，不需要装 Python
    dist/Gloss-<版本>-win64.zip       上面那个文件夹的压缩包，用来分发

打包完会用 `Gloss.exe --selftest` 跑一遍自检，自检不过就算失败。
本地翻译模型（1 GB 以上）不打进包里，用户在「设置」页点「下载」时才取。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "Gloss"
sys.path.insert(0, str(ROOT))

from gloss import __version__  # noqa: E402

# 打进包里的 OCR 模型：三个档位用到的检测和识别模型。其它语言的识别模型首次用到时再下载
KEEP_MODELS = ("PP-OCRv6_det_tiny", "PP-OCRv6_det_small", "PP-OCRv6_rec_tiny", "PP-OCRv6_rec_small", "_cls_")


def make_icon() -> Path:
    """用界面里的 SVG 图标生成 exe 用的 .ico。"""
    from PIL import Image
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    _app = QGuiApplication.instance() or QGuiApplication([])
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(str(ROOT / "gloss" / "ui" / "icon.svg")).render(painter)
    painter.end()
    png = Path(tempfile.mkdtemp()) / "icon.png"
    image.save(str(png))
    ico = ROOT / "build" / "gloss.ico"
    ico.parent.mkdir(exist_ok=True)
    Image.open(png).save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    return ico


def main() -> int:
    icon = make_icon()
    shutil.rmtree(APP, ignore_errors=True)
    cmd = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "launcher.py"),
        "--name", "Gloss", "--windowed", "--noconfirm", "--clean", "--icon", str(icon),
        "--distpath", str(DIST), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
        "--paths", str(ROOT),
        # 界面文件、内置预设：包里的非 Python 文件
        "--collect-data", "gloss",
        # 这几个库有运行时才按名字加载的模块、模型或原生库，PyInstaller 自己找不全
        "--collect-all", "rapidocr",
        "--collect-all", "onnxruntime",
        "--collect-all", "windows_capture",
        "--collect-binaries", "ctranslate2",
        "--collect-submodules", "winrt",
        "--hidden-import", "winrt.windows.foundation",
        "--hidden-import", "winrt.windows.foundation.collections",
        "--hidden-import", "winrt.windows.globalization",
        "--hidden-import", "winrt.windows.graphics.imaging",
        "--hidden-import", "winrt.windows.media.ocr",
        "--hidden-import", "winrt.windows.storage.streams",
        "--hidden-import", "anthropic",
        "--exclude-module", "tkinter",
        "--exclude-module", "pytest",
    ]
    print("running PyInstaller…", flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)

    # 去掉没用到的 OCR 模型（开发时试过的旧版本），省一百多 MB
    removed = 0
    for model in (APP / "_internal" / "rapidocr" / "models").glob("*.onnx"):
        if not any(key in model.name for key in KEEP_MODELS):
            removed += model.stat().st_size
            model.unlink()
    print(f"pruned unused OCR models: {removed / 1e6:.0f} MB", flush=True)
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, APP / name)

    # 自检：打出来的程序真的能加载界面、跑 OCR
    report = Path(tempfile.mkdtemp()) / "selftest.json"
    code = subprocess.run([str(APP / "Gloss.exe"), "--selftest", str(report)], timeout=180).returncode
    result = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {"ok": False, "steps": {"start": "程序没有写出自检结果"}}
    for name, value in result["steps"].items():
        print(f"  selftest · {name}: {'FAILED' if str(value).startswith('FAILED') else 'ok'}", flush=True)
    if code != 0 or not result["ok"]:
        print(json.dumps(result, ensure_ascii=True, indent=1))
        return 1

    archive = DIST / f"Gloss-{__version__}-win64.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(APP.rglob("*")):
            if path.is_file():
                z.write(path, Path("Gloss") / path.relative_to(APP))
    size = sum(p.stat().st_size for p in APP.rglob("*") if p.is_file())
    print(f"built {APP} ({size / 1e6:.0f} MB) -> {archive.name} ({archive.stat().st_size / 1e6:.0f} MB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
