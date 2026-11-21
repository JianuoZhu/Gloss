"""全局快捷键：有哪些动作、默认按键，以及"Ctrl+Alt+T"这种写法和系统按键码之间的换算。"""

from __future__ import annotations

# (动作, 界面上的名字, 默认按键)。顺序就是界面上的顺序
ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("toggle", "开始 / 停止连续翻译", "Ctrl+Alt+T"),
    ("overlay", "显示 / 隐藏译文", "Ctrl+Alt+H"),
    ("regions", "编辑识别区域", "Ctrl+Alt+R"),
    ("snap_full", "临时翻译整个窗口", "Ctrl+Alt+F"),
    ("snap_region", "临时框选一块翻译", "Ctrl+Alt+S"),
    ("scope", "切换识别范围", "Ctrl+Alt+A"),
)
DEFAULTS = {action: keys for action, _, keys in ACTIONS}
LABELS = {action: label for action, label, _ in ACTIONS}

# RegisterHotKey 的修饰键
_MODS = {"Ctrl": 0x2, "Alt": 0x1, "Shift": 0x4, "Win": 0x8}
# Qt 的修饰键位（QML 里 event.modifiers 的值）
_QT_MODS = (("Ctrl", 0x04000000), ("Alt", 0x08000000), ("Shift", 0x02000000), ("Win", 0x10000000))

_PUNCT = {"`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC}


def _vk(name: str) -> int | None:
    """按键名 -> Windows 虚拟键码。"""
    if len(name) == 1 and (name.isdigit() or ("A" <= name <= "Z")):
        return ord(name)
    if name == "Space":
        return 0x20
    if name in _PUNCT:
        return _PUNCT[name]
    if name.startswith("F") and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
        return 0x70 + int(name[1:]) - 1
    return None


def parse(combo: str) -> tuple[int, int] | None:
    """"Ctrl+Alt+T" -> (修饰键, 虚拟键码)；空串或写法不对返回 None。"""
    parts = [p.strip() for p in combo.split("+") if p.strip()] if combo else []
    if not parts:
        return None
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            return None
        mods |= _MODS[p]
    vk = _vk(parts[-1])
    return (mods, vk) if vk is not None else None


def from_qt(key: int, modifiers: int) -> str | None:
    """把 QML 按键事件的 key / modifiers 变成 "Ctrl+Alt+T"。

    只接受适合做全局快捷键的组合：功能键可以单独用，其它键必须带 Ctrl、Alt 或 Win
    （只带 Shift 或什么都不带的字母键会让正常打字和游戏操作全被截走）。不合适时返回 None。
    """
    if 0x41 <= key <= 0x5A or 0x30 <= key <= 0x39:
        name = chr(key)
    elif key == 0x20:
        name = "Space"
    elif 0x01000030 <= key <= 0x01000047:  # Qt.Key_F1 … Qt.Key_F24
        name = f"F{key - 0x01000030 + 1}"
    elif key == 0x60:
        name = "`"
    elif 0 < key < 0x80 and chr(key) in _PUNCT:
        name = chr(key)
    else:
        return None
    held = [label for label, bit in _QT_MODS if modifiers & bit]
    if not name.startswith("F") or len(name) == 1:
        if not {"Ctrl", "Alt", "Win"} & set(held):
            return None
    return "+".join([*held, name])
