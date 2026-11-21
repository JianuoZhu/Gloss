"""在线机翻引擎：用本地模拟服务器检查我们发出的请求（地址、头、参数、签名）和对响应的解析。

这些测试不联网、不需要密钥。它们证明的是"请求是按协议拼的"，不能证明真实服务一定接受——
各引擎的协议依据见 gloss/translate/registry.py 里的 verified 字段。
"""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from gloss.config import DEFAULT_SETTINGS
from gloss.translate import create_translator
from gloss.translate import cloud
from gloss.translate.base import Term, TranslateContext, TranslateError
from gloss.translate.registry import BY_ID, ENGINES, default_settings

CTX = TranslateContext(source_lang="ja", target_lang="zh-CN", glossary=[Term("アリシア", "艾莉西亚")])
AUTO = TranslateContext(source_lang="auto", target_lang="zh-CN")
TEXTS = ["アリシア、準備はいい？", "New Game"]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        url = urlparse(self.path)
        ctype = self.headers.get("Content-Type", "")
        body = json.loads(raw) if "json" in ctype else {k: v[0] for k, v in parse_qs(raw.decode("utf-8")).items()}
        req = {"path": url.path, "query": {k: v[0] for k, v in parse_qs(url.query).items()}, "headers": dict(self.headers),
               "body": body, "raw": raw.decode("utf-8")}
        self.server.seen.append(req)
        status, reply = self.server.reply(req)
        data = json.dumps(reply, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.seen, srv.reply = [], lambda req: (200, {})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.url = f"http://127.0.0.1:{srv.server_port}"
    yield srv
    srv.shutdown()


def test_deepl(server):
    server.reply = lambda req: (200, {"translations": [{"text": f"译{i}"} for i, _ in enumerate(req["body"]["text"])]})
    out = cloud.DeepLTranslator("key-123:fx", base_url=server.url).translate(TEXTS, CTX)
    assert out == ["译0", "译1"]
    req = server.seen[0]
    assert req["path"] == "/v2/translate" and req["headers"]["Authorization"] == "DeepL-Auth-Key key-123:fx"
    assert req["body"]["target_lang"] == "ZH-HANS" and req["body"]["source_lang"] == "JA"
    assert req["body"]["text"] == ["艾莉西亚、準備はいい？", "New Game"]  # 术语在翻译前替换；一次请求翻一整批
    assert len(server.seen) == 1
    assert "source_lang" not in cloud.DeepLTranslator("k", base_url=server.url).translate(["hi there"], AUTO) or True
    assert "source_lang" not in server.seen[-1]["body"]  # 自动检测时不传原文语言


def test_deepl_picks_host_by_key_and_reports_bad_key(server):
    assert cloud.DeepLTranslator("abc:fx")._base == "https://api-free.deepl.com"
    assert cloud.DeepLTranslator("abc")._base == "https://api.deepl.com"
    server.reply = lambda req: (403, {"message": "forbidden"})
    with pytest.raises(TranslateError, match="密钥无效"):
        cloud.DeepLTranslator("bad", base_url=server.url).translate(TEXTS, CTX)


def test_deeplx(server):
    server.reply = lambda req: (200, {"code": 200, "data": "译:" + req["body"]["text"]})
    out = cloud.DeepLXTranslator(server.url, token="tok").translate(TEXTS, CTX)
    assert out == ["译:艾莉西亚、準備はいい？", "译:New Game"]
    req = server.seen[0]
    assert req["path"] == "/translate" and req["headers"]["Authorization"] == "Bearer tok"
    assert req["body"]["target_lang"] == "ZH" and req["body"]["source_lang"] == "JA"
    server.reply = lambda req: (429, {"code": 429, "message": "too many"})
    with pytest.raises(TranslateError, match="429"):
        cloud.DeepLXTranslator(server.url).translate(["hello there"], AUTO)


def test_azure(server):
    server.reply = lambda req: (200, [{"translations": [{"text": "译:" + row["Text"]}]} for row in req["body"]])
    out = cloud.AzureTranslator("k", "eastasia", base_url=server.url).translate(TEXTS, CTX)
    assert out == ["译:艾莉西亚、準備はいい？", "译:New Game"]
    req = server.seen[0]
    assert req["path"] == "/translate" and req["query"] == {"api-version": "3.0", "to": "zh-Hans", "from": "ja"}
    assert req["headers"]["Ocp-Apim-Subscription-Key"] == "k" and req["headers"]["Ocp-Apim-Subscription-Region"] == "eastasia"


def test_baidu_signs_and_batches(server):
    server.reply = lambda req: (200, {"trans_result": [{"src": s, "dst": "译:" + s} for s in req["body"]["q"].split("\n")]})
    out = cloud.BaiduTranslator("appid1", "secret1", base_url=server.url).translate(TEXTS, CTX)
    assert out == ["译:艾莉西亚、準備はいい？", "译:New Game"] and len(server.seen) == 1
    b = server.seen[0]["body"]
    assert server.seen[0]["path"] == "/api/trans/vip/translate"
    assert (b["from"], b["to"], b["appid"]) == ("jp", "zh", "appid1")
    assert b["sign"] == hashlib.md5(("appid1" + b["q"] + b["salt"] + "secret1").encode("utf-8")).hexdigest()
    server.reply = lambda req: (200, {"error_code": "54003", "error_msg": "Invalid Access Limit"})
    with pytest.raises(TranslateError, match="54003"):
        cloud.BaiduTranslator("a", "s", base_url=server.url).translate(TEXTS, CTX)


def test_youdao_signature_rule():
    short = cloud.youdao_sign("KEY", "hello", "salt", "1700000000", "SECRET")
    assert short == hashlib.sha256(b"KEYhellosalt1700000000SECRET").hexdigest()
    q = "abcdefghijklmnopqrstuvwxyz"  # 26 个字符：取前 10 个 + 长度 + 后 10 个
    assert cloud.youdao_sign("KEY", q, "salt", "1700000000", "SECRET") == hashlib.sha256(
        b"KEYabcdefghij26qrstuvwxyzsalt1700000000SECRET").hexdigest()


def test_youdao(server):
    server.reply = lambda req: (200, {"errorCode": "0", "translation": ["译:" + req["body"]["q"]]})
    out = cloud.YoudaoTranslator("KEY", "SECRET", base_url=server.url).translate(TEXTS, CTX)
    assert out == ["译:艾莉西亚、準備はいい？", "译:New Game"]
    for req in server.seen:
        b = req["body"]
        assert req["path"] == "/api" and (b["from"], b["to"], b["signType"], b["appKey"]) == ("ja", "zh-CHS", "v3", "KEY")
        assert b["sign"] == cloud.youdao_sign("KEY", b["q"], b["salt"], b["curtime"], "SECRET")
    assert len({r["body"]["salt"] for r in server.seen}) == 2  # 每次请求的 salt 不能重复
    server.reply = lambda req: (200, {"errorCode": "202"})
    with pytest.raises(TranslateError, match="202"):
        cloud.YoudaoTranslator("K", "S", base_url=server.url).translate(["hello there"], AUTO)


def test_tc3_canonical_hash_matches_tencent_doc_example():
    # 腾讯云签名文档里的示例（云服务器 DescribeInstances）给出了这两步的结果，和密钥无关，可以直接对
    payload = json.dumps({"Limit": 1, "Filters": [{"Values": ["未命名"], "Name": "instance-name"}]})
    assert hashlib.sha256(payload.encode()).hexdigest() == "35e9c5b0e3ae67532d3c9f17ead6c90222632e5b1ff7f6e89887f1398934f064"
    assert cloud.tc3_canonical_hash("cvm.tencentcloudapi.com", "DescribeInstances", payload) == \
        "7019a55be8395899b900fb5564e4200d984910f34794a27cb3fb7d10ff6a1e84"


def test_tencent(server):
    server.reply = lambda req: (200, {"Response": {"TargetTextList": ["译:" + s for s in req["body"]["SourceTextList"]], "RequestId": "r"}})
    out = cloud.TencentTranslator("AKID1", "KEY1", "ap-shanghai", base_url=server.url).translate(TEXTS, CTX)
    assert out == ["译:艾莉西亚、準備はいい？", "译:New Game"]
    req = server.seen[0]
    h = req["headers"]
    assert req["body"] == {"Source": "ja", "Target": "zh", "ProjectId": 0, "SourceTextList": ["艾莉西亚、準備はいい？", "New Game"]}
    assert (h["X-TC-Action"], h["X-TC-Version"], h["X-TC-Region"]) == ("TextTranslateBatch", "2018-03-21", "ap-shanghai")
    assert h["Content-Type"] == "application/json; charset=utf-8"
    expected = cloud.tc3_authorization("AKID1", "KEY1", "tmt", "tmt.tencentcloudapi.com", "TextTranslateBatch", req["raw"], int(h["X-TC-Timestamp"]))
    assert h["Authorization"] == expected  # 签的正是实际发出去的那串字节
    assert expected.startswith("TC3-HMAC-SHA256 Credential=AKID1/") and "SignedHeaders=content-type;host;x-tc-action" in expected
    server.reply = lambda req: (200, {"Response": {"Error": {"Code": "AuthFailure.SignatureFailure", "Message": "bad"}}})
    with pytest.raises(TranslateError, match="SignatureFailure"):
        cloud.TencentTranslator("a", "b", base_url=server.url).translate(TEXTS, CTX)


def test_caiyun(server):
    server.reply = lambda req: (200, {"target": ["译:" + s for s in req["body"]["source"]]})
    out = cloud.CaiyunTranslator("tok", base_url=server.url).translate(TEXTS, CTX)
    assert out == ["译:艾莉西亚、準備はいい？", "译:New Game"]
    req = server.seen[0]
    assert req["path"] == "/v1/translator" and req["headers"]["X-Authorization"] == "token tok"
    assert req["body"]["trans_type"] == "ja2zh" and req["body"]["detect"] is False
    cloud.CaiyunTranslator("tok", base_url=server.url).translate(["hello there"], AUTO)
    assert server.seen[-1]["body"]["trans_type"] == "auto2zh" and server.seen[-1]["body"]["detect"] is True
    server.reply = lambda req: (200, {"message": "Invalid token"})
    with pytest.raises(TranslateError, match="没有返回译文"):
        cloud.CaiyunTranslator("x", base_url=server.url).translate(TEXTS, CTX)


def test_wrong_number_of_results_is_an_error(server):
    server.reply = lambda req: (200, {"target": ["只有一条"]})
    with pytest.raises(TranslateError, match="1 条"):
        cloud.CaiyunTranslator("tok", base_url=server.url).translate(TEXTS, CTX)


# ---- 登记表 ----
def test_every_engine_has_settings_and_can_be_created_or_explains_what_is_missing():
    defaults = default_settings()
    assert DEFAULT_SETTINGS["translator"]["provider"] == "google"
    for engine in ENGINES:
        if engine.fields:
            assert set(defaults[engine.id]) >= {f.key for f in engine.fields}
        if engine.kind in ("hymt", "nllb", "claude", "google"):
            continue  # 本地模型要有模型文件；Claude 和 Google 不填也能创建
        cfg = {"provider": engine.id, **{k: dict(v) for k, v in defaults.items()}}
        ready = (engine.kind == "openai" and defaults[engine.id].get("base_url") and defaults[engine.id].get("model")) \
            or engine.kind == "deeplx"  # 默认值就够用的引擎（DeepSeek 自带模型名，DeepLX 自带本机地址）
        if ready:
            create_translator(cfg)
            continue
        with pytest.raises(TranslateError):  # 没填密钥 / 模型名时，报的是用户看得懂的话
            create_translator(cfg)


def test_llm_vendors_share_the_openai_backend(server):
    cfg = {"provider": "deepseek", "deepseek": {"api_key": "sk-x", "model": "deepseek-chat", "base_url": server.url + "/v1"}}
    tr = create_translator(cfg)
    assert type(tr).__name__ == "OpenAICompatTranslator" and tr.temperature is None
    assert BY_ID["deepseek"].kind == BY_ID["qwen"].kind == BY_ID["ollama"].kind == "openai"
    assert len({e.id for e in ENGINES}) == len(ENGINES) >= 20
