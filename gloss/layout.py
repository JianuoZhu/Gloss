"""把 OCR 的行整理成"块"，并估计每块的字号、对齐和颜色。

译文要按原文的排版覆盖回去，所以这里决定了悬浮层长什么样：
- 换行的段落合成一块（整段一起翻译，译文在原段落的框里重新折行）；
- 菜单项、按钮这类短标签各自成块（逐个原位替换）；
- 字号取自原文行高，前景/背景色取自原画面。
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np

from .types import Block, TextLine

_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯ｦ-ﾟ]")
_KANA_RE = re.compile(r"[぀-ヿｦ-ﾟ]")
_HANGUL_RE = re.compile(r"[가-힯]")
_HAN_RE = re.compile(r"[㐀-䶿一-鿿]")


def has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def normalize(text: str) -> str:
    """用于判断"是不是同一句话"的规范形式：去空白、统一全半角和大小写。"""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", text).lower()


def worth_translating(text: str, source_lang: str = "auto", target_lang: str = "zh-CN") -> bool:
    """过滤掉没必要翻译的内容：纯数字/符号、过短的拉丁缩写、已经是目标语言的文字。"""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    if not has_cjk(text):
        return len(letters) >= 3
    if target_lang.startswith("zh") and source_lang != "ja":
        # 没有假名和谚文的汉字串多半已经是中文；明确指定源语言是日语时才翻译纯汉字词
        if not _KANA_RE.search(text) and not _HANGUL_RE.search(text):
            return False
    if target_lang.startswith("ja") and _KANA_RE.search(text):
        return False
    if target_lang.startswith("ko") and _HANGUL_RE.search(text):
        return False
    return True


def _is_long(line: TextLine) -> bool:
    """这一行像不像"被折行的句子的一部分"。折行的行会占满容器宽度，所以一定不短。"""
    t = line.text.strip()
    cjk = len(_CJK_RE.findall(t))
    if cjk >= 9:
        return True
    return len(t.split()) >= 4 or len(t) >= 20


def _same_paragraph(a: TextLine, b: TextLine) -> bool:
    """a 在上、b 在下，它们是否属于同一段。"""
    h = min(a.h, b.h)
    if max(a.h, b.h) > 1.5 * h:
        return False
    gap = b.y - a.bottom
    if gap < -0.5 * h or gap > 0.6 * h:
        return False
    overlap = min(a.right, b.right) - max(a.x, b.x)
    if overlap < 0.3 * min(a.w, b.w):
        return False
    aligned = min(abs(a.x - b.x), abs(a.cx - b.cx), abs(a.right - b.right)) <= 1.2 * h
    if not aligned:
        return False
    # 菜单项也是上下紧挨、左对齐的短行；区别在于段落里非末行一定是长行
    return _is_long(a) and a.w >= 0.6 * b.w


def _join(lines: list[TextLine]) -> str:
    out = ""
    for ln in lines:
        t = ln.text.strip()
        if not out:
            out = t
        elif has_cjk(out[-1]) or has_cjk(t[:1]):
            out += t
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha():
            out = out[:-1] + t  # 英文连字符断词
        else:
            out += " " + t
    return out


def _glyph_height(line: TextLine) -> float:
    """把 OCR 行框的高度换算成"看起来一样大的方块字"的高度。"""
    h = line.h
    if not has_cjk(line.text):
        if any(c in "gjpqy" for c in line.text):
            h *= 0.86  # 行框被下伸的笔画撑高了
        h *= 0.9  # 同样字号下，拉丁字母比方块字显小
    return h


def _align(lines: list[TextLine]) -> str:
    if len(lines) < 2:
        return "left"
    spread = {
        "left": np.ptp([ln.x for ln in lines]),
        "center": np.ptp([ln.cx for ln in lines]),
        "right": np.ptp([ln.right for ln in lines]),
    }
    # 末行通常比较短：左对齐段落的右边缘本来就不齐，所以优先判左
    best = min(spread, key=lambda k: (spread[k], ("left", "center", "right").index(k)))
    return best


def group_lines(lines: list[TextLine], font_factor: float = 0.74) -> list[Block]:
    """把行合并成块。font_factor 是"译文字号 / OCR 行框高度"，不同引擎的行框松紧不同。"""
    lines = sorted(lines, key=lambda ln: (ln.y, ln.x))
    n = len(lines)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _same_paragraph(lines[i], lines[j]):
                parent[find(j)] = find(i)

    groups: dict[int, list[TextLine]] = {}
    for i, ln in enumerate(lines):
        groups.setdefault(find(i), []).append(ln)

    blocks: list[Block] = []
    for members in groups.values():
        members.sort(key=lambda ln: ln.y)
        x0 = min(ln.x for ln in members)
        y0 = min(ln.y for ln in members)
        x1 = max(ln.right for ln in members)
        y1 = max(ln.bottom for ln in members)
        line_h = float(np.median([_glyph_height(ln) for ln in members]))
        blocks.append(
            Block(
                lines=members,
                text=_join(members),
                x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                font_px=max(9.0, line_h * font_factor),
                align=_align(members),
            )
        )

    # 单行块自己看不出对齐方式，要靠邻居判断：两个单行块中心对齐、左边缘明显不齐，说明是居中的菜单。
    # 证据要够强（左边缘差一个字高以上），否则左对齐列表里宽度相近的两项会被误判。
    singles = [b for b in blocks if not b.multiline]

    def centered_with(b: Block, o: Block) -> bool:
        return abs((b.x + b.w / 2) - (o.x + o.w / 2)) < 0.25 * min(b.h, o.h)

    for b in singles:
        if any(o is not b and centered_with(b, o) and abs(b.x - o.x) > min(b.h, o.h) for o in singles):
            b.align = "center"
    # 再把和"已确定居中的块"中心对齐的块也算进去（宽度和邻居差不多的那一项）
    for b in singles:
        if b.align != "center" and any(o.align == "center" and centered_with(b, o) for o in singles):
            b.align = "center"

    blocks.sort(key=lambda b: (b.y, b.x))
    return blocks


def _hex(bgr) -> str:
    b, g, r = (int(max(0, min(255, round(float(v))))) for v in bgr)
    return f"#{r:02X}{g:02X}{b:02X}"


def _luma(bgr) -> float:
    return 0.114 * bgr[0] + 0.587 * bgr[1] + 0.299 * bgr[2]


def sample_colors(frame: np.ndarray, x: float, y: float, w: float, h: float) -> tuple[str, str]:
    """从原画面里取这块文字的 (前景色, 背景色)。

    背景 = 框内出现最多的颜色；前景 = 和背景差得足够远的像素里出现最多的颜色。
    """
    fh, fw = frame.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(fw, int(x + w) + 1), min(fh, int(y + h) + 1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return "#FFFFFF", "#101216"
    crop = frame[y0:y1, x0:x1]
    step = max(1, int(max(crop.shape[0] / 48, crop.shape[1] / 256)))
    px = crop[::step, ::step].reshape(-1, 3).astype(np.int32)

    codes = ((px[:, 0] >> 4) << 8) | ((px[:, 1] >> 4) << 4) | (px[:, 2] >> 4)
    bg_code = np.bincount(codes, minlength=4096).argmax()
    bg = px[codes == bg_code].mean(axis=0)

    far = np.abs(px - bg).sum(axis=1) > 120
    if far.sum() >= max(6, 0.02 * len(px)):
        fcodes = codes[far]
        fg = px[far][fcodes == np.bincount(fcodes, minlength=4096).argmax()].mean(axis=0)
    else:
        fg = np.array([255, 255, 255]) if _luma(bg) < 128 else np.array([16, 16, 16])
    if abs(_luma(fg) - _luma(bg)) < 60:
        fg = np.array([255, 255, 255]) if _luma(bg) < 128 else np.array([16, 16, 16])
    return _hex(fg), _hex(bg)
