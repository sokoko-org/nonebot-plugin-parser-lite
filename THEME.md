# 渲染主题开发指南

本指南旨在帮助开发者了解并快速开发 `nonebot-plugin-parser-lite` 的自定义渲染主题。主题基于 Jinja2 模板引擎与 CSS 建立，最终由渲染器生成图片消息。

## 一、 整体解析与渲染流程

插件在处理数据并渲染成图时，遵循以下核心工作流：

```text
平台解析器
   └─> ParseResult (原始数据)
         └─> Theme API v1 数据格式
               └─> 匹配最佳模板 (Jinja)
                     └─> 渲染生成 HTML
                           └─> Blitz 分层渲染
                                 └─> 发送图片消息
```

> [!NOTE]
> **数据传入机制**
>
> 渲染模板时，模板上下文**仅接收一个名为 `data` 的根对象**。模板的核心职责即为对 `data` 内部的数据进行样式渲染与排版展示。

渲染模板中对 http(s) 的访问会被故意忽略，也不支持加载 JavaScripts。详细文档可参考 [blitz-py](https://github.com/adrienbrault/blitz-py)

```jinja
{# 示例：访问全局 data 对象 #}
{{ data.post.title }}
{{ data.post.author.name }}

{% for item in data.post.content %}
  {{ item.type }}
{% endfor %}
```

## 二、 主题目录与文件结构

### 1. 基础主题结构

一个合法的最小主题包必须包含以下两个文件：

```text
my-theme/
├── theme.json           # 主题元数据配置文件
└── default.html.jinja   # 默认/兜底渲染模板
```

### 2. 完整主题结构示例

您可以根据需求在主题目录中扩展多个平台专属模板及静态资源：

```text
my-theme/
├── theme.json
├── default.html.jinja    # 默认兜底模板（通用）
├── music.html.jinja      # 音乐类平台通用模板
├── netease.html.jinja    # 网易云音乐专属模板
├── theme.css             # 主题自定义样式表
└── assets/               # 静态资源目录
    ├── logo.png
    └── background.webp
```

> [!TIP]
>
> - `default.html.jinja` 是主题的**强制兜底模板**，当没有匹配到特定的平台模板时会使用此文件。
> - CSS 文件与静态资源文件名均无强制命名限制，引入时采用相对路径即可。

## 三、 主题配置与安装

### 1. 编写元数据文件 theme.json

每个主题根目录下必须包含 theme.json，用于声明主题信息：

```json
{
  "schema_version": 1,
  "id": "my-custom-theme",
  "name": "极简暗黑主题",
  "desc": "适用于各大平台的暗色调优雅渲染主题",
  "author": "开发者名称",
  "version": "1.0.0"
}
```

| 字段名称         | 是否必填 | 类型     | 说明                                                                                                  |
| ---------------- | -------- | -------- | ----------------------------------------------------------------------------------------------------- |
| `schema_version` | 否       | `number` | 配置规范版本，目前固定为 `1`（缺省时默认为 `1`）。若后续版本不兼容将自动忽略该主题。                  |
| `id`             | 是       | `string` | 主题唯一标识。仅允许字母、数字和连字符（`-`），且必须以字母或数字开头。用户配置中通过此 ID 匹配主题。 |
| `name`           | 否       | `string` | 主题展示名称，缺省时自动使用 `id`。                                                                   |
| `desc`           | 否       | `string` | 主题简要描述。                                                                                        |
| `author`         | 否       | `string` | 主题作者信息。                                                                                        |
| `version`        | 否       | `string` | 主题语义化版本号。更新版本号可强制刷新插件的渲染缓存。                                                |

### 2. 主题安装与加载顺序

插件启动时，会按照以下优先级顺序检索主题：

1. 用户自定义配置目录 `plite_theme_dirs`
2. 插件数据存储目录下的 `themes/`
3. 插件包内置的模板目录 `render/templates/`（最终兜底）

加载方式配置（`.env` 或配置文件）
`plite_theme_dirs` 支持配置为**单个主题目录**，或者**包含多个子主题的根目录**：

```toml
# extra_config.toml
plite_render_theme = "my-custom-theme" # 当前选中的主题 ID

plite_theme_dirs = [
  "D:/bot/themes/my-custom-theme",       # 单主题目录
  "D:/bot/themes/community-themes-pack"  # 多主题集合目录
]
```

多主题集合目录的合法结构示例：

```text
community-themes-pack/
├── pink-cute/
│   ├── theme.json
│   └── default.html.jinja
└── minimal-mono/
    ├── theme.json
    └── default.html.jinja
```

> [!WARNING]
> 若多个主题定义了重复的 `id`，后加载的主题将覆盖先加载的主题。
>
> 若目标主题无效（包含损坏的 `theme.json` 或版本不兼容），插件将自动回退使用内置默认主题。

## 四、 模板选择与回退机制

当解析目标平台（例如：网易云音乐 `netease`）时，插件查找模板的匹配顺序如下：

```text
1. <platform>.html.jinja   (例如: netease.html.jinja - 平台专属)
      │
      ▼
2. music.html.jinja        (仅音乐类平台会触发此级查找 - 领域通用)
      │
      ▼
3. default.html.jinja      (当前主题目录下的通用兜底)
      │
      ▼
4. 内置 default.html.jinja  (插件内置终极兜底)
```

### 1. 音乐平台定义

目前系统认定的音乐平台标识 ID 如下（详见源码 `src/nonebot_plugin_parser_lite/render/theme.py`）：

- `kugou` (酷狗)
- `netease` (网易云音乐)
- `kuwo` (酷我)
- `qsmusic` (汽水音乐)
- `qqmusic` (QQ音乐)

> [!IMPORTANT]
> 模板文件名必须严格使用**平台 ID**（小写字母），不能使用平台的中文显示名称。
>
> 例如：网易云音乐应命名为 `netease.html.jinja`，而非 `网易云音乐.html.jinja`。平台 ID 汇总参考源码 `constants.py`。

## 五、 Theme API v1 数据结构

模板中通过 `data` 对象获取渲染所需的全部信息，支持的最高层级字段如下：

```javascript
data.schema_version; // [number] 当前协议版本号 (1)
data.theme; // [string] 当前色彩模式："light" | "dark"
data.theme_id; // [string] 当前生效的主题 ID
data.meta; // [object] 渲染相关的元数据
data.post; // [object] 动态/帖子核心数据
```

### 1. `data.meta`（元信息）

| 字段             | 类型     | 说明                                  |
| ---------------- | -------- | ------------------------------------- |
| `bot_name`       | `string` | 机器人名称                            |
| `rendering_time` | `string` | 渲染时间，格式：`YYYY-MM-DD HH:MM:SS` |
| `width`          | `number` | 建议卡片容器宽度（默认推荐 `620px`）  |

### 2. `data.post`（帖子/动态主数据）

| 字段                 | 类型             | 说明                                                  |
| -------------------- | ---------------- | ----------------------------------------------------- |
| `title`              | `string \| null` | 帖子标题                                              |
| `url`                | `string`         | 原始动态/帖子跳转链接                                 |
| `formatted_datetime` | `string`         | 格式化的发布时间（无时间时为空字符串）                |
| `timestamp`          | `number \| null` | 秒级时间戳                                            |
| `platform`           | `object`         | 平台属性对象（详细介绍见下表）                        |
| `author`             | `object`         | 作者信息对象（详细介绍见下表）                        |
| `content`            | `array`          | 正文内容项列表（元素结构见第六章节）                  |
| `stats`              | `object`         | 交互统计数据                                          |
| `comments`           | `array`          | 评论列表                                              |
| `repost`             | `object \| null` | 转发的原帖数据（嵌套结构与 `post` 相同）              |
| `qrcode`             | `string \| null` | 帖子二维码的 Data URI（需开启 `plite_append_qrcode`） |
| `ai_summary`         | `string \| null` | AI 生成的摘要文本                                     |
| `extra`              | `object`         | 平台扩展参数（结构因平台不同而异，需做判空处理）      |

平台属性 `post.platform`

- `id`: 平台 ID（如 `"bilibili"`, `"netease"`）
- `name`: 平台显示名称（如 `"哔哩哔哩"`）
- `logo`: 平台图标 URI（若获取失败会自动使用内置占位图）

作者信息 `post.author`

- `name`: 作者昵称
- `id`: 作者唯一 ID（可能为 `null`）
- `avatar`: 头像 URI
- `description`: 个人简介（可能为 `null`）
- `location`: IP 归属地（可能为 `null`）

交互统计 `post.stats`
包括基础指标：`view_count`、`like_count`、`collect_count`、`share_count`、`comment_count`（均已格式化为字符串，如 `"1.2万"`）。

此外包含平台特殊统计项 `post.stats.extra`：

```jinja
{% for item in post.stats.extra %}
  {% if item.value is not none %}
    <span class="stat-item stat-{{ item.key }}">
      <b>{{ item.value }}</b>
      <small>{{ item.label }}</small>
    </span>
  {% endif %}
{% endfor %}
```

## 六、 正文内容类型 (`post.content`) 渲染规范

`post.content` 数组包含了文章或动态的所有正文元素，模板需针对不同的 `type` 逐一渲染：

### 1. 文本 (`text`)

```json
{
  "type": "text",
  "text": "第一行正文\n第二行正文"
}
```

> [!NOTE]
> 文本内容可能包含换行符，建议在 CSS 中设置 `.text { white-space: pre-wrap; word-break: break-word; }`。

### 2. 普通图片与封面 (`image` / `cover`)

```json
{
  "type": "image",
  "src": "file:///path/to/img.png",
  "layout": "grid", // 布局建议："grid" (网格) | "x" (横向推特流)
  "width": 800, // 像素尺寸
  "height": 400,
  "orientation": "landscape", // "portrait"表示尺寸为竖图，"landscape"尺寸为横图
  "source_url": "http://..." // 原始网络地址（不建议模板直接请求）
}
```

```json
{
  "type": "cover",
  "src": "file:///path/to/img.png",
  "layout": "grid", // "grid" | "x"，封面不需要处理布局建议
  "width": 800,
  "height": 400,
  "orientation": "landscape",
  "alt": "...",
  "source_url": "https://.."
}
```

- 封面图 (`cover`)：音乐平台的第一张图片或封面卡片会标记为 `cover。`

### 3. 实况照片 (`live_photo`)

```json
{
  "type": "live_photo",
  "src": "...",
  "layout": "grid",
  "width": 800,
  "height": 400,
  "orientation": "landscape",
  "is_live": true,
  "source_url": "https://.."
}
```

- 可根据 `item.is_live == true` 在 UI 上叠加“实况/Live”角标。

### 4. 独立图文卡片 (`graphic`)

```json
{
  "type": "graphic",
  "src": "file:///path/to/img.png",
  "width": 800,
  "height": 400,
  "orientation": "landscape",
  "alt": "...",
  "source_url": "https://.."
}
```

- `graphic` 类型为带说明的独立图片，不应混入普通多图网格（Grid）中展示。

### 5. 贴纸/表情包 (`sticker`)

```json
{
  "type": "sticker",
  "src": "...",
  "size": "small", // 表情尺寸，small / medium
  "description": "笑哭", // 贴纸描述
  "source_url": "..."
}
```

- 若 `src` 为 `null`，应回退显示 `description`（如 `[笑哭]`）。

### 6. 音视频媒体 (`video` / `audio`)

```json
// video
{
  "type": "video",
  "src": "封面URI",
  "duration": "01:23", // 视频时长
  "speedup": "1.25x", // 视频倍速，1倍速时为 null
  "size": "12.34MB", // 视频大小
  "source_url": "..."
}

// audio
{
  "type": "audio",
  "duration": "03:45",
  "speedup": "1.25x",
  "size": "7.63GB",
  "source_url": "..."
}
```

### 7. 链接卡片与引用 (`link` / `quote`)

```json
// link
{
  "type": "link",
  "url": "string", // 链接地址
  "title": "string", // 链接标题
  "site_name": "string / null", // 来源站点名称
  "description": "string / null", // 链接摘要
  "icon": "uri / null", // 链接站点 icon
  "preview": "uri / null" // 链接预览图片
}

// quote
{
  "type": "quote",
  "text": "引用内容",
  "title": "string / null", // 引用来源标题
  "url": "string / null", // 引用来源链接
  "icon": "uri / null" // 引用来源图标或头像
}
```

### 8. 投票模块 (`poll`)

```json
{
  "type": "poll",
  "title": "string / null", // 投票标题
  "options": [
    {
      "text": "选项 A", // 选项文本
      "votes": 10, // 选项票数
      "percentage": 62.5, // float
      "image": "uri / null" // 选项图片
    },
    ...
  ],
  "option_vote_total": 123, // 选项票数之和
  "total_votes": 123 / null, // 平台返回的总票数，多选时可能大于投票人数
  "total_voters": 123 / null, // 投票人数
  "multiple": false, // 是否允许多选
  "closed": false, // 投票是否已结束
  "close_at": "2026-xx-...", // 投票结束时间，由平台保留原始表示
  "has_images": false // 是否有选项图片
}
```

- `percentage` 字段已计算为百分比数值，可直接用于进度条渲染：

```jinja
<div class="poll-bar" style="width: {{ '%.2f'|format(option.percentage) }}%"></div>
```

### 9. 未知类型兜底 (`unknown`)

为保证向前兼容，未识别的新类型数据统一封装为 `type="unknown"`：

```jinja
{% else %}
  <p class="unknown-type">{{ item.text }}</p>
{% endif %}
```

## 七、 模板与样式编写规范

### 1. Jinja2 转义原则

> [!IMPORTANT]
> **切勿重复使用转义过滤器 `|e`**
>
> 渲染管道在向 Jinja2 传入数据前已统一完成安全转义，同时自动转义功能在 Jinja 环境中已关闭。
>
> - **正确**：`{{ post.title }}`
> - **错误**：`{{ post.title | e }}`（会导致字符被双重转义，如显示为 `&amp;lt;`）

### 2. HTML 与容器结构要求

生成图的截图区域基于 HTML 中的 `<main>` 节点，因此模板**必须包含 `<main>` 元素**作为根容器：

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="{{ data.theme }}">
  <head>
    <meta charset="UTF-8" />
    <link rel="stylesheet" href="theme.css" />
  </head>
  <body>
    <!-- 必须存在 main 容器，用于捕获渲染区域 -->
    <main class="theme-card">
      <!-- 内容区域 -->
    </main>
  </body>
</html>
```

### 3. CSS 与主题资源规范

相对路径与静态资源

CSS 及图片资源的引入推荐使用相对路径，其解释起点为**当前主题文件根目录**：

```html
<link rel="stylesheet" href="theme.css" />
<img src="assets/background.png" alt="背景" />
```

内置图标支持 (`icon.css`)

渲染器会自动向页面注入全局图标样式表。即使不引入外部图标库，也可直接使用内置类名：

```html
<i class="fa-icon fa-heart"></i>
<i class="fa-icon fa-comment-dots"></i>
<i class="fa-icon fa-play"></i>
```

深浅色模式适配 (`data-theme`)

结合 `data.theme` 全局变量控制暗色模式：

```css
:root {
  --bg-color: #ffffff;
  --text-color: #202020;
}

[data-theme="dark"] {
  --bg-color: #1a1a1a;
  --text-color: #f5f5f5;
}

body {
  background: var(--bg-color);
  color: var(--text-color);
}
```

## 八、 常见问题排查 (FAQ)

### Q1: 编写的主题模板没有生效？

1.  检查 `theme.json` 中的 `id` 是否与配置文件中的 `plite_render_theme` 保持一致。
2.  检查 `id` 是否遵循命名规则（小写字母、数字、连字符）。
3.  确认 `plite_theme_dirs` 的目录路径是否准确指向了主题文件夹或其父级目录。
4.  若为平台模板，确认文件名使用了小写的平台 ID（如 `bilibili.html.jinja`）。

### Q2: 为什么修改了 CSS 或 HTML 后渲染效果没有发生变化？

渲染器为了保证性能默认启用了渲染结果缓存。在开发和调试阶段，可以通过**递增 `theme.json` 中的 `version` 字段**（如 `1.0.0` -> `1.0.1`）来强制刷新缓存。

### Q3: 可以在 Jinja2 模板中调用 Python 方法吗？

**不可以**。出于安全性考虑，渲染上下文并未向 Jinja 环境注入任何 Python 执行方法，仅暴露预置的 `data` 数据结构。

## 九、 拓展资源与样例

- 官方主题仓库：[sokoko-org/nonebot-plugin-parser-themes](https://github.com/sokoko-org/nonebot-plugin-parser-themes)
  - 包含了 `pink-cute`、`minimal-mono`、`hatsune-miku` 等示例主题源码，可作为开发参考。
