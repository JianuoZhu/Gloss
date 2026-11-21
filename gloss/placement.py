"""悬浮模式下译文标签放在原文的哪一侧。

目标是不遮字：标签不能盖住自己的原文（靠摆在外侧保证），也尽量不盖别的原文和别的标签。
每块原文有四个候选位置（上、下、右、左），挑遮挡面积最小的；一样好时按"上、下、右、左"的顺序选。
"""

from __future__ import annotations

ABOVE, BELOW, RIGHT, LEFT = 0, 1, 2, 3
Rect = tuple[float, float, float, float]  # x, y, w, h


def _overlap(a: Rect, b: Rect) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _outside(r: Rect, viewport: tuple[float, float]) -> float:
    vw, vh = viewport
    if vw <= 0 or vh <= 0:
        return 0.0
    return r[2] * r[3] - _overlap(r, (0.0, 0.0, vw, vh))


def place_labels(
    blocks: list[tuple[float, float, float, float, str]],
    sizes: list[tuple[float, float]],
    viewport: tuple[float, float] = (0.0, 0.0),
    previous: list[int | None] | None = None,
    gap: float = 6.0,
) -> list[tuple[int, float]]:
    """blocks: 每块原文的 (x, y, w, h, 对齐)；sizes: 对应标签的 (宽, 高)。

    返回每个标签的 (哪一侧, 放在上/下方时的 x)。previous 是上一次的选择：
    差不多好的时候沿用它，免得译文逐字出来、标签变宽的过程中在两侧之间来回跳。
    """
    n = len(blocks)
    out: list[tuple[int, float]] = [(ABOVE, 0.0)] * n
    placed: list[Rect] = []
    for i in sorted(range(n), key=lambda i: (blocks[i][1], blocks[i][0])):
        bx, by, bw, bh, align = blocks[i]
        w, h = sizes[i]
        x0 = bx if align == "left" else bx + (bw - w) / 2 if align == "center" else bx + bw - w
        if viewport[0] > 0:
            x0 = min(max(4.0, x0), max(4.0, viewport[0] - w - 4.0))
        candidates = {
            ABOVE: (x0, by - gap - h),
            BELOW: (x0, by + bh + gap),
            RIGHT: (bx + bw + gap, by + (bh - h) / 2),
            LEFT: (bx - gap - w, by + (bh - h) / 2),
        }
        area = max(1.0, w * h)
        best_side, best_cost = ABOVE, float("inf")
        for side, (x, y) in candidates.items():
            rect = (x, y, w, h)
            cost = sum(_overlap(rect, blocks[j][:4]) for j in range(n) if j != i)
            cost += 1.5 * sum(_overlap(rect, p) for p in placed)
            cost += 3.0 * _outside(rect, viewport)
            cost += side * 0.002 * area  # 一样好时的偏好顺序
            if previous and previous[i] == side:
                cost -= 0.08 * area
            if cost < best_cost:
                best_side, best_cost = side, cost
        x, y = candidates[best_side]
        placed.append((x, y, w, h))
        out[i] = (best_side, x0)
    return out
