<div align="center">
<a href="https://v2.nonebot.dev/store">
    <img src="https://raw.githubusercontent.com/fllesser/nonebot-plugin-template/refs/heads/resource/.docs/NoneBotPlugin.svg" width="310" alt="logo">
</a>

## ✨ [Nonebot2](https://github.com/nonebot/nonebot2) 链接分享自动解析插件 ✨

</div>

## 📖 介绍

| 平台       | 触发的消息形态                    | 视频           | 图集          | 音频 |
| ---------- | --------------------------------- | -------------- | ------------- | ---- |
| B 站       | av 号/BV 号/链接/短链/卡片/小程序 | ✅​            | ✅​           | ✅​  |
| 抖音       | 链接(分享链接，兼容电脑端链接)    | ✅​            | ✅​           | -    |
| 微博       | 链接(博文，视频，show, 文章)      | ✅​            | ✅​           | -    |
| 小红书     | 链接(含短链)/卡片                 | ✅​            | ✅​           | -    |
| 快手       | 链接(包含标准链接和短链)          | ✅​            | ✅​           | -    |
| acfun      | 链接                              | ✅​            | -             | -    |
| X          | 链接                              | ✅​            | ✅​           | -    |
| 酷狗音乐   | 链接(分享链接，歌曲链接)          | -              | -             | ✅​  |
| 网易云音乐 | 链接(分享链接，短链接)            | -              | -             | ✅​  |
| 汽水音乐   | 链接(分享链接)                    | -              | -             | ✅​  |
| 酷我音乐   | 链接(分享链接)                    | -              | -             | ✅​  |
| QQ音乐     | 链接(分享链接)                    | -              | -             | ✅​  |
| 百度贴吧   | 链接                              | 没写           | ✅​(图文帖子) | -    |
| TapTap     | 链接(游戏详情、帖子链接)          | ✅             | ✅            | -    |
| 今日头条   | 链接(视频链接)                    | ✅             | -             | -    |
| 知乎       | 链接                              | ❌(解密不出来) | ✅            | ✅   |
| 堆糖       | 链接                              | ❌️(没遇到过)   | ✅            | -    |
| 小黑盒     | 链接                              | ✅             | ✅            | -    |

支持的链接，可参考 [测试链接](https://github.com/fllesser/nonebot-plugin-parser/blob/master/tests/others/test_urls.md)

## 💿 安装

把`src/nonebot_plugin_parser`文件夹复制到插件加载目录(比如`plugins`)

## 🎈 特性

- 评论区渲染支持
- 通用的基础模板，便于拓展自定义
- 富文本内容渲染支持

## TODO

- [ ] 把所有网络请求换成 `curl_cffi`

## ⚙️ 配置

<details>
<summary>配置项</summary>

```bash
# [可选] nonebot2 内置配置，若服务器上传带宽太低，建议调高，防止超时
API_TIMEOUT=30.0

# [可选] B 站 cookie, 必须含有 SESSDATA 项，可附加 B 站 AI 总结功能
# 如果需要长期使用此凭据则不应该在浏览器登录账户导致 cookie 被刷新，建议注册个小号获取
# 各项获取方式 https://nemo2011.github.io/bilibili-api/#/get-credential
# ac_time_value 相对特殊，仅用于刷新 Cookies
# B站网页打开开发者工具，进入控制台，输入 window.localStorage.ac_time_value 即可获取其值。
parser_bili_ck="SESSDATA=xxxxxxxxxx;ac_time_value=131231241231241"

# [可选] 允许的 B 站视频编码，越靠前的编码优先级越高
# 可选 "avc"(H.264，体积较大), "hev"(HEVC), "av01"(AV1)
# 后两项在不同设备可能有兼容性问题，如需完全避免，可只填一项，如 '["avc"]'
parser_bili_video_codes=["avc", "av01", "hev"]

# [可选] B 站视频清晰度
# 360p(16), 480p(32), 720p(64), 1080p(80), 1080p+(112), 1080p_60(116), 4k(120)
parser_bili_video_quality=80

# [可选] 小红书 Cookie, 部分链接无法解析，可填
parser_xhs_ck=""

# [可选] 代理, 仅作用于 tiktok 解析
# 推特解析会自动读取环境变量中的 http_proxy / https_proxy(代理软件通常会自动设置)
parser_proxy=None

# [可选] 音频解析，是否需要上传群文件
parser_need_upload=False

# [可选] 视频，图片，音频是否使用 base64 发送
# 注意：编解码和传输 base64 会占用更多的内存,性能和带宽, 甚至可能会使 websocket 连接崩溃
# 因此该配置项仅推荐 nonebot 和 协议端不在同一机器的用户配置
parser_use_base64=False

# [可选] 视频最大解析时长，单位：秒
parser_duration_maximum=480

# [可选] 音视频下载最大文件大小，单位 MB，超过该配置将阻断下载
parser_max_size=90

# [可选] 全局禁止的解析
# 示例 parser_disabled_platforms=["bilibili", "douyin"] 表示禁止了哔哩哔哩和抖音
# 可选值: ["bilibili", "douyin", "kuaishou", "x", "acfun", "weibo", "rednote"]
parser_disabled_platforms=["x"]

# [可选] 是否在解析结果中附加原始URL
parser_append_url=False

# [可选] 是否需要转发媒体内容(超过 4 项时始终使用合并转发)
parser_need_forward_contents=True

# [可选] 是否延迟发送视频/音频，需要用户发送特定表情或点赞特定表情后才发送
parser_delay_send_media=False

# [可选] 触发延迟发送视频的表情ID列表，用于监听group_msg_emoji_like事件
parser_delay_send_emoji_ids=[128077]

# [可选] 是否开启懒下载模式，仅在用户请求时才下载视频
parser_delay_send_lazy_download=False

# [可选] 图片反代,用于解决可能的403和外网访问问题
# (例如,https://image.baidu.com/search/down?url=)
# 可以用于不使用魔法下载推特图片(bushi
parser_pic_proxy=
```

</details>

## 🎉 使用

|   指令   |         权限          | 需要@ | 范围 |       说明        |
| :------: | :-------------------: | :---: | :--: | :---------------: |
| 开启解析 | SUPERUSER/OWNER/ADMIN |  是   | 群聊 |     开启解析      |
| 关闭解析 | SUPERUSER/OWNER/ADMIN |  是   | 群聊 |     关闭解析      |
|    bm    |           -           |  否   | 群聊 |   下载 B 站音频   |
|  blogin  |       SUPERUSER       |  否   | 私聊 | 扫码获取 B 站凭证 |

## 🎉 致谢

- [nonebot-plugin-resolver](https://github.com/zhiyu1998/nonebot-plugin-resolver) 本插件的上游的上游的上游
- [nonebot-plugin-parser](https://github.com/fllesser/nonebot-plugin-parser) 本插件的上游的上游(时不时从此版本同步一些功能)
- [nonebot-plugin-parser-m](https://github.com/LoCCai/nonebot-plugin-parser-m) 本插件的上游(由此版本修改)
- [parse-video-py](https://github.com/wujunwei928/parse-video-py) Python短视频去水印爬虫
- [Spider_XHS](https://github.com/cv-cat/Spider_XHS) 小红书爬虫数据采集，小红书全域运营解决方案
- [aiotieba](https://github.com/lumina37/aiotieba) 贴吧接口合集✨可用于工具箱/吧务管理/数据采集
- [xhs](https://github.com/ReaJason/xhs) 基于小红书 Web 端进行的请求封装。
- [xhshow](https://github.com/Cloxl/xhshow) 小红书xs纯算 小红书x-s x-s-common xsc 等字段 纯算逆向
- 神通广大的群友们
