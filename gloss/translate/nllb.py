"""NLLB-200（Meta 的传统机翻模型），用 CTranslate2 在本进程里跑。

优点是轻：int8 量化后纯 CPU 就够快，不占显存。缺点是没有上下文、不懂术语表（只能翻译前替换），
日译中质量一般。必须明确告诉它原文是什么语言，所以"自动检测"时按字符种类猜。
"""

from __future__ import annotations

import re

from ..local_mt import NLLB_DIR, installed
from .base import PartialCallback, TranslateContext, TranslateError, relevant_terms, substitute_terms

_CODES = {
    "ja": "jpn_Jpan", "en": "eng_Latn", "ko": "kor_Hang", "zh": "zho_Hans", "zh-CN": "zho_Hans", "zh-TW": "zho_Hant",
    "ru": "rus_Cyrl", "fr": "fra_Latn", "de": "deu_Latn", "es": "spa_Latn",
}
_KANA = re.compile(r"[぀-ヿｦ-ﾟ]")
_HANGUL = re.compile(r"[가-힯]")
_HAN = re.compile(r"[㐀-䶿一-鿿]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def guess_language(text: str) -> str:
    if _KANA.search(text):
        return "ja"
    if _HANGUL.search(text):
        return "ko"
    if _HAN.search(text):
        return "zh"
    if _CYRILLIC.search(text):
        return "ru"
    return "en"


class NllbTranslator:
    name = "nllb"

    def __init__(self, threads: int = 4) -> None:
        if not installed("nllb"):
            raise TranslateError("还没有下载 NLLB 模型：到「引擎」页点「下载」。")
        import ctranslate2
        import sentencepiece

        self._model = ctranslate2.Translator(
            str(NLLB_DIR), device="cpu", compute_type="int8", inter_threads=1, intra_threads=threads
        )
        self._sp = sentencepiece.SentencePieceProcessor(model_file=str(NLLB_DIR / "sentencepiece.bpe.model"))

    def translate(self, items: list[str], ctx: TranslateContext, on_partial: PartialCallback | None = None) -> list[str]:
        if not items:
            return []
        target = _CODES.get(ctx.target_lang, "zho_Hans")
        sources = []
        for text in items:
            text = substitute_terms(text, relevant_terms(ctx.glossary, [text]))
            lang = ctx.source_lang if ctx.source_lang != "auto" else guess_language(text)
            sources.append([_CODES.get(lang, "eng_Latn"), *self._sp.encode(text, out_type=str), "</s>"])
        results = self._model.translate_batch(
            sources,
            target_prefix=[[target]] * len(sources),
            beam_size=2,
            max_decoding_length=256,
            no_repeat_ngram_size=4,  # 小模型遇到没见过的词容易原地打转
        )
        out = [self._sp.decode(r.hypotheses[0][1:]) for r in results]
        if on_partial:
            for i, text in enumerate(out):
                on_partial(i, text, True)
        return out
