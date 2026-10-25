# Parser Lite Standalone 独立版指南

这是从 `main` 分支自动生成的独立模块版本（发布在 `standalone` 分支），可直接在其他应用项目中使用。

---

## 📦 安装与项目集成

将 `src/nonebot_plugin_parser_lite` 整个目录复制到你的项目中

```text
your_project/
├── nonebot_plugin_parser_lite/
│   ├── parsers/
│   ├── utils/
│   └── __init__.py
└── your_code.py
```

同时，在你的项目中安装 `requirements.txt` 中列出的基础依赖即可

## 🚀 快速上手

### 1. 文本解析流水线

解析入口接收纯文本。可通过 `until` 参数控制解析阶段

- `ParseStep.MATCH`：仅匹配阶段
- `ParseStep.PARSE`：结构化解析（默认）
- `ParseStep.RESOLVE`：生成渲染数据（会触发媒体下载）

```python
from nonebot_plugin_parser_lite import ParseStep, Parser

async with Parser() as parser:
    # 1. 仅匹配
    matched = await parser.parse(text, until=ParseStep.MATCH)

    # 2. 结构化解析
    result = await parser.parse(text, until=ParseStep.PARSE)

    # 3. 生成模板数据（含媒体下载）
    render_data = await parser.parse(text, until=ParseStep.RESOLVE, color_scheme="dark")

# 注：长期运行的应用可复用 Parser 实例，退出前调用 await parser.aclose()
```

`render_data`中的图片、头像、平台图标、封面等资源使用 `data:image/...;base64,...`
内嵌

已有 `ParseResult` 时，也可直接转换

```python
from nonebot_plugin_parser_lite import resolve_parse_result

render_data = await resolve_parse_result(result, color_scheme="dark", theme_id="custom")
# 事实上，`theme_id` 在独立版没有用
```

### 2. 按需加载指定平台

若只需使用特定平台，建议直接导入对应 Parser，避免加载无用模块

```python
from nonebot_plugin_parser_lite import Parser
from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser

async with Parser([BilibiliParser]) as parser:
    result = await parser.parse("看看这个 https://www.bilibili.com/video/BV1xx411c7mD")
```

### 3. 底层调用方式

```python
from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser

parser = BilibiliParser()
keyword, searched = parser.search_url("https://www.bilibili.com/video/BV1xx411c7mD")
result = await parser.parse(keyword, searched)
await parser.aclose()
```

## ⚙️ 配置与缓存

### 1. 环境变量与动态配置

配置默认读取同名环境变量

```python
from nonebot_plugin_parser_lite import configure

configure(plite_max_comments=10, plite_disabled_platforms=["x"])
```

### 2. 缓存与定时任务

- 缓存根目录默认为当前目录下的 `.parser-lite`（可通过配置项 `PARSER_LITE_BASE_DIR` 修改）
- 首次进入异步解析时，会在当前事件循环自动注册周期缓存清理任务
- 应用程序退出前，可调用 `await shutdown_runtime()` 关闭后台定时任务
