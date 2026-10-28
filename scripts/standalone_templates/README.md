# Parser Lite Standalone 独立版指南

这是从 `main` 分支自动生成的独立模块版本（发布在 `standalone` 分支），可直接在其他应用项目中使用。

---

## 📦 安装与项目集成

需要 Python **3.11 或更高版本**

从 Git 或源码安装还需要 Rust 工具链用于编译模块。以下方式任选其一

### 下载编译产物安装

从 Release 下载独立版 wheel，或在 [Actions](https://github.com/sokoko-org/nonebot-plugin-parser-lite/actions/workflows/build.yml) 下载安装对应平台的产物

### 从 Git 或源码安装

```shell
python -m pip install "nonebot-plugin-parser-lite-standalone @ git+https://github.com/sokoko-org/nonebot-plugin-parser-lite.git@standalone"
```

安装完成后即可在项目中导入使用

### 手动复制到项目

在仓库根目录安装依赖并编译 QMC 模块(或者从产物 whl 解压)

```shell
python -m pip install "setuptools>=77" "setuptools-rust>=1.12,<2"
python setup.py build_ext --inplace
```

随后将 `src/nonebot_plugin_parser_lite` 复制到你的项目中

```text
your_project/
├── nonebot_plugin_parser_lite/
│   ├── parsers/
│   ├── utils/
│   └── __init__.py
└── your_code.py
```

并在项目环境安装运行依赖

```shell
python -m pip install -r requirements.txt
```

## 🚀 快速上手

### 1. 文本解析流水线

解析入口接收文本，也可以接收已有的 `MatchResult` 或 `ParseResult` 继续后续阶段。
通过 `until` 参数控制执行到哪一步

- `ParseStep.MATCH`：仅匹配阶段
- `ParseStep.PARSE`：结构化解析（默认）
- `ParseStep.RESOLVE`：生成渲染数据（会触发媒体下载）
- `ParseStep.RENDER`：返回 `RenderResult`，含解析结果、实际图片格式和图片 bytes

```python
from nonebot_plugin_parser_lite import ParseStep, Parser

async with Parser() as parser:
    # 1. 仅匹配
    matched = await parser.parse(text, until=ParseStep.MATCH)

    # 2. 结构化解析
    result = await parser.parse(matched, until=ParseStep.PARSE)

    # 3. 生成模板数据（含媒体下载）
    render_data = await parser.parse(result, until=ParseStep.RESOLVE)

    # 4. 从解析结果继续生成图片，也可直接传入 text
    rendered = await parser.parse(result, until=ParseStep.RENDER)

    # 可从渲染结果获取原始媒体
    for media in rendered.result.iter_sendable_media():
        media_path = await media.get_path()

    from pathlib import Path

    Path(f"post.{rendered.image_format}").write_bytes(rendered.image)

# 注：长期运行的应用可复用 Parser 实例，退出前调用 await parser.aclose()
```

`RenderResult.result` 保留传入的解析结果及其媒体。
仅需生成渲染数据，或已有渲染数据时，也可直接使用底层接口

```python
from nonebot_plugin_parser_lite import resolve_parse_result

render_data = await resolve_parse_result(result, color_scheme="dark", theme_id="custom")
```

```python
from pathlib import Path
from nonebot_plugin_parser_lite import render_theme_data

image_format, image = await render_theme_data(render_data)
Path(f"post.{image_format}").write_bytes(image)
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
