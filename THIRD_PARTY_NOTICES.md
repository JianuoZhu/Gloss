# 第三方组件

Gloss 的打包版本里带有下面这些开源组件。它们各自的版权归原作者所有，按各自的许可证分发；
许可证全文见各组件的包目录（打包版在 `_internal` 下对应的文件夹里）或它们的项目主页。

下表里的许可证是我按各项目公开的信息整理的，分发前请以各项目仓库里的许可证文件为准。

## 随程序分发的组件

| 组件 | 用途 | 许可证 |
|---|---|---|
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/) 和 Qt 6 | 界面 | LGPL-3.0（Qt 的库以动态链接的 DLL 形式随附，可以替换） |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | 文字识别的流程 | Apache-2.0 |
| [PP-OCR 模型](https://github.com/PaddlePaddle/PaddleOCR)（PP-OCRv6 检测 / 识别） | 文字识别模型 | Apache-2.0 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime)（DirectML 版） | 运行识别模型 | MIT |
| [OpenCV](https://github.com/opencv/opencv) | 图像处理 | Apache-2.0 |
| [NumPy](https://numpy.org/) | 数组运算 | BSD-3-Clause |
| [windows-capture](https://github.com/NiiightmareXD/windows-capture) | 窗口画面捕获 | MIT |
| [python-mss](https://github.com/BoboTiG/python-mss) | 屏幕区域捕获 | MIT |
| [PyWinRT](https://github.com/pywinrt/pywinrt) | 调用 Windows 自带的 OCR | MIT |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | 运行 NLLB 模型 | MIT |
| [SentencePiece](https://github.com/google/sentencepiece) | NLLB 的分词 | Apache-2.0 |
| [HTTPX](https://github.com/encode/httpx) | 网络请求 | BSD-3-Clause |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | Claude 翻译后端 | MIT |
| [psutil](https://github.com/giampaolo/psutil) | 占用监测 | BSD-3-Clause |
| [Pillow](https://github.com/python-pillow/Pillow)、[PyYAML](https://github.com/yaml/pyyaml)、[Shapely](https://github.com/shapely/shapely)、[pyclipper](https://github.com/fonttools/pyclipper) 等 | RapidOCR 的依赖 | 各自的开源许可证（MIT / BSD 等） |
| [Python](https://www.python.org/) 运行时 | — | PSF-2.0 |

## 不随程序分发、由用户按需下载的内容

在「设置」页点「下载」时，Gloss 会从下面的官方地址取这些文件，放在 `%LOCALAPPDATA%\Gloss\local-mt`：

| 内容 | 来源 | 许可证 |
|---|---|---|
| 混元翻译模型 Hy-MT2 1.8B（GGUF） | [tencent/Hy-MT2-1.8B-GGUF](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF) | Apache-2.0（模型页面标注） |
| llama.cpp（Windows Vulkan 版，用来运行上面的模型） | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) 的发行包 | MIT |
| NLLB-200 蒸馏版 600M（CTranslate2 转换） | [JustFrederik/nllb-200-distilled-600M-ct2-int8](https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8) | CC-BY-NC-4.0，**禁止商用** |

## 在线服务

Gloss 可以调用多家在线翻译服务（列表见 README）。这些服务各有自己的使用条款和收费方式，
密钥由用户自己申请和填写，Gloss 不附带任何密钥。其中「Google 机翻（免密钥）」用的是非官方接口。
