# Parser Lite Standalone

这是从 `main` 自动生成的独立模块版本，发布在 `standalone` 分支。它保留
`nonebot_plugin_parser_lite` 包路径与各平台 Parser 路径，但不依赖 NoneBot、适配器或
任何 NoneBot 插件。

> [!IMPORTANT]
>
> 严禁将本项目用于任何非法用途
>
> 由于使用不当造成的一切责任由使用者承担，本项目维护者无任何责任

## 复制到项目中使用

将 `src/nonebot_plugin_parser_lite` 整个目录复制到目标项目中。目标
项目需要安装 `requirements.txt` 中列出的普通 Python 运行依赖，但不需要安装 NoneBot、
适配器或任何 NoneBot 插件，也不依赖本仓库中的其他目录。

复制后目录结构示例：

```text
your_project/
├── nonebot_plugin_parser_lite/
│   ├── parsers/
│   ├── render/
│   ├── utils/
│   ├── __init__.py
│   └── ...
└── your_code.py
```
或
```text
your_project/
├── utils/
│   └── nonebot_plugin_parser_lite/
│       ├── parsers/
│       ├── render/
│       ├── utils/
│       ├── __init__.py
│       └── ...
└── your_code.py
```

## 文本解析流水线

解析入口只接受文本。`until` 可停在匹配、结构化解析、模板数据解析或图片
渲染阶段，默认停留在解析阶段，不会进行渲染

```python
from nonebot_plugin_parser_lite import ParseStep, Parser

async with Parser() as parser:
    matched = await parser.parse(text, until=ParseStep.MATCH)
    result = await parser.parse(text, until=ParseStep.PARSE)
    template_data = await parser.parse(text, until=ParseStep.RESOLVE)
    image_bytes = await parser.parse(text, until=ParseStep.RENDER)

# 长期运行的应用可以复用 Parser 实例，并在退出前调用 await parser.aclose()
```

只使用一个平台时应直接导入对应 Parser，避免加载其他平台模块：

```python
from nonebot_plugin_parser_lite import Parser
from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser

async with Parser([BilibiliParser]) as parser:
    result = await parser.parse("看看这个 https://www.bilibili.com/video/BV1xx411c7mD")
```

也可以保留原有的底层调用方式：

```python
from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser

parser = BilibiliParser()
keyword, searched = parser.search_url("https://www.bilibili.com/video/BV1xx411c7mD")
result = await parser.parse(keyword, searched)
await parser.aclose()
```

## 配置

配置默认从同名环境变量读取，例如 `PLITE_BILI_CK`、`PLITE_MAX_COMMENTS`。
列表和布尔值使用 JSON 格式。也可在导入后更新共享配置：

```python
from nonebot_plugin_parser_lite import configure

configure(plite_max_comments=10, plite_disabled_platforms=["x"])
```

缓存根目录默认是当前目录的 `.parser-lite`，可通过 `PARSER_LITE_BASE_DIR` 修改。
图片渲染使用 Playwright Chromium，并固定以无头模式运行。
解析结果会保留最近 50 项；首次进入异步解析时会在当前事件循环注册每两小时执行一次
的缓存清理任务。应用退出前可调用 `await shutdown_runtime()` 关闭定时任务和浏览器。

## 独立版边界

消息发送、权限、事件、回复和表情回应属于机器人框架职责，不包含在独立版中。独立版
仅保留解析运行所需的 asyncio 周期任务。解析结果中的媒体任务仍是惰性的：只有显式
等待媒体路径或进入解析/渲染的相应阶段时才会下载。
