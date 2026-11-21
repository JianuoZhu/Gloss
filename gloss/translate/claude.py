"""Claude 后端（官方 anthropic SDK，流式）。"""

from __future__ import annotations

import anthropic

from .base import (
    NumberedStreamParser,
    PartialCallback,
    TranslateContext,
    TranslateError,
    build_system_prompt,
    build_user_prompt,
)

DEFAULT_MODEL = "claude-opus-5-5"

# 这些模型被安全分类器拒绝时，可以让服务端自动换模型重跑同一请求
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeTranslator:
    name = "claude"

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str = "", effort: str = "low", base_url: str = "") -> None:
        self.model = model or DEFAULT_MODEL
        self.effort = effort or "low"
        # 不填的项让 SDK 自己从环境里找（ANTHROPIC_API_KEY、ANTHROPIC_BASE_URL 或 `ant auth login` 的配置）
        options = {"timeout": 30.0}
        if api_key:
            options["api_key"] = api_key
        if base_url:
            options["base_url"] = base_url
        self._client = anthropic.Anthropic(**options)

    def translate(self, items: list[str], ctx: TranslateContext, on_partial: PartialCallback | None = None) -> list[str]:
        if not items:
            return []
        parser = NumberedStreamParser(len(items), on_partial)
        params = dict(
            model=self.model,
            max_tokens=4096,
            system=build_system_prompt(ctx),
            messages=[{"role": "user", "content": build_user_prompt(items, ctx)}],
            # 实时翻译要的是低延迟。当前的 Opus 不能关闭思考，只能把 effort 调低
            output_config={"effort": self.effort},
        )
        if self.model in _FALLBACK_MODELS:
            open_stream = lambda: self._client.beta.messages.stream(  # noqa: E731
                betas=[_FALLBACK_BETA], fallbacks="default", **params
            )
        else:
            open_stream = lambda: self._client.messages.stream(**params)  # noqa: E731
        try:
            with open_stream() as stream:
                for text in stream.text_stream:
                    parser.feed(text)
                final = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise TranslateError("Claude API 密钥无效或未设置。") from e
        except anthropic.NotFoundError as e:
            raise TranslateError(f"找不到模型「{self.model}」。") from e
        except anthropic.RateLimitError as e:
            raise TranslateError("Claude API 触发限流，稍后会自动重试。") from e
        except anthropic.APIStatusError as e:
            raise TranslateError(f"Claude API 错误（{e.status_code}）：{e.message}") from e
        except anthropic.APIConnectionError as e:
            raise TranslateError("连接不上 Claude API，请检查网络。") from e
        if final.stop_reason == "refusal":
            raise TranslateError("Claude 拒绝了这段文本的翻译。")
        return parser.finish()
