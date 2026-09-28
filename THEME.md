# 渲染主题开发指南

## 解析流程

```text
平台解析器
    -> ParseResult
    -> Theme API v1 数据
    -> 选择模板
    -> Jinja 渲染 HTML
    -> 浏览器截图
    -> 图片消息
```

如上，模板只会收到一个名为 `data` 的根对象

```jinja
{{ data.post.title }}
{{ data.post.author.name }}
{% for item in data.post.content %}
    {{ item.type }}
{% endfor %}
```

所以，模板只需要处理如何展示这些信息

## 主题结构

一个主题至少需要以下两个文件

```text
zszt/
├── theme.json
└── default.html.jinja # 或任一平台的模板文件
```

其余资源不限制数量和名称

```text
zszt/
├── theme.json
├── default.html.jinja
├── music.html.jinja          # 音乐平台的通用模板
├── netease.html.jinja        # 网易云音乐专用模板
├── icon.css                  # 自定义图标样式
├── theme.css                 # 主题自己的 CSS
└── assets/
    ├── logo.png
    └── background.webp
```

`default.html.jinja` 是主题的兜底模板，主要在没有特定平台模板时使用

`icon.css` 和 `theme.css` 不是固定的名字，你要是想，可以把这俩合一块，叫 `zscss.css` 都行

### `theme.json`

```json
{
  "schema_version": 1,
  "id": "zsztdid",
  "name": "...",
  "desc": "bzd",
  "author": "低性能",
  "version": "1.0.0"
}
```

| 字段             | 是否必需 | 说明                                                                              |
| ---------------- | -------- | --------------------------------------------------------------------------------- |
| `schema_version` | 否       | 当前固定为 `1`；省略时按 `1` 处理。未来版本不兼容时，插件会忽略该主题。           |
| `id`             | 是       | 主题唯一 ID，只能由数字字母和连字符组成，且以字母或数字开头<br>是用户选择主题用的 |
| `name`           | 否       | 主题名称，缺省使用 `id`                                                           |
| `desc`           | 否       | 主题描述                                                                          |
| `author`         | 否       | 作者信息                                                                          |
| `version`        | 否       | 主题版本，用更新版本可以让插件不复用旧主题渲染缓存                                |

## 安装主题

插件按以下顺序寻找主

1. `plite_theme_dirs` 配置的目录
2. 插件数据目录下的 `themes/` 目录
3. 插件包内置的 `render/templates` 目录 (兜底)

`plite_theme_dirs` 中的每一项可以是一个主题目录，也可以是包含多个主题子目录的目录

```toml
plite_theme_dirs = [
  "A:/themes/zszt",
  "B:/themes/nonebot-plugin-parser-themes"
]
```

多主题目录的结构如下：

```text
nonebot-plugin-parser-themes/
├── pink-cute/    <- 其实文件夹名称是什么无所谓
│   ├── theme.json
│   └── x.html.jinja
├── minimal-mono/
│   ├── theme.json
│   └── buff.html.jinja
└── hatsune-miku/
    ├── theme.json
    └── bilibili.html.jinja
```

主题 ID 重复时，会有一个倒霉的主题被其他主题覆盖

### 配置主题

```bash
# .env 或你指定的配置文件
plite_render_theme = "zsztdid"
plite_theme_dirs = ["C:/themes/nonebot-plugin-parser-themes"]
```

如果目标主题不存在，插件会使用默认模板。损坏、缺少合法 `theme.json` 或版本不支持的主题也会被忽略

## 模板选择顺序

设当前解析平台的 ID 是 `netease`，则插件会在选中的主题目录中依次查找

```text
netease.html.jinja
music.html.jinja          # 仅音乐平台会查找
default.html.jinja
```

查找顺序如下

1. 平台专属模板 `<platform>.html.jinja`
2. 如果平台是音乐平台，看音乐模板 `music.html.jinja`
3. 看主题的兜底模板 `default.html.jinja`
4. 回退到内置 `default.html.jinja`

目前这些平台是音乐平台，具体可以去看源码 `src\nonebot_plugin_parser_lite\render\theme.py`

```text
kugou
netease
kuwo
qsmusic
```

平台模板文件名要用平台的 ID，不是平台的显示名称

比如网易云音乐使用 `netease.html.jinja`，不能写成 `网易云音乐.html.jinja`

具体的 id 可以去看源码 `src\nonebot_plugin_parser_lite\constants.py`

所以说，你可以写出这样的主题包

- 只提供 `default.html.jinja`，统一处理所有内容
- 提供 `music.html.jinja`，让音乐内容使用另一种布局
- 在此基础上增加 `bilibili.html.jinja`、`netease.html.jinja` 等平台专用模板

> 后续我看看支持一下加载多个主题，这样每个主题可以只负责一个平台，然后走多级回退

这样，一个只想定制网易云音乐的主题可以这样写

```text
zszt/
├── theme.json
└── netease.html.jinja
```

## 模板的基本写法

这是一个最小模板

```jinja
{% set post = data.post %}
<!DOCTYPE html>
<html lang="zh-CN" data-theme="{{ data.theme }}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ post.title or post.platform.name }}</title>
    <link rel="stylesheet" href="我是.css" />
  </head>
  <body>
    <main class="theme-card">
      <header>
        <img src="{{ post.author.avatar }}" alt="" class="avatar" />
        <div>
          <strong>{{ post.author.name }}</strong>
          <small>{{ post.formatted_datetime }}</small>
        </div>
      </header>

      {% if post.title %}<h1>{{ post.title }}</h1>{% endif %}

      <section class="content">
        {% for item in post.content %}
          {% if item.type == "text" %}
            <p class="text">{{ item.text }}</p>
          {% elif item.type in ["image", "cover", "graphic", "live_photo"] %}
            <img src="{{ item.src }}" alt="{{ item.alt or '' }}" class="media" />
          {% elif item.type == "video" %}
            <figure>
              <img src="{{ item.src }}" alt="视频封面" class="media" />
              <figcaption>{{ item.duration }} · {{ item.size }}</figcaption>
            </figure>
          {% elif item.type == "audio" %}
            <p>音频 · {{ item.duration }} · {{ item.size }}</p>
          {% elif item.type == "link" %}
            <a href="{{ item.url }}">{{ item.title }}</a>
          {% elif item.type == "quote" %}
            <blockquote>{{ item.text }}</blockquote>
          {% elif item.type == "poll" %}
            <section>
              <strong>{{ item.title or "投票" }}</strong>
              {% for option in item.options %}
                <p>{{ option.text }}：{{ option.percentage }}%</p>
              {% endfor %}
            </section>
          {% endif %}
        {% endfor %}
      </section>

      {% if post.comments %}
        <section class="comments">
          <h2>评论</h2>
          {% for comment in post.comments %}
            <article>
              <img src="{{ comment.author.avatar }}" alt="" class="comment-avatar" />
              <strong>{{ comment.author.name }}</strong>
              {% for item in comment.content if item.type == "text" %}
                <p>{{ item.text }}</p>
              {% endfor %}
            </article>
          {% endfor %}
        </section>
      {% endif %}
    </main>
  </body>
</html>
```

引入的 `我是.css` 可以这样写

```css
* {
  box-sizing: border-box;
}
html,
body {
  margin: 0;
}
main {
  width: 620px;
  color: #222;
  background: #f5f5f5;
  font-family: system-ui, "Microsoft YaHei", sans-serif;
}
.theme-card {
  width: 620px;
  padding: 32px;
  background: #fff;
}
.media {
  display: block;
  max-width: 100%;
  height: auto;
}
.text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
```

`main` 的宽度会影响出的结果图的宽度，建议是 `620px`

> [!IMPORTANT]
>
> 必须有 `main` 元素作为容器，这是渲染时的目标元素

## Jinja 转义

Jinja 自动转义已被禁用，所以主题模板应直接输出数据

```jinja
{{ post.title }}
{{ item.text }}
<img src="{{ item.src }}" alt="{{ item.alt or '' }}" />
```

不要再次使用 `|e`：

```jinja
{# 错误：会导致 &lt; 等被再次转义 #}
{{ post.title|e }}
```

不用担心 xss 注入，数据在传给模板前都进行了转义处理

## Theme API v1

模板数据只有以下五个根字段

```js
data.schema_version = 1
data.theme          = "light" | "dark"
data.theme_id       = 当前选中的主题 ID
data.post           = 渲染数据
data.meta           = 渲染元数据
```

所有值的类型都只有字典、列表、字符串、数字、布尔值和 `None`

### `data.meta`

| 字段             | 类型   | 说明                                                                                   |
| ---------------- | ------ | -------------------------------------------------------------------------------------- |
| `bot_name`       | string | 机器人名称                                                                             |
| `rendering_time` | string | 渲染时间，格式为 `YYYY-MM-DD HH:MM:SS`。                                               |
| `width`          | number | 建议的`main`宽度，目前为 `620`<br>其实不用管这个，只要你想，你横着排我也能给你正常渲染 |

### `data.post`

| 字段                 | 类型            | 说明                                                                  |
| -------------------- | --------------- | --------------------------------------------------------------------- |
| `title`              | string / `None` | 标题                                                                  |
| `url`                | string          | 原始链接                                                              |
| `formatted_datetime` | string          | 已格式化的发布时间；没有时间时为空字符串                              |
| `timestamp`          | int / `None`    | 原始时间戳，没有时间为 `None`                                         |
| `extra`              | object          | 平台或解析器提供的额外字段，结构因平台而异                            |
| `platform`           | object          | 平台信息                                                              |
| `author`             | object          | 作者信息                                                              |
| `content`            | array           | 正文内容                                                              |
| `stats`              | object          | 统计信息                                                              |
| `comments`           | array           | 评论列表，数量受 `plite_max_comments` 限制                            |
| `qrcode`             | string / `None` | 帖子二维码的 `data:` URI；只有启用 `plite_append_qrcode` 时才会有内容 |
| `ai_summary`         | string / `None` | AI 摘要                                                               |
| `embed_url`          | string / `None` | 可嵌入播放或查看的链接（后续考虑移除）                                |
| `repost`             | object / `None` | 转发的帖子数据，结构与 `data.post` 相同                               |

### `post.platform`

```js
post.platform.id       平台 ID, eg "bilibili"/"netease"
post.platform.name     平台显示名称, eg  "哔哩哔哩"
post.platform.logo     平台图标 URI
```

平台图标下载失败时会使用内置占位图不用判断是否为 `None`

### `post.author`

```js
post.author.name          作者名称
post.author.id            作者 ID，可能为 None
post.author.description   作者简介，可能为 None
post.author.location      IP归属地，可能为 None
post.author.avatar        头像 URI
```

头像没有可用资源时会使用占位图

可以这样判断位置信息等的存在

```jinja
{% if post.author.location %}
  <span>{{ post.author.location }}</span>
{% endif %}
```

### `post.stats`

固定统计字段都是字符串或 `None`

```js
post.stats.view_count;
post.stats.like_count;
post.stats.collect_count;
post.stats.share_count;
post.stats.comment_count;
```

额外统计信息

```js
post.stats.extra = [
  {
    "key": "coin",
    "label": "硬币",
    "value": "1.2万"
  },
  ...
]
```

可以这样遍历

```jinja
{% for item in post.stats.extra %}
  {% if item.value is not none %}
    <span class="stat stat-{{ item.key }}">
      <b>{{ item.value }}</b>
      <small>{{ item.label }}</small>
    </span>
  {% endif %}
{% endfor %}
```

`key` 用来在css中自定义图标，比如 `fa-{{ item.key }}`

### `post.extra`

`extra` 是解析扩展区域，不同平台字段可能不一样

比如

```js
post.extra.album;
post.extra.info;
```

不能认为这些字段一定存在

```jinja
{% if post.extra.album %}
  <span>专辑：{{ post.extra.album }}</span>
{% endif %}
```

## `post.content` 内容项

包含文本、图片和其他媒体

### 文本

```js
{
  "type": "text",
  "text": "低性能机器人"
}
```

文本可能包含换行，CSS 通常需要：

```css
.text {
  white-space: pre-wrap;
}
```

### 图片和封面

> [!IMPORTANT]
>
> `source_url` 是资源的原始 http 网络地址，不建议使用这个字段。模板里不要发起网络请求，后面不一一说了

普通图片

```js
{
  "type": "image",
  "src": "file:///... 或其他可访问 URI",
  "layout": "grid" | "x",
  "is_live": false,
  "source_url": "原始资源地址或 None"
}
```

音乐平台的第一张图片或 `GraphicContent` 会被标记为封面

```js
{
  "type": "cover",
  "src": "...",
  "alt": "专辑封面",
  "layout": "grid",
  "is_live": false,
  "source_url": "..."
}
```

`layout` 是布局提示

- `grid` 表示3x3和2x2网格布局
- `x` 表示推特的横向布局

主题可以遵守它，也可以用自己的布局策略

### 实况照片

```js
{
  "type": "live_photo",
  "src": "底图 URI",
  "layout": "grid",
  "is_live": true,
  "source_url": "..."
}
```

这里的 `src` 是用于渲染卡片的底图

可以用 `is_live` 判断是否添加“实况”标记

### 普通图文卡片

```js
{
  "type": "graphic",
  "src": "图片 URI",
  "alt": "图片说明或 None",
  "source_url": "..."
}
```

`graphic` 不应该参与普通图片网格，是单独展示的带说明的图片

音乐封面如果来自 `GraphicContent`，会被序列化成 `cover`，并额外带上 `layout` 和 `is_live`

### 贴纸

```js
{
  "type": "sticker",
  "src": "贴纸 URI 或 None",
  "size": "small" | "medium",
  "description": "贴纸描述或 None",
  "source_url": "..."
}
```

没有可用贴纸图片时，`src` 为 `None`，主题应回退显示 `description` 或直接跳过

### 视频

```js
{
  "type": "video",
  "src": "视频封面 URI",
  "duration": "1:23",
  "size": "12.34MB",
  "source_url": "原始视频地址或 None"
}
```

`duration` 和 `size` 都是已经格式化好的字符串

### 音频

```js
{
  "type": "audio",
  "duration": "245:13:45",
  "size": "7.63GB",
  "source_url": "原始音频地址或 None"
}
```

### 链接卡片

```js
{
  "type": "link",
  "url": "http://nonebot.dev",
  "title": "链接标题",
  "site_name": "站点名称或 None",
  "description": "摘要或 None",
  "icon": "站点图标 URI 或 None",
  "preview": "预览图 URI 或 None"
}
```

`url` 可以作为 `<a href>`，`icon` 和 `preview` 是可选资源

### 引用

```js
{
  "type": "quote",
  "text": "引用正文",
  "title": "来源标题或 None",
  "url": "来源链接或 None",
  "icon": "来源图标 URI 或 None"
}
```

### 投票

```js
{
  "type": "poll",
  "title": "投票标题或 None",
  "options": [
    {
      "text": "选项 A",
      "votes": 10,
      "percentage": 62.5,
      "image": "选项图片 URI 或 None"
    }
  ],
  "option_vote_total": 16,
  "total_votes": 18,
  "total_voters": 16,
  "multiple": false,
  "closed": false,
  "close_at": "原始结束时间或 None",
  "has_images": false
}
```

`percentage` 是插件计算的投票占比，单位是百分比，可以当显示宽度用

```jinja
<div class="poll-bar">
  <i style="width: {{ '%.2f'|format(option.percentage) }}%"></i>
</div>
```

`has_images` 表示是否有任一选项带图片，可用于切换为图片投票布局

没有有效票数时，`percentage` 为 `0.0`，`total_votes`、`total_voters` 和 `close_at` 可能为 `None`

### 未知类型

为了让主题在插件增加新内容类型后仍能尽量显示，模板无法识别的对象会整理为

```js
{
  "type": "unknown",
  "text": "对象的字符串表示"
}
```

模板可以在最后提供通用文本回退

```jinja
{% elif item.type == "unknown" %}
  <p>{{ item.text }}</p>
{% endif %}
```

或者更通用的 `else`

```jinja
{% else %}
  <p>Unknown type {{ item.type }}</p>
{% endif %}
```

## 评论和转发

`post.comments` 中的每条评论结构如下：

```js
{
  "author": { ... },
  "content": [ ... ],
  "timestamp": 1710000000 | None,
  "formatted_datetime": "2024-03-09 12:00:00",
  "stats": { ... },
  "replies": [ ... ],
  "parent_author": { ... } | None
}
```

评论和回复的 `content` 与 `post.content` 类型相同

评论回复会递归嵌套，主题应限制展示层数或数量，避免极端数据造成过长图片

`post.repost` 也是一份完整的帖子对象，内部还可能继续包含 `repost`，不过不建议再渲染内部的 `repost`

建议为转发内容使用较紧凑的样式，并对空值进行判断

## 音乐主题

音乐的歌词位于 `post.content`

```js
{
  "type": "text",
  "text": "[00:01.00]歌词内容"
}
```

音乐封面也在 `post.content` 中，通常是第一个 `type="cover"` 的内容项,因此音乐模板可以和普通模板一样遍历 `content`，再对 `cover` 做特殊布局

```jinja
{% set cover = none %}
{% for item in post.content %}
  {% if item.type == "cover" and cover is none %}
    {% set cover = item %}
  {% endif %}
{% endfor %}

{% if cover %}
  <img src="{{ cover.src }}" alt="{{ cover.alt }}" class="album-cover" />
{% endif %}
```

歌曲名、专辑、歌手等平台特有信息可能位于 `post.title`、`post.author` 或 `post.extra`中，不能把某个平台的扩展字段当作所有音乐平台都拥有的字段

## CSS、静态资源和图标

### 主题自己的 CSS

模板中的相对路径以当前模板所在的主题目录为基准：

```html
<link rel="stylesheet" href="这是.css" /> <img src="assets/rf.png" alt="" />
```

自定义主题应尽量把自己的 CSS 和图片放在主题包内，不要依赖插件仓库中的绝对路径。模板被回退到内置主题时，静态资源相对路径也会相应从内置模板目录解析

### 内置图标 CSS

插件每次渲染都会把内置 `icon.css` 注入 HTML，作为所有主题都可使用的图标兜底。主题即使没有自己的图标样式，也可以使用

```html
<i class="fa-icon fa-heart"></i> <i class="fa-icon fa-comment-dots"></i>
```

如果主题需要覆盖图标颜色或图标定义，可以在css里写自己的图标并在模板中引用

```html
<link rel="stylesheet" href="sooo_many_icon.css" />
```

内置图标 CSS 仍然会被加载，逆可以利用 CSS 的后定义规则覆盖它

内置类包括

```text
fa-eye
fa-heart
fa-comment-dots
fa-star
fa-share-nodes
fa-play
fa-music
fa-wand-magic-sparkles
live-icon
...
```

具体可以查看源码 `src\nonebot_plugin_parser_lite\render\templates\icon.css`

### 深浅色主题

渲染时 `data.theme` 是 `light` 或 `dark`

主题可以自己注入这个变量，然后通过css改变颜色

```html
<html data-theme="{{ data.theme }}"></html>
```

```css
:root {
  --bg: #ffffff;
  --text: #202020;
}
[data-theme="dark"] {
  --bg: #171717;
  --text: #f5f5f5;
}
body {
  color: var(--text);
  background: var(--bg);
}
```

插件会根据时间和配置选择当前色彩模式，主题不需要自己判断时间

## 媒体尺寸建议

媒体资源的 URI 已经由插件准备好，但尺寸策略由主题决定。设计时建议：

- 普通图片保留比例，使用 `height: auto`
- 网格图片可以使用 `object-fit: cover`，因为网格本身就可以是裁切布局
- 单图或评论图片如果不希望裁切，使用 `object-fit: contain`
- 文字设置 `white-space: pre-wrap`，否则歌词和多行正文会挤成一行
- 给图片、头像、二维码设置稳定的宽度或最大尺寸，避免资源加载后卡片布局跳动
- 不要给整个 `main` 设置固定高度，帖子内容、评论和歌词会使页面自然变长

内置主题对评论中的单图会在图片加载完成后根据原始宽高比处理

- 高图限制宽度并自动延伸高度
- 横图限制高度并自动计算宽度

主题可以采用自己的策略，但应避免在图片还没加载时用 `offsetHeight` 判断比例

## 完整示例和主题库

主题库地址：[sokoko-org/nonebot-plugin-parser-themes](https://github.com/sokoko-org/nonebot-plugin-parser-themes)

`pink-cute`,`minimal-mono`,`hatsune-miku`这三个示例主题极其简单，不建议作为生产使用

## 常见问题

### 为什么模板文件存在，却没有生效？

检查以下项目：

- `theme.json` 中的 `id` 是否与 `plite_render_theme` 完全一致
- ID 是否符合小写字母、数字、点、下划线和短横线规则
- `plite_theme_dirs` 是否指向主题目录本身，或包含该主题目录的父目录
- 平台模板文件名是否使用平台 ID，例如 `bilibili.html.jinja`
- 修改主题后是否递增了 `theme.json` 的 `version`

### 为什么自定义主题只有部分平台生效？

主题选择是“平台模板 -> 音乐模板 -> default 模板”的顺序。只写了 `netease.html.jinja` 时，它只影响网易云音乐；其他平台会继续使用当前主题的 `default.html.jinja` 或回退到内置主题

### 为什么显示了空白图片或占位图？

头像、平台图标、必需媒体资源获取失败时，插件会使用内置占位图。链接预览、链接图标和贴纸属于可选资源，失败时可能是 `None`。模板需要分别处理这两种情况

### 为什么使用 `|e` 后文字变成 `&amp;lt;`？

因为模板数据已经在进入 Jinja 前转义一次。当前渲染器关闭了 Jinja 自动转义，主题应直接输出 `{{ value }}`，不要再加 `|e`

### 为什么改了主题但图片没有变化？

渲染结果有缓存。递增 `theme.json` 的 `version` 会改变主题缓存键，使旧图片自然失效。开发过程中也可以清理插件的渲染缓存目录

### 可以在主题模板里调用 Python 方法吗？

不可以，因为我没给你传入任何 Python 方法

## 设计建议

- 普通内容、音乐内容和平台专用内容分别有明确的回退关系
- 对 `None`、空数组、未知 `type` 和缺失扩展字段都有展示或隐藏策略
- 正文、评论、回复共用内容项渲染逻辑，避免三套模板逐渐不一致
- 样式和资源都放在主题包内，模板不依赖本机绝对路径
- 主题元数据中有清晰的 `desc`、`author` 和 `version`
- 每次发布模板或 CSS 改动都递增版本号，并准备至少一张渲染结果预览图
