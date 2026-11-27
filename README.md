<p align="center">
  <img src="./assets/readme/banner.svg" width="100%" alt="nonebot-plugin-parser-lite：B 站与小红书的实际渲染卡片">
</p>

<p align="center">
  基于 <a href="https://github.com/nonebot/nonebot2">NoneBot2</a> 的多平台链接分享解析插件。<br>
  自动识别分享链接、BV 号与小程序卡片，提取视频、图文、音频与热评，并渲染成适合群聊直接浏览的卡片。
</p>

<p align="center">
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/nonebot/nonebot2"><img src="https://img.shields.io/badge/NoneBot-2-EA5252?style=flat-square" alt="NoneBot2"></a>
  <a href="https://github.com/sokoko-org/nonebot-plugin-parser-lite/actions/workflows/build.yml"><img src="https://img.shields.io/github/actions/workflow/status/sokoko-org/nonebot-plugin-parser-lite/build.yml?branch=main&style=flat-square&logo=github&label=构建" alt="构建状态"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/sokoko-org/nonebot-plugin-parser-lite?style=flat-square&label=许可证" alt="MIT 许可证"></a>
</p>

<p align="center">
  <a href="https://parser-docs.sokoko.org">使用文档</a> ·
  <a href="https://parser-docs.sokoko.org/docs/guide/quick-start/">快速开始</a> ·
  <a href="https://parser-docs.sokoko.org/docs/guide/configuration/">配置说明</a> ·
  <a href="https://parser-docs.sokoko.org/docs/platforms/">支持的平台</a> ·
  <a href="https://github.com/sokoko-org/nonebot-plugin-parser-lite/issues/new/choose">问题反馈</a>
</p>

> [!IMPORTANT]
>
> 严禁将本项目用于任何非法用途。请遵守所在地法律法规、平台服务协议与著作权规则，仅处理你有权下载、保存或传播的内容。
>
> 因使用不当造成的一切责任由使用者承担。本项目与所支持的平台不存在隶属、授权或合作关系。

## 核心能力

> 分享链接、短链、BV / av 号、小程序与分享卡片 → 自动识别 → 媒体解析 → 卡片渲染与发送

- **32 个平台** — B 站、抖音、微博、小红书、知乎、贴吧等内容平台，以及网易云、QQ 音乐等 6 个音乐平台。
- **零指令触发** — 群友发链接即解析，无需复制资源地址或记忆命令。
- **评论区与富文本** — 热评、楼中楼、贴纸、投票、引用与 Live Photo 一并渲染进卡片。
- **灵活的发送方式** — 自由组合卡片 / 正文 / 视频 / 音频，支持合并转发与懒下载。
- **可替换的主题** — Jinja2 + CSS 渲染主题，按时间自动切换日夜模式，见 [主题商店](https://github.com/sokoko-org/nonebot-plugin-parser-themes)。

## 快速开始

需要 Python >= 3.11，可选安装 FFmpeg（Live Photo、B 站音视频合并）。

```shell
uv add git+https://github.com/sokoko-org/nonebot-plugin-parser-lite.git --branch main
```

加载插件后在群里发一条链接即可，所有配置都有默认值。pip 安装、指定版本与手动安装见 [快速开始](https://parser-docs.sokoko.org/docs/guide/quick-start/)；不使用 NoneBot 请看 [独立版](https://parser-docs.sokoko.org/docs/standalone/)。

## 常用指令

- `@机器人 开启解析` / `@机器人 关闭解析` — 开关当前会话的解析。
- `bm <BV号>` — 下载 B 站音频，也可引用一条链接后发送。
- `@机器人 blogin` — 扫码登录 B 站，仅超级用户。
- `@机器人 解析统计` / `@机器人 全局解析统计` — 查看解析趋势与平台排行，[效果预览](https://parser-docs.sokoko.org/docs/features/stats/)。

## 文档与社区

- **使用文档** — [parser-docs.sokoko.org](https://parser-docs.sokoko.org)（源码位于 [`docs/`](docs)）
- **主题开发** — [主题开发指南](https://parser-docs.sokoko.org/docs/themes/)
- **独立版** — [独立版文档](https://parser-docs.sokoko.org/docs/standalone/)（发布在 [`standalone`](https://github.com/sokoko-org/nonebot-plugin-parser-lite/tree/standalone) 分支）
- **交流反馈** — [Discussions](https://github.com/sokoko-org/nonebot-plugin-parser-lite/discussions) · [Issues](https://github.com/sokoko-org/nonebot-plugin-parser-lite/issues/new/choose)

## 致谢

- [fllesser/nonebot-plugin-parser](https://github.com/fllesser/nonebot-plugin-parser) — 原始项目
- [LoCCai/nonebot-plugin-parser-m](https://github.com/LoCCai/nonebot-plugin-parser-m) — 本项目基于此项目开发并大幅重构
- [adrienbrault/blitz-py](https://github.com/adrienbrault/blitz-py) — 高性能高兼容的渲染引擎

以及更多参考项目与贡献者，完整名单见 [致谢与许可](https://parser-docs.sokoko.org/docs/about/credits/)。

<p align="center">
  <a href="https://github.com/sokoko-org/nonebot-plugin-parser-lite/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=sokoko-org/nonebot-plugin-parser-lite" alt="项目贡献者">
  </a>
</p>

## License

本项目代码采用 [MIT](LICENSE) 开源；第三方代码和资源保留各自许可，见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
