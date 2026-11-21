"""RapidOCR（ONNX 版 PaddleOCR）。

默认配置是为文档准备的，直接用在游戏画面上又慢又费 CPU。这里做了几处针对性的改动（数字是在开发机上实测的）：

- 检测前把长边缩到 det_side，而不是把短边放大；关掉方向分类器。
- 关掉 onnxruntime 的线程空转。默认情况下推理线程在两次识别之间会原地空转等活干：
  一次 0.27 秒的识别、每 0.9 秒一次，本该占不到 1 个核，实际占了 5.4 个核。关掉后是 0.8 个核，耗时不变。
- 检测和识别分两步走，只识别"和上次不一样"的文字行。画面一直在动的游戏里要反复识别同一屏文字，
  其中检测必须每次做，但识别（占一多半时间）对没变的行可以直接用上次的结果。

模型档位（检测模型 / 识别模型）。tiny 识别模型认不好假名，所以默认用 balanced：
  fast      tiny / tiny    只适合中文和英文
  balanced  tiny / small
  accurate  small / small  检测更稳，再慢一些
"""

from __future__ import annotations

import cv2
import numpy as np

from ..types import TextLine

# 源语言 -> (识别模型语言, 模型版本, 模型规格)；None 表示用 PP-OCRv6 多语言模型
_SPECIAL_REC = {
    "ko": ("KOREAN", "PPOCRV5", "MOBILE"),
    "ru": ("CYRILLIC", "PPOCRV5", "MOBILE"),
    "fr": ("LATIN", "PPOCRV5", "MOBILE"),
    "de": ("LATIN", "PPOCRV5", "MOBILE"),
    "es": ("LATIN", "PPOCRV5", "MOBILE"),
}

_THUMB = (48, 12)  # 用来判断"这一行的像素变没变"的缩略图尺寸
_SAME = 7.0  # 两张缩略图平均灰度差小于它就算没变
_CACHE_MAX = 400


def _no_spinning() -> None:
    """让 RapidOCR 创建的 onnxruntime 会话不要线程空转（它自己的配置里没有这一项，只能在创建处补上）。"""
    from rapidocr.inference_engine.onnxruntime import main as ort_main

    cls = ort_main.OrtInferSession
    if getattr(cls, "_gloss_no_spin", False):
        return
    original = cls._init_sess_opts

    def patched(cfg):
        opts = original(cfg)
        opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
        return opts

    cls._init_sess_opts = staticmethod(patched)
    cls._gloss_no_spin = True


class RapidOcr:
    name = "rapid"
    font_factor = 0.70  # PP-OCR 的行框比字形高出一圈

    def __init__(
        self,
        source_lang: str = "auto",
        model: str = "balanced",
        det_side: int = 1280,
        threads: int = 4,
        use_gpu: bool = False,
    ) -> None:
        from rapidocr import RapidOCR
        from rapidocr.utils.typings import LangRec, ModelType, OCRVersion

        _no_spinning()
        det_size, rec_size = {
            "fast": (ModelType.TINY, ModelType.TINY),
            "balanced": (ModelType.TINY, ModelType.SMALL),
            "accurate": (ModelType.SMALL, ModelType.SMALL),
        }.get(model, (ModelType.TINY, ModelType.SMALL))
        params = {
            "Global.log_level": "error",
            "Global.use_cls": False,
            "Global.text_score": 0.0,  # 置信度过滤交给管线
            "Det.model_type": det_size,
            "Det.limit_type": "max",
            "Det.limit_side_len": int(det_side),
            "Rec.model_type": rec_size,
            "EngineConfig.onnxruntime.intra_op_num_threads": int(threads),
            "EngineConfig.onnxruntime.use_dml": bool(use_gpu),
        }
        special = _SPECIAL_REC.get(source_lang)
        if special:
            lang, version, special_size = special
            params["Rec.lang_type"] = getattr(LangRec, lang)
            params["Rec.ocr_version"] = getattr(OCRVersion, version)
            params["Rec.model_type"] = getattr(ModelType, special_size)
        self._engine = RapidOCR(params=params)
        self._cache: list[dict] = []  # 最近识别过的行：位置、缩略图、文字
        self._pass = 0
        self.recognized = 0  # 累计真正跑了识别模型的行数
        self.reused = 0  # 累计直接沿用上次结果的行数

    def recognize(self, bgr: np.ndarray, origin: tuple[int, int] = (0, 0)) -> list[TextLine]:
        """origin 是这张图左上角在整个画面里的位置：同一行文字不管是随整屏还是随局部送进来，都能认出是同一行。"""
        det = self._engine(bgr, use_det=True, use_cls=False, use_rec=False)
        if det is None or det.boxes is None or len(det.boxes) == 0:
            return []
        self._pass += 1
        h, w = bgr.shape[:2]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        lines: list[TextLine] = []
        for box in det.boxes:
            x0, y0 = max(0, int(box[:, 0].min())), max(0, int(box[:, 1].min()))
            x1, y1 = min(w, int(box[:, 0].max()) + 1), min(h, int(box[:, 1].max()) + 1)
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            thumb = cv2.resize(gray[y0:y1, x0:x1], _THUMB, interpolation=cv2.INTER_AREA).astype(np.int16)
            gx, gy = origin[0] + x0, origin[1] + y0
            hit = self._lookup(gx, gy, x1 - x0, y1 - y0, thumb)
            if hit is None:
                rec = self._engine(bgr[y0:y1, x0:x1], use_det=False, use_cls=False, use_rec=True)
                text = rec.txts[0].strip() if rec is not None and rec.txts else ""
                score = float(rec.scores[0]) if rec is not None and rec.scores else 0.0
                hit = {"x": gx, "y": gy, "w": x1 - x0, "h": y1 - y0, "thumb": thumb, "text": text, "score": score}
                self._cache.append(hit)
                self.recognized += 1
            else:
                self.reused += 1
            hit["seen"] = self._pass
            if hit["text"]:
                lines.append(TextLine(hit["text"], float(x0), float(y0), float(x1 - x0), float(y1 - y0), hit["score"]))
        if len(self._cache) > _CACHE_MAX:
            self._cache = sorted(self._cache, key=lambda e: e["seen"])[-_CACHE_MAX // 2 :]
        return lines

    def _lookup(self, x: int, y: int, w: int, h: int, thumb: np.ndarray) -> dict | None:
        for e in self._cache:
            # 同一行字换一张图去检测（整屏 / 局部），框会差几个像素；位置放宽一点，真正把关的是下面的像素比较
            if abs(e["x"] - x) <= 8 and abs(e["y"] - y) <= 8 and abs(e["w"] - w) <= 14 and abs(e["h"] - h) <= 8:
                if float(np.abs(e["thumb"] - thumb).mean()) < _SAME:
                    return e
        return None
