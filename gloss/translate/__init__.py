"""翻译后端。有哪些引擎、各自的设置项见 registry.py。"""

from __future__ import annotations

from .base import Term, TranslateContext, TranslateError, Translator
from .registry import BY_ID, ENGINES


def create_translator(cfg: dict) -> Translator:
    """cfg 是设置里的 translator 段：provider 是引擎 id，同名的子项是这个引擎的设置。"""
    engine = BY_ID.get(cfg.get("provider", "google"), BY_ID["google"])
    c = cfg.get(engine.id, {})
    kind = engine.kind

    if kind == "hymt":
        from .hymt import HyMTTranslator

        return HyMTTranslator(device=c.get("device", "auto"), threads=int(c.get("threads", 0)))
    if kind == "nllb":
        from .nllb import NllbTranslator

        return NllbTranslator()
    if kind == "claude":
        from .claude import ClaudeTranslator

        return ClaudeTranslator(model=c.get("model", ""), api_key=c.get("api_key", ""), effort=c.get("effort", "low"),
                                base_url=c.get("base_url", ""))
    if kind == "openai":
        from .openai_compat import OpenAICompatTranslator

        if not c.get("base_url") or not c.get("model"):
            raise TranslateError(f"{engine.label}需要填写接口地址和模型名。")
        # 不传 temperature：有些厂商的模型只接受默认值，传了会直接报错
        return OpenAICompatTranslator(c["base_url"], c["model"], c.get("api_key", ""), temperature=None)
    if kind == "google":
        from .google import GoogleTranslator

        return GoogleTranslator()

    from . import cloud

    if kind == "deepl":
        return cloud.DeepLTranslator(c.get("api_key", ""))
    if kind == "deeplx":
        return cloud.DeepLXTranslator(c.get("url", ""), c.get("token", ""))
    if kind == "azure":
        return cloud.AzureTranslator(c.get("api_key", ""), c.get("region", ""))
    if kind == "baidu":
        return cloud.BaiduTranslator(c.get("app_id", ""), c.get("secret", ""))
    if kind == "youdao":
        return cloud.YoudaoTranslator(c.get("app_key", ""), c.get("app_secret", ""))
    if kind == "tencent":
        return cloud.TencentTranslator(c.get("secret_id", ""), c.get("secret_key", ""), c.get("region", ""))
    if kind == "caiyun":
        return cloud.CaiyunTranslator(c.get("token", ""))
    raise TranslateError(f"不认识的翻译引擎：{engine.id}")


def translator_signature(cfg: dict) -> str:
    """区分"换了后端或模型"的标识，用作缓存键的一部分。"""
    provider = cfg.get("provider", "google")
    sub = cfg.get(provider, {})
    return f"{provider}:{sub.get('model', '')}:{sub.get('base_url', '')}"


__all__ = [
    "ENGINES", "Term", "TranslateContext", "TranslateError", "Translator",
    "create_translator", "translator_signature",
]
