"""OpenAI 兼容的 chat/completions 接口。

本地大模型（Ollama、LM Studio、llama.cpp server）和大多数厂商的大模型 API 都讲这套协议，
所以登记表里那一串大模型引擎用的都是这一个类，只是地址不同。
"""

from __future__ import annotations

import json

import httpx

from .base import (
    NumberedStreamParser,
    PartialCallback,
    TranslateContext,
    TranslateError,
    build_system_prompt,
    build_user_prompt,
)

class OpenAICompatTranslator:
    name = "openai_compat"

    def __init__(self, base_url: str, model: str, api_key: str = "", temperature: float | None = 0.3) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(headers=headers, timeout=httpx.Timeout(30.0, connect=4.0))

    def translate(self, items: list[str], ctx: TranslateContext, on_partial: PartialCallback | None = None) -> list[str]:
        if not items:
            return []
        parser = NumberedStreamParser(len(items), on_partial)
        body = {
            "model": self.model,
            "stream": True,
            "messages": [
                {"role": "system", "content": build_system_prompt(ctx)},
                {"role": "user", "content": build_user_prompt(items, ctx)},
            ],
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        try:
            with self._client.stream("POST", f"{self.base_url}/chat/completions", json=body) as resp:
                if resp.status_code >= 400:
                    detail = resp.read().decode("utf-8", "replace")[:300]
                    raise TranslateError(f"翻译接口返回 {resp.status_code}：{detail}")
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta", {})
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta.get("content"):
                        parser.feed(delta["content"])
        except httpx.ConnectError as e:
            raise TranslateError(f"连接不上 {self.base_url}（本地模型服务没启动？）") from e
        except httpx.TimeoutException as e:
            raise TranslateError("翻译接口超时。") from e
        except httpx.HTTPError as e:
            raise TranslateError(f"翻译接口出错：{e}") from e
        return parser.finish()
