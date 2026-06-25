<div align="center">
<a href="https://v2.nonebot.dev/store">
    <img src="https://raw.githubusercontent.com/fllesser/nonebot-plugin-template/refs/heads/resource/.docs/NoneBotPlugin.svg" width="310" alt="logo">

</a>

## ✨ [Nonebot2](https://github.com/nonebot/nonebot2) 链接分享自动解析插件 ✨

[![Code style: djlint](https://img.shields.io/badge/html%20style-djlint-blue.svg)](https://www.djlint.com)

</div>

> [!IMPORTANT]
>
> 严禁将本项目用于任何非法用途
>
> 由于使用不当造成的一切责任由使用者承担，本项目维护者无任何责任

## 📖 支持的平台

| 平台       | 图文/文章/帖子/动态 | 视频 | 音频 | 图集/相册 | 评论区渲染 | Live Photo |
| :--------- | :-----------------: | :--: | :--: | :-------: | :--------: | :--------: |
| B 站       |         ✅          |  ✅  |  ✅  |    ✅     |     ✅     |     ✅     |
| 抖音       |         ✅          |  ✅  |  🚫  |    ✅     | ⛔(仅文章) |     ✅     |
| 微博       |         ✅          |  ✅  |  🚫  |    ✅     |     ✅     |     ✅     |
| 小红书     |         ✅          |  ✅  |  🚫  |    ✅     |     ✅     |     ✅     |
| 快手       |         🚫          |  ✅  |  🚫  |    ❌     |     ✅     |     🚫     |
| AcFun      |         ✅          |  ✅  |  🚫  |    🚫     |     ❌     |     🚫     |
| X          |         ✅          |  ✅  |  🚫  |    ✅     |     ❌     |     🚫     |
| 酷狗音乐   |         🚫          |  🚫  |  ✅  |    🚫     |     🚫     |     🚫     |
| 网易云音乐 |         🚫          |  🚫  |  ✅  |    🚫     |     🚫     |     🚫     |
| 汽水音乐   |         🚫          |  🚫  |  ✅  |    🚫     |     ❌     |     🚫     |
| 酷我音乐   |         🚫          |  🚫  |  ✅  |    🚫     |     ❌     |     🚫     |
| 百度贴吧   |         🚫          |  ❌  |  🚫  |    ✅     |     ✅     |     🚫     |
| 今日头条   |         🚫          |  ✅  |  🚫  |    🚫     |     ❌     |     🚫     |
| 知乎       |         ✅          |  ✅  |  🚫  |    ✅     |     ✅     |     🚫     |
| 堆糖       |         ✅          |  🚫  |  🚫  |    ✅     |     ✅     |     🚫     |
| 小黑盒     |         ✅          |  ✅  |  🚫  |    ✅     |     ✅     |     🚫     |
| ILLU       |         ✅          |  🚫  |  🚫  |    ✅     |     ✅     |     🚫     |
| LOFTER     |         ✅          |  🚫  |  🚫  |    ✅     |     ✅     |     🚫     |
| BUFF       |         ✅          |  ✅  |  🚫  |    ✅     |     ✅     |     🚫     |
| 酷安       |         ✅          |  🚫  |  🚫  |    ✅     |     ✅     |     🚫     |

> 💡 **标识说明**
>
> - `✅` 表示完整支持解析与富文本渲染
> - `❌` 表示插件尚未适配该模块
> - `🚫` 表示该平台暂无此类内容形态(至少我不知道有，如果有，你可以提交issue告诉我)
> - “图文/文章/帖子/动态”列指的文字+图片混排、专栏、问答、动态、show 等文本型内容

支持的链接，可参考 [测试链接](https://github.com/fllesser/nonebot-plugin-parser/blob/master/tests/others/test_urls.md)

## 💿 安装

把`src/nonebot_plugin_parser_lite`文件夹复制到插件加载目录(比如`plugins`)

<details>
<summary>pip</summary>

```shell
pip install -r requirements.txt
```

</details>

<details>
<summary>uv</summary>

```shell
uv add --requirements requirements.txt
```

</details>

## 🎈 特性

- 评论区渲染支持
- 通用的基础模板，便于拓展自定义
- 富文本内容渲染支持

<details>
<summary>渲染效果</summary>

|                                                                            哔哩哔哩                                                                             |                                                                               小红书                                                                                |
| :-------------------------------------------------------------------------------------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------------------------------------------------------------------------------------------: |
| <img width="1240" height="2880" alt="142f794a8df94207bf742c75434c942b" src="https://github.com/user-attachments/assets/7c73228d-bf1c-44e1-96be-adcf9ef32f85" /> | <img width="1240" height="5382" alt="203b2500-2393-53c4-901c-77169489e4ee" src="https://github.com/user-attachments/assets/969290cd-9bb3-4945-8f26-8d6cdeb51f57" /> |

</details>

## ⚙️ 配置

> [!NOTE]
>
> 插件会自动使用系统环境中的http系统代理进行网络请求

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
plite_bili_ck="SESSDATA=xxxxxxxxxx;ac_time_value=131231241231241"

# [可选] 允许的 B 站视频编码，越靠前的编码优先级越高
# 可选 "avc"(H.264，体积较大), "hev"(HEVC), "av01"(AV1), "unknown"(未知)
# 后两项在不同设备可能有兼容性问题，如需完全避免，可只填一项，如 '["avc"]'
plite_bili_video_codes=["avc", "av01", "hev", "unknown"]

# [可选] B 站视频清晰度
# 360p(16), 480p(32), 720p(64), 1080p(80), 1080p+(112), 1080p_60(116), 4k(120)
plite_bili_video_quality=80

# [必填] 快手 Cookie，此cookie无需登录态，首页匿名用户ck即可(只需要确保did字段存在)
plite_ks_ck=""

# [可选] 音频解析，是否需要上传群文件
plite_need_upload_audio=False

# [可选] 视频解析，是否需要上传群文件
plite_need_upload_video=False

# [可选] 视频，图片，音频是否使用 base64 发送
# 注意：编解码和传输 base64 会占用更多的内存,性能和带宽, 甚至可能会使 websocket 连接崩溃
# 因此该配置项仅推荐 nonebot 和 协议端不在同一机器的用户配置
plite_use_base64=False

# [可选] 视频最大解析时长，单位：秒
plite_duration_maximum=480

# [可选] 音视频下载最大文件大小，单位 MB，超过该配置将阻断下载
plite_max_size=90

# [可选] 全局禁止的解析
# 示例 plite_disabled_platforms=["bilibili", "douyin"] 表示禁止了哔哩哔哩和抖音
# 可选值: ["bilibili", "douyin", "kuaishou", "x", "acfun", "weibo", "rednote"]
plite_disabled_platforms=["x"]

# [可选] 黑名单用户列表
# 示例 plite_blacklist=["QQClient_123456"]
plite_blacklist_users=[]

# [可选] 是否在解析结果中附加原始URL
plite_append_url=False

# [可选] 是否在解析结果中添加原始URL二维码
plite_append_qrcode=False

# [可选] 是否需要转发媒体内容(超过 4 项时始终使用合并转发)
plite_need_forward_contents=True

# [可选] 是否开启懒下载模式，仅在用户请求时才下载视频
plite_lazy_download=False

# [可选] 懒下载模式等待命令超时时间
plite_lazy_download_timeout=30

# [可选] 在懒下载模式中用户请求下载视频时的命令列表
plite_download_command=["xz", "下载"]

# [可选] 浏览器程序路径，如果无法识别浏览器请填写此配置
plite_browser_path=""

# [可选] 是否使用 ffmpeg 转码 Live Photo，若设备配置不佳，请禁用此功能
# 禁用后将分别发送 Live Photo 底图和动图部分
plite_live_photo=True

# [可选] 浏览器是否使用无头模式，无头模式有可能会被检测到
plite_headless=False

# [可选] 最大评论数量
plite_max_comments=5

# [可选] 纯文本文本长度阈值，超过此长度的文本将会强制转发
plite_forward_text_threshold=300
```

</details>

## 🎉 使用

|   指令   |          参数           |         权限          | 需要@ | 范围 |       说明        |
| :------: | :---------------------: | :-------------------: | :---: | :--: | :---------------: |
| 开启解析 |            -            | SUPERUSER/OWNER/ADMIN |  是   | 群聊 |     开启解析      |
| 关闭解析 |            -            | SUPERUSER/OWNER/ADMIN |  是   | 群聊 |     关闭解析      |
|    bm    | bv号或引用一个链接/卡片 |           -           |  否   | 群聊 |   下载 B 站音频   |
|  blogin  |            -            |       SUPERUSER       |  是   | 全部 | 扫码获取 B 站凭证 |

## 🎉 致谢

<a href="https://github.com/sokoko-org/nonebot-plugin-parser-lite/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=sokoko-org/nonebot-plugin-parser-lite" />
</a>

- [fllesser/nonebot-plugin-parser](https://github.com/fllesser/nonebot-plugin-parser) 社交媒体分享链接解析插件
- [LoCCai/nonebot-plugin-parser-m](https://github.com/LoCCai/nonebot-plugin-parser-m) 社交媒体分享链接解析插件
- [lumina37/aiotieba](https://github.com/lumina37/aiotieba) 贴吧接口合集✨可用于工具箱/吧务管理/数据采集
- [ikenxuan/karin-plugin-kkk](https://github.com/ikenxuan/karin-plugin-kkk) 给群聊机器人提供视频作品、动态解析和推送功能，并使用 React + Tailwindcss 构建出现代审美设计的信息卡片
- [ikenxuan/amagi](https://github.com/ikenxuan/amagi) 抖音、B站 web 端相关数据接口封装基于 Node.js 的实现
- [zly2006/zhihu-plus-plus](https://github.com/zly2006/zhihu-plus-plus) Zhihu++ | 知乎++: Ad-free, low cost, AI powered zhihu android 3rd-party client. 去广告、占用低、AI大模型的新时代知乎安卓端体验
- [Uesugi Hanako](https://github.com/negichan) 渲染模板设计
- 致2026年的你们
