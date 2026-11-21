"""翻译引擎登记表：有哪些引擎、各自要填什么、验证到了什么程度。

界面上的引擎列表和设置项都是从这张表生成的；加一个引擎 = 在这里加一项 + 写一个实现类。
这个文件只有数据，不导入任何实现，所以设置模块可以放心引用它。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    secret: bool = False
    placeholder: str = ""
    default: str = ""
    hint: str = ""


@dataclass(frozen=True)
class Engine:
    id: str
    label: str
    group: str  # 本地 | 在线机翻 | 大模型
    kind: str  # 用哪个实现类
    note: str = ""
    fields: tuple[Field, ...] = ()
    # 验证程度，界面上如实显示：
    #   real    连真实服务跑通过
    #   docs    按官方文档实现，只用模拟服务器测过（没有密钥）
    #   memory  官方文档没查到，按已知的协议实现，只用模拟服务器测过
    verified: str = "docs"


_KEY = Field("api_key", "API 密钥", secret=True)


def _llm(id: str, label: str, base_url: str, model: str = "", note: str = "", local: bool = False) -> Engine:
    """讲 OpenAI 兼容协议的大模型服务：只是地址不同。"""
    fields = [Field("model", "模型", placeholder="模型名，见该平台的模型列表", default=model)]
    if not local:
        fields.insert(0, _KEY)
    fields.append(Field("base_url", "接口地址", default=base_url))
    return Engine(id, label, "本地" if local else "大模型", "openai", note or "走 OpenAI 兼容协议。带术语表和最近几句对话作上下文，流式显示。",
                  tuple(fields), "docs")


ENGINES: tuple[Engine, ...] = (
    # ---- 本地 ----
    Engine("hymt", "混元 Hy-MT2（本地翻译模型，推荐）", "本地", "hymt",
           "腾讯混元的专用翻译模型（1.8B），完全离线，原生支持术语表和背景说明。开始翻译时启动、停止后退出。"
           "在 RTX 5060 上实测：显卡空闲时单句约 85 ms、占显存约 1.4 GB；游戏把显卡占满时自动改用 CPU，单句约 0.4 秒。", verified="real"),
    Engine("nllb", "NLLB-200（本地翻译模型，轻量）", "本地", "nllb",
           "Meta 的传统机翻模型，纯 CPU 运行，不占显存（内存约 0.7 GB，单句约 230 ms）。"
           "译文质量明显不如混元，术语表基本不起作用，许可证禁止商用。只建议在显存和内存都很紧张时用。", verified="real"),
    _llm("ollama", "Ollama（本地大模型）", "http://localhost:11434/v1", local=True,
         note="需要自己安装 Ollama 并下载模型。通用大模型做实时翻译通常比专用翻译模型慢。"),
    _llm("lmstudio", "LM Studio（本地大模型）", "http://localhost:1234/v1", local=True,
         note="需要在 LM Studio 里加载模型并开启本地服务。"),
    _llm("llamacpp", "llama.cpp / Sakura（本地大模型）", "http://localhost:8080/v1", local=True,
         note="连接自己启动的 llama-server。对 llama.cpp 的真实服务验证过。"),
    # ---- 在线机翻 ----
    Engine("google", "Google 机翻（免密钥）", "在线机翻", "google",
           "不需要密钥，开箱即用。逐句机翻，没有上下文；术语表通过翻译前替换生效。这是非官方接口，请求太频繁会被限流。",
           verified="real"),
    Engine("deepl", "DeepL API", "在线机翻", "deepl", "官方接口，免费版和专业版密钥都可以（按密钥结尾的 :fx 自动区分）。一次请求翻一整批。",
           (_KEY,)),
    Engine("deeplx", "DeepLX / DLX（自建）", "在线机翻", "deeplx", "连接自己搭的 DeepLX（现名 DLX）服务。它是非官方项目，稳定性取决于上游。",
           (Field("url", "服务地址", default="http://localhost:1188"), Field("token", "访问令牌", secret=True, hint="没设就留空"))),
    Engine("azure", "微软 Azure 翻译", "在线机翻", "azure", "Azure AI Translator 的官方接口。一次请求翻一整批。",
           (_KEY, Field("region", "区域", placeholder="例如 eastasia", hint="资源所在区域")), "memory"),
    Engine("baidu", "百度翻译", "在线机翻", "baidu", "百度翻译开放平台的通用文本翻译。标准版每秒只能请求 1 次，所以一屏文字合成一次请求。",
           (Field("app_id", "APP ID"), Field("secret", "密钥", secret=True)), "memory"),
    Engine("youdao", "有道智云", "在线机翻", "youdao", "有道智云的文本翻译服务（v3 签名）。",
           (Field("app_key", "应用 ID"), Field("app_secret", "应用密钥", secret=True))),
    Engine("tencent", "腾讯云机器翻译", "在线机翻", "tencent", "腾讯云 TMT 的批量文本翻译（TC3 签名）。",
           (Field("secret_id", "SecretId"), Field("secret_key", "SecretKey", secret=True),
            Field("region", "地域", default="ap-guangzhou")), "memory"),
    Engine("caiyun", "彩云小译", "在线机翻", "caiyun", "彩云小译的官方接口。主要支持其它语言和中文互译。",
           (Field("token", "令牌", secret=True),)),
    # ---- 大模型 ----
    _llm("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    _llm("openai", "OpenAI", "https://api.openai.com/v1"),
    _llm("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
    _llm("qwen", "通义千问（阿里云百炼）", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    _llm("zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4"),
    _llm("moonshot", "Kimi（月之暗面）", "https://api.moonshot.cn/v1"),
    _llm("doubao", "豆包（火山方舟）", "https://ark.cn-beijing.volces.com/api/v3", note="走 OpenAI 兼容协议。模型一栏填方舟控制台里的推理接入点或模型名。"),
    _llm("siliconflow", "硅基流动", "https://api.siliconflow.cn/v1"),
    _llm("openrouter", "OpenRouter", "https://openrouter.ai/api/v1"),
    Engine("claude", "Claude API", "大模型", "claude", "Anthropic 官方 SDK。带术语表和最近几句对话作上下文，流式显示。",
           (Field("api_key", "API 密钥", secret=True, placeholder="sk-ant-…", hint="留空则用环境变量 ANTHROPIC_API_KEY"),
            Field("model", "模型", default="claude-opus-5-5")), "docs"),
    _llm("openai_compat", "自定义 OpenAI 兼容接口", "", note="任何讲 OpenAI 兼容协议的服务：填地址、模型名和密钥。"),
)

BY_ID = {e.id: e for e in ENGINES}

VERIFIED_TEXT = {
    "real": "",
    "docs": "这个引擎按官方文档实现，但我手头没有密钥，还没连真实服务验证过。",
    "memory": "这个引擎的官方文档没能查到，是按已知的协议实现的，还没连真实服务验证过。",
}


def default_settings() -> dict:
    """每个引擎的设置项及默认值，并入设置的 translator 段。"""
    out = {e.id: {f.key: f.default for f in e.fields} for e in ENGINES if e.fields}
    out["claude"]["effort"] = "low"
    out["hymt"] = {"device": "auto", "threads": 0}
    return out
