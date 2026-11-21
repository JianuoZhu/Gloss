"""用本地模拟服务器验证两个 LLM 后端：请求长什么样、流式输出能不能边到边解析。

不联网、不需要密钥。它验证的是"我们发出的请求和对流的解析"，不是真实服务的行为。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from gloss.translate.base import Term, TranslateContext, TranslateError
from gloss.translate.claude import ClaudeTranslator
from gloss.translate.openai_compat import OpenAICompatTranslator

CHUNKS = ["1| 新", "游戏\n2", "| 继续\n"]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _sse(self, lines: list[str]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for line in lines:
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if self.server.fail:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"type":"error","error":{"type":"authentication_error","message":"bad key"}}')
            return
        if self.path.startswith("/v1/chat/completions"):
            events = [f'data: {json.dumps({"choices": [{"delta": {"content": c}}]})}\n\n' for c in CHUNKS]
            self._sse(events + ["data: [DONE]\n\n"])
        elif self.path.startswith("/v1/messages"):
            def ev(name, data):
                return f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n"

            message = {
                "id": "msg_test", "type": "message", "role": "assistant", "model": body["model"], "content": [],
                "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0},
            }
            events = [ev("message_start", {"message": message}),
                      ev("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}})]
            events += [ev("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": c}}) for c in CHUNKS]
            events += [ev("content_block_stop", {"index": 0}),
                       ev("message_delta", {"delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 8}}),
                       ev("message_stop", {})]
            self._sse(events)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.seen, srv.fail = [], False
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


CTX = TranslateContext(source_lang="en", target_lang="zh-CN", glossary=[Term("Continue", "继续")], game_hint="奇幻 RPG")


def test_openai_compat_streams_and_parses(server):
    partials = []
    tr = OpenAICompatTranslator(f"http://127.0.0.1:{server.server_port}/v1", "local-model", api_key="k")
    out = tr.translate(["New Game", "Continue"], CTX, lambda i, t, f: partials.append((i, t, f)))
    assert out == ["新游戏", "继续"]
    assert (0, "新", False) in partials  # 第一条还没写完时就已经报出来了
    req = server.seen[0]
    assert req["body"]["model"] == "local-model" and req["body"]["stream"] is True
    assert req["headers"]["Authorization"] == "Bearer k"
    system, user = (m["content"] for m in req["body"]["messages"])
    assert "Simplified Chinese" in system and "奇幻 RPG" in system
    assert "Continue => 继续" in user and "1| New Game" in user


def test_openai_compat_reports_connection_failure():
    tr = OpenAICompatTranslator("http://127.0.0.1:9/v1", "m")
    with pytest.raises(TranslateError):
        tr.translate(["hi there"], CTX)


def test_claude_request_shape_and_stream(server):
    partials = []
    tr = ClaudeTranslator(api_key="test-key", base_url=f"http://127.0.0.1:{server.server_port}")
    out = tr.translate(["New Game", "Continue"], CTX, lambda i, t, f: partials.append((i, t, f)))
    assert out == ["新游戏", "继续"]
    assert (0, "新", False) in partials
    req = server.seen[0]
    body = req["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["stream"] is True
    assert body["output_config"] == {"effort": "low"}
    assert body["fallbacks"] == "default"
    assert "thinking" not in body  # 这个模型不能关思考，也不该显式配置
    assert "server-side-fallback-2026-07-01" in req["headers"].get("anthropic-beta", "")
    assert "Simplified Chinese" in body["system"]
    assert "1| New Game" in body["messages"][0]["content"]


def test_claude_without_fallback_for_other_models(server):
    tr = ClaudeTranslator(model="claude-haiku-5-5", api_key="test-key", base_url=f"http://127.0.0.1:{server.server_port}")
    assert tr.translate(["New Game", "Continue"], CTX) == ["新游戏", "继续"]
    req = server.seen[0]
    assert "fallbacks" not in req["body"]
    assert "server-side-fallback" not in req["headers"].get("anthropic-beta", "")


def test_claude_auth_error_is_readable(server):
    server.fail = True
    tr = ClaudeTranslator(api_key="bad", base_url=f"http://127.0.0.1:{server.server_port}")
    with pytest.raises(TranslateError, match="密钥"):
        tr.translate(["New Game"], CTX)
