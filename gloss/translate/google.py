"""免密钥的 Google 机翻（非官方接口）。开箱即用，但没有上下文，术语靠翻译前替换。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

from .base import PartialCallback, TranslateContext, TranslateError, relevant_terms, substitute_terms

_URL = "https://translate.googleapis.com/translate_a/single"


class GoogleTranslator:
    name = "google"

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=httpx.Timeout(8.0, connect=4.0))
        self._pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="gloss-gt")

    def _one(self, text: str, ctx: TranslateContext) -> str:
        text = substitute_terms(text, relevant_terms(ctx.glossary, [text]))
        resp = self._client.post(
            _URL,
            params={"client": "gtx", "sl": "auto" if ctx.source_lang == "auto" else ctx.source_lang, "tl": ctx.target_lang, "dt": "t"},
            data={"q": text},
        )
        resp.raise_for_status()
        return "".join(seg[0] for seg in resp.json()[0] if seg and seg[0])

    def translate(self, items: list[str], ctx: TranslateContext, on_partial: PartialCallback | None = None) -> list[str]:
        def work(i: int) -> str:
            out = self._one(items[i], ctx)
            if on_partial:
                on_partial(i, out, True)
            return out

        try:
            return list(self._pool.map(work, range(len(items))))
        except httpx.HTTPError as e:
            raise TranslateError(f"Google 机翻请求失败：{e}") from e
