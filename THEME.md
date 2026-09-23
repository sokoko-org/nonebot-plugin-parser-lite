# 渲染主题

渲染主题从解析器模型中解耦。主题模板只接收 `Theme API v1` 数据，不应调用 Python 对象方法、依赖内容类名，或自行下载资源。

## 安装目录

插件会按以下顺序查找主题，前面的主题优先：

1. `plite_theme_dirs` 中配置的目录
2. 插件数据目录下的 `themes`
3. 包内的 `render/templates`

配置目录既可以直接指向一个主题，也可以指向包含多个主题子目录的目录。例如：

```text
<plugin-data>/themes/
└── paper/
    ├── theme.json
    ├── default.html.jinja
    ├── music.html.jinja
    ├── netease.html.jinja
    ├── ....jinja
    └── anyname.css
```

主题清单：

```json
{
  "schema_version": 1,
  "id": "paper",
  "name": "Paper",
  "desc": "简洁的纸张风格",
  "author": "主题作者",
  "version": "1.0.0"
}
```

`id` 只能使用小写字母、数字、点、下划线和短横线。模板按以下顺序选择：

1. 平台对应的 `<platform>.html.jinja`；
2. 如果是音乐平台，再选择 `music.html.jinja`；
3. 最后选择主题目录内的 `default.html.jinja`。

主题目录没有可用的默认模板时，会回退到内置主题的 `default.html.jinja`

渲染器会始终把内置 `icon.css` 注入页面，并放在主题自定义样式之前。主题可以提供自己的 `icon.css` 覆盖内置图标样式；缺少自定义文件时仍可使用内置图标。

安装后配置：

```bash
plite_render_theme="paper"
plite_theme_dirs=[]
```

主题模板是 Jinja/HTML。插件只加载上述本地目录中的主题文件，不负责联网下载或维护主题。

## Theme API v1

模板上下文只有一个根对象 `data`：

```text
data.schema_version   = 1
data.theme            = "light" | "dark"
data.theme_id         = 当前主题 ID
data.meta              = { bot_name, rendering_time, width }
data.post              = 帖子数据
```

传给模板的字符串已经在数据层统一按 HTML 转义，主题模板不需要也不应该再次使用 `|e`。渲染环境关闭 Jinja 自动转义，以便模板宏可以组合 HTML 片段。

`data.post`、`author`、`platform`、`stats`、`comments` 和 `repost` 都只包含字典、列表、标量和 `None`。头像、平台图标及媒体封面已经解析为可直接放入 `img` 的 URI；资源不可用时会使用占位图，非必需资源为 `None`。

内容项使用 `type` 区分：

| `type`       | 主要字段                                                                |
| ------------ | ----------------------------------------------------------------------- |
| `text`       | `text`                                                                  |
| `image`      | `src`, `layout`, `is_live`                                              |
| `cover`      | `src`, `alt`, `layout`                                                  |
| `live_photo` | `src`, `layout`, `is_live`                                              |
| `graphic`    | `src`, `alt`                                                            |
| `sticker`    | `src`, `size`, `description`                                            |
| `video`      | `src`, `duration`, `size`, `source_url`                                 |
| `audio`      | `duration`, `size`, `source_url`                                        |
| `link`       | `url`, `title`, `site_name`, `description`, `icon`, `preview`           |
| `quote`      | `text`, `title`, `url`, `icon`                                          |
| `poll`       | `title`, `options`, `total_votes`, `total_voters`, `multiple`, `closed` |

投票 `options` 中的每项包含 `text`、`votes` 和已经计算好的 `percentage`。统计数据的固定字段为 `view_count`、`like_count`、`collect_count`、`share_count`、`comment_count`，额外统计位于 `stats.extra` 列表中，每项包含 `key`、`label`、`value`。

音乐解析器中的歌词会作为普通字符串内容提供，序列化后对应 `type="text"`；音乐封面会作为 `type="cover"` 内容项提供。

内置主题可以作为第三方主题的起点；但复制后应更新 `theme.json` 中的 `id` 和 `version`。版本号会参与渲染缓存键，主题更新时递增即可让旧图片自然失效。
