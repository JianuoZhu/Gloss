"""OCR 的"只识别变了的行"：真的跑一遍 RapidOCR（模型首次使用时会自动下载）。"""

from __future__ import annotations

from pathlib import Path

import cv2
import pytest

IMAGE = Path(__file__).parent.parent / "docs" / "demo-before.png"


@pytest.mark.skipif(not IMAGE.exists(), reason="没有测试图")
def test_unchanged_lines_are_not_recognized_again():
    from gloss.ocr import create_engine

    engine = create_engine("rapid", "auto")
    img = cv2.imread(str(IMAGE))
    first = engine.recognize(img)
    assert len(first) >= 8 and engine.reused == 0
    recognized = engine.recognized

    again = engine.recognize(img)
    assert [ln.text for ln in again] == [ln.text for ln in first]
    assert engine.recognized == recognized  # 第二遍一行都没重新识别
    assert engine.reused >= len(first)

    # 只送进来画面的下半部分（管线只识别变了的那一块时就是这样）：靠 origin 仍然认得出是同一行
    h = img.shape[0]
    lower = engine.recognize(img[h // 2 :], origin=(0, h // 2))
    assert lower and engine.recognized - recognized <= 1  # 换一张图检测，框会略有出入，偶尔有一行对不上
    recognized = engine.recognized

    # 把一行涂掉重写：只有它需要重新识别
    changed = img.copy()
    ln = max(first, key=lambda ln: ln.w)
    x, y, w, hh = int(ln.x), int(ln.y), int(ln.w), int(ln.h)
    changed[y : y + hh, x : x + w] = changed[y + 2, x + 2]
    cv2.putText(changed, "Completely different words", (x + 6, y + hh - 10), cv2.FONT_HERSHEY_SIMPLEX, hh / 45, (240, 240, 240), 2, cv2.LINE_AA)
    engine.recognize(changed)
    assert 1 <= engine.recognized - recognized <= 2
