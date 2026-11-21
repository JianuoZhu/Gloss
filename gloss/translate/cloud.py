"""在线机翻接口：DeepL、DeepLX、Azure、百度、有道、腾讯云、彩云。

它们都是"一句进一句出"的传统机翻：没有上下文，术语表靠翻译前替换。能一次请求翻一整批的就合成一次，
不能的并发请求。各家的协议依据见 registry.py 里每个引擎的 verified 字段。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx

from .base import PartialCallback, TranslateContext, TranslateError, relevant_terms, substitute_terms


class CloudTranslator:
    """公共部分：术语替换、网络错误转成可读的消息、结果回调。子类只写 _translate。"""

    name = "cloud"
    label = "在线翻译"

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=httpx.Timeout(10.0, connect=4.0))

    def _translate(self, texts: list[str], ctx: TranslateContext) -> list[str]:
        raise NotImplementedError

    def translate(self, items: list[str], ctx: TranslateContext, on_partial: PartialCallback | None = None) -> list[str]:
        if not items:
            return []
        texts = [substitute_terms(" ".join(t.split()), relevant_terms(ctx.glossary, [t])) for t in items]
        try:
            out = self._translate(texts, ctx)
        except httpx.HTTPStatusError as e:
            raise TranslateError(f"{self.label}返回 {e.response.status_code}：{e.response.text[:200]}") from e
        except httpx.HTTPError as e:
            raise TranslateError(f"{self.label}请求失败：{e}") from e
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise TranslateError(f"{self.label}返回了看不懂的内容：{e}") from e
        if len(out) != len(items):
            raise TranslateError(f"{self.label}返回了 {len(out)} 条译文，应为 {len(items)} 条。")
        if on_partial:
            for i, text in enumerate(out):
                on_partial(i, text, True)
        return out

    def _each(self, texts: list[str], one) -> list[str]:
        """接口一次只能翻一句时，并发着发。"""
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(one, texts))

    def close(self) -> None:
        self._client.close()


def _need(value: str, what: str) -> str:
    if not value:
        raise TranslateError(f"还没有填写{what}。")
    return value


# ---------------------------------------------------------------- DeepL
class DeepLTranslator(CloudTranslator):
    name, label = "deepl", "DeepL"
    _TARGET = {"zh-CN": "ZH-HANS", "zh-TW": "ZH-HANT", "en": "EN-US"}

    def __init__(self, api_key: str, base_url: str = "") -> None:
        super().__init__()
        self._key = _need(api_key, " DeepL 的 API 密钥")
        # 免费版密钥以 :fx 结尾，用另一个域名
        self._base = base_url.rstrip("/") or ("https://api-free.deepl.com" if api_key.endswith(":fx") else "https://api.deepl.com")

    def _translate(self, texts, ctx):
        body = {"text": texts, "target_lang": self._TARGET.get(ctx.target_lang, ctx.target_lang.upper())}
        if ctx.source_lang != "auto":
            body["source_lang"] = ctx.source_lang.split("-")[0].upper()
        resp = self._client.post(f"{self._base}/v2/translate", json=body, headers={"Authorization": f"DeepL-Auth-Key {self._key}"})
        if resp.status_code == 403:
            raise TranslateError("DeepL 密钥无效。")
        if resp.status_code == 456:
            raise TranslateError("DeepL 本月的字符额度用完了。")
        resp.raise_for_status()
        return [t["text"] for t in resp.json()["translations"]]


# ---------------------------------------------------------------- DeepLX / DLX
class DeepLXTranslator(CloudTranslator):
    name, label = "deeplx", "DeepLX"
    _TARGET = {"zh-CN": "ZH", "zh-TW": "ZH-HANT", "en": "EN-US"}

    def __init__(self, url: str, token: str = "") -> None:
        super().__init__()
        self._url = _need(url, " DeepLX 的服务地址").rstrip("/")
        if not self._url.endswith("/translate"):
            self._url += "/translate"
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _translate(self, texts, ctx):
        def one(text: str) -> str:  # 老版本一次只收一句，所以逐句发，新老版本都能用
            body = {"text": text, "target_lang": self._TARGET.get(ctx.target_lang, ctx.target_lang.upper()),
                    "source_lang": "auto" if ctx.source_lang == "auto" else ctx.source_lang.split("-")[0].upper()}
            resp = self._client.post(self._url, json=body, headers=self._headers)
            data = resp.json() if resp.content else {}
            if resp.status_code != 200 or data.get("code", 200) != 200:
                raise TranslateError(f"DeepLX 返回 {data.get('code', resp.status_code)}：{data.get('message', '')}")
            return data["data"]

        return self._each(texts, one)


# ---------------------------------------------------------------- Azure
class AzureTranslator(CloudTranslator):
    name, label = "azure", "Azure 翻译"
    _LANG = {"zh-CN": "zh-Hans", "zh": "zh-Hans", "zh-TW": "zh-Hant"}

    def __init__(self, api_key: str, region: str = "", base_url: str = "") -> None:
        super().__init__()
        self._headers = {"Ocp-Apim-Subscription-Key": _need(api_key, " Azure 翻译的密钥")}
        if region:
            self._headers["Ocp-Apim-Subscription-Region"] = region
        self._base = base_url.rstrip("/") or "https://api.cognitive.microsofttranslator.com"

    def _translate(self, texts, ctx):
        params = {"api-version": "3.0", "to": self._LANG.get(ctx.target_lang, ctx.target_lang)}
        if ctx.source_lang != "auto":
            params["from"] = self._LANG.get(ctx.source_lang, ctx.source_lang)
        resp = self._client.post(f"{self._base}/translate", params=params, json=[{"Text": t} for t in texts], headers=self._headers)
        if resp.status_code == 401:
            raise TranslateError("Azure 翻译的密钥或区域不对。")
        resp.raise_for_status()
        return [row["translations"][0]["text"] for row in resp.json()]


# ---------------------------------------------------------------- 百度
class BaiduTranslator(CloudTranslator):
    name, label = "baidu", "百度翻译"
    _LANG = {"zh-CN": "zh", "zh-TW": "cht", "ja": "jp", "ko": "kor", "fr": "fra", "es": "spa"}

    def __init__(self, app_id: str, secret: str, base_url: str = "") -> None:
        super().__init__()
        self._app_id, self._secret = _need(app_id, "百度翻译的 APP ID"), _need(secret, "百度翻译的密钥")
        self._url = (base_url.rstrip("/") or "https://fanyi-api.baidu.com") + "/api/trans/vip/translate"

    def _translate(self, texts, ctx):
        q = "\n".join(texts)  # 一行一条，一次请求翻完（标准版限制每秒 1 次请求）
        salt = uuid.uuid4().hex
        sign = hashlib.md5((self._app_id + q + salt + self._secret).encode("utf-8")).hexdigest()
        resp = self._client.post(self._url, data={
            "q": q, "from": self._LANG.get(ctx.source_lang, ctx.source_lang), "to": self._LANG.get(ctx.target_lang, ctx.target_lang),
            "appid": self._app_id, "salt": salt, "sign": sign,
        })
        resp.raise_for_status()
        data = resp.json()
        if "error_code" in data:
            raise TranslateError(f"百度翻译出错 {data['error_code']}：{data.get('error_msg', '')}")
        return [row["dst"] for row in data["trans_result"]]


# ---------------------------------------------------------------- 有道
def youdao_sign(app_key: str, q: str, salt: str, curtime: str, app_secret: str) -> str:
    """有道 v3 签名：sha256(应用ID + input + salt + curtime + 应用密钥)，q 超过 20 个字符时 input 取首尾各 10 个加长度。"""
    shown = q if len(q) <= 20 else q[:10] + str(len(q)) + q[-10:]
    return hashlib.sha256((app_key + shown + salt + curtime + app_secret).encode("utf-8")).hexdigest()


class YoudaoTranslator(CloudTranslator):
    name, label = "youdao", "有道智云"
    _LANG = {"zh-CN": "zh-CHS", "zh": "zh-CHS", "zh-TW": "zh-CHT"}

    def __init__(self, app_key: str, app_secret: str, base_url: str = "") -> None:
        super().__init__()
        self._key, self._secret = _need(app_key, "有道智云的应用 ID"), _need(app_secret, "有道智云的应用密钥")
        self._url = (base_url.rstrip("/") or "https://openapi.youdao.com") + "/api"

    def _translate(self, texts, ctx):
        def one(text: str) -> str:
            salt, curtime = uuid.uuid4().hex, str(int(time.time()))
            resp = self._client.post(self._url, data={
                "q": text, "from": self._LANG.get(ctx.source_lang, ctx.source_lang), "to": self._LANG.get(ctx.target_lang, ctx.target_lang),
                "appKey": self._key, "salt": salt, "sign": youdao_sign(self._key, text, salt, curtime, self._secret),
                "signType": "v3", "curtime": curtime,
            })
            resp.raise_for_status()
            data = resp.json()
            if data.get("errorCode") != "0":
                raise TranslateError(f"有道智云出错，错误码 {data.get('errorCode')}。")
            return "".join(data["translation"])

        return self._each(texts, one)


# ---------------------------------------------------------------- 腾讯云
def tc3_canonical_hash(host: str, action: str, payload: str) -> str:
    """TC3 签名第一步：规范请求串的 SHA-256。参与签名的头固定为 content-type、host、x-tc-action。"""
    canonical = "\n".join([
        "POST", "/", "",
        f"content-type:application/json; charset=utf-8\nhost:{host}\nx-tc-action:{action.lower()}\n",
        "content-type;host;x-tc-action",
        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def tc3_authorization(secret_id: str, secret_key: str, service: str, host: str, action: str, payload: str, timestamp: int) -> str:
    """腾讯云 API 3.0 的 TC3-HMAC-SHA256 签名，返回 Authorization 头的值。"""
    date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
    scope = f"{date}/{service}/tc3_request"
    to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n{tc3_canonical_hash(host, action, payload)}"

    def mac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    signing = mac(mac(mac(("TC3" + secret_key).encode("utf-8"), date), service), "tc3_request")
    signature = hmac.new(signing, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, SignedHeaders=content-type;host;x-tc-action, Signature={signature}"


class TencentTranslator(CloudTranslator):
    name, label = "tencent", "腾讯云翻译"
    _HOST, _ACTION = "tmt.tencentcloudapi.com", "TextTranslateBatch"
    _LANG = {"zh-CN": "zh"}

    def __init__(self, secret_id: str, secret_key: str, region: str = "ap-guangzhou", base_url: str = "") -> None:
        super().__init__()
        self._id, self._key = _need(secret_id, "腾讯云的 SecretId"), _need(secret_key, "腾讯云的 SecretKey")
        self._region = region or "ap-guangzhou"
        self._url = base_url.rstrip("/") or f"https://{self._HOST}"

    def _translate(self, texts, ctx):
        payload = json.dumps({
            "Source": self._LANG.get(ctx.source_lang, ctx.source_lang), "Target": self._LANG.get(ctx.target_lang, ctx.target_lang),
            "ProjectId": 0, "SourceTextList": texts,
        })
        now = int(time.time())
        resp = self._client.post(self._url, content=payload.encode("utf-8"), headers={
            "Authorization": tc3_authorization(self._id, self._key, "tmt", self._HOST, self._ACTION, payload, now),
            "Content-Type": "application/json; charset=utf-8", "Host": self._HOST,
            "X-TC-Action": self._ACTION, "X-TC-Version": "2018-03-21", "X-TC-Timestamp": str(now), "X-TC-Region": self._region,
        })
        resp.raise_for_status()
        data = resp.json()["Response"]
        if "Error" in data:
            raise TranslateError(f"腾讯云翻译出错 {data['Error'].get('Code')}：{data['Error'].get('Message', '')}")
        return list(data["TargetTextList"])


# ---------------------------------------------------------------- 彩云
class CaiyunTranslator(CloudTranslator):
    name, label = "caiyun", "彩云小译"
    _LANG = {"zh-CN": "zh", "zh-TW": "zh-Hant"}

    def __init__(self, token: str, base_url: str = "") -> None:
        super().__init__()
        self._token = _need(token, "彩云小译的令牌")
        self._url = (base_url.rstrip("/") or "https://api.interpreter.caiyunai.com") + "/v1/translator"

    def _translate(self, texts, ctx):
        direction = f"{self._LANG.get(ctx.source_lang, ctx.source_lang)}2{self._LANG.get(ctx.target_lang, ctx.target_lang)}"
        body = {"source": texts, "trans_type": direction, "request_id": "gloss", "media": "text",
                "detect": ctx.source_lang == "auto"}  # 自动识别原文语言时必须带 detect
        resp = self._client.post(self._url, json=body, headers={"X-Authorization": f"token {self._token}"})
        resp.raise_for_status()
        data = resp.json()
        if "target" not in data:
            raise TranslateError(f"彩云小译没有返回译文（可能不支持 {direction} 这个方向）：{str(data)[:120]}")
        return list(data["target"])
