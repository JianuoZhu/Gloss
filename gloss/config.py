"""设置与游戏预设的读写。数据放在 %APPDATA%\\Gloss，不进项目目录。"""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from importlib import resources
from pathlib import Path

from . import hotkeys
from .translate.registry import default_settings

APP_DIR = Path(os.environ.get("GLOSS_HOME") or Path(os.environ.get("APPDATA", Path.home())) / "Gloss")

DEFAULT_SETTINGS: dict = {
    "active_profile": "default",
    "theme": "light",  # light 浅色 | paper 暖纸 | dark 深色 | midnight 墨蓝 | system 跟随系统的浅色 / 深色
    # provider 是引擎 id；每个引擎自己的设置项（密钥、模型名等）由登记表生成，放在同名的子项里
    "translator": {"provider": "google", **default_settings()},
    "ocr": {"engine": "rapid", "model": "balanced", "det_side": 1280, "use_gpu": False, "threads": 4},
    "capture": {"mode": "window"},  # window 窗口捕获 | screen 屏幕区域
    "hotkeys": dict(hotkeys.DEFAULTS),  # 动作 -> "Ctrl+Alt+T" 这样的按键；空串 = 不用这个快捷键
    "quick": {"hold_s": 10},  # 临时翻译的译文停留几秒；0 = 一直留到再按一次
    "pipeline": {"poll_ms": 80, "settle_ms": 140, "max_wait_ms": 1000},
}

DEFAULT_PROFILE: dict = {
    "id": "default",
    "name": "默认",
    "match": {"exe": "", "title": ""},  # 这份预设属于哪个游戏：exe 文件名（不分大小写）；标题用正则
    "source_lang": "auto",
    "target_lang": "zh-CN",
    "regions": [],  # [[x, y, w, h]]，相对窗口客户区的 0~1 比例；空 = 整个窗口
    "scope": "regions",  # 连续翻译识别哪里：regions 只识别上面的固定区域 | full 整个窗口（区域留着不删）
    "display": {
        "mode": "inplace",  # inplace 原位覆盖 | float 悬浮在原文旁（不遮原文）| subtitle 字幕条
        "background": "auto",  # 原位覆盖的底：auto 取原画面底色 | color 用 bg_color | none 不要底、只描边
        "opacity": 1.0,  # 原位覆盖时底框的不透明度
        "float_opacity": 0.72,  # 悬浮标签和字幕条的不透明度
        "font_scale": 1.0,
        "font_family": "",
        "font_weight": "medium",  # normal | medium | bold
        "text_color": "",  # 译文颜色，"" = 自动（原位覆盖跟随原文，其它用白色）
        "bg_color": "",  # 底色，"" = 默认深色（原位覆盖在 background 为 color 时才用它）
        "outline": False,  # 给文字加一圈描边，背景花的时候更好认
    },
    "filter": {"min_conf": 0.6, "min_height": 14, "ignore": []},
    "glossary": [],  # [{"src": "...", "dst": "...", "note": "..."}]
    "prompt": "",  # 给 LLM 的游戏背景/语气说明
}


_LEGACY_TEMPLATES = {"jrpg-dialogue", "subtitle-en"}


def _merge(base: dict, override: dict) -> dict:
    """用 override 覆盖 base 的同名键（递归），base 里新增的键保留默认值。"""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def set_path(data: dict, dotted: str, value) -> None:
    """set_path(d, "display.opacity", 0.8)"""
    keys = dotted.split(".")
    for k in keys[:-1]:
        data = data.setdefault(k, {})
    data[keys[-1]] = value


class Store:
    """设置 + 全部预设。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or APP_DIR
        self.profiles_dir = self.root / "profiles"
        self.cache_dir = self.root / "cache"
        first_run = not (self.root / "settings.json").exists()
        self.settings = _merge(DEFAULT_SETTINGS, _read(self.root / "settings.json"))
        if first_run:
            from . import local_mt

            # 本地翻译模型已经装好的话，第一次启动就直接用它：比在线接口快，也不会被限流
            if local_mt.installed("hymt"):
                self.settings["translator"]["provider"] = "hymt"
        self.profiles: dict[str, dict] = {}
        self._load_profiles()

    # ---- 设置 ----
    def save_settings(self) -> None:
        _write(self.root / "settings.json", self.settings)

    # ---- 预设 ----
    def _load_profiles(self) -> None:
        first_run = not self.profiles_dir.exists()
        if first_run:
            for res in resources.files("gloss.presets").iterdir():
                if res.name.endswith(".json"):
                    data = json.loads(res.read_text(encoding="utf-8"))
                    _write(self.profiles_dir / res.name, data)
        for path in sorted(self.profiles_dir.glob("*.json")):
            data = _read(path)
            if not data.get("id"):
                continue
            # 早期版本自带过两份"按游戏类型"的模板。预设现在是一个游戏一份，没被用过的旧模板直接清掉
            if data["id"] in _LEGACY_TEMPLATES and not data.get("match", {}).get("exe") and not data.get("glossary"):
                path.unlink(missing_ok=True)
                continue
            self.profiles[data["id"]] = _merge(DEFAULT_PROFILE, data)
        if self.profiles.get("default", {}).get("name") == "通用":
            self.profiles["default"]["name"] = "默认"
        if "default" not in self.profiles:
            self.profiles["default"] = copy.deepcopy(DEFAULT_PROFILE)
            self.save_profile("default")
        if self.settings.get("active_profile") not in self.profiles:
            self.settings["active_profile"] = "default"

    def profile(self, pid: str | None = None) -> dict:
        pid = pid or self.settings.get("active_profile", "default")
        return self.profiles.get(pid) or self.profiles["default"]

    def save_profile(self, pid: str) -> None:
        _write(self.profiles_dir / f"{pid}.json", self.profiles[pid])

    def new_game_profile(self, name: str, exe: str, save: bool = True) -> str:
        """给一个游戏建专属预设：设置从默认预设复制，绑定到它的 exe。save=False 时先只放在内存里。"""
        pid = uuid.uuid4().hex[:8]
        data = copy.deepcopy(self.profiles["default"])
        data.update(id=pid, name=name, match={"exe": exe, "title": ""})
        self.profiles[pid] = data
        if save:
            self.save_profile(pid)
        return pid

    def delete_profile(self, pid: str) -> None:
        if pid == "default" or pid not in self.profiles:
            return
        del self.profiles[pid]
        (self.profiles_dir / f"{pid}.json").unlink(missing_ok=True)
        if self.settings.get("active_profile") == pid:
            self.settings["active_profile"] = "default"
            self.save_settings()

    def match_profile(self, exe: str, title: str) -> str | None:
        """找出为这个窗口准备的预设；没有就返回 None。"""
        for pid, p in self.profiles.items():
            m = p.get("match", {})
            if m.get("exe") and m["exe"].lower() == exe.lower():
                return pid
            if m.get("title"):
                try:
                    if re.search(m["title"], title, re.IGNORECASE):
                        return pid
                except re.error:
                    continue
        return None

    # ---- 翻译缓存 ----
    def load_cache(self, pid: str) -> dict:
        return _read(self.cache_dir / f"{pid}.json")

    def save_cache(self, pid: str, cache: dict) -> None:
        # 只留最近的一部分，避免文件无限增长
        items = list(cache.items())[-4000:]
        _write(self.cache_dir / f"{pid}.json", dict(items))
