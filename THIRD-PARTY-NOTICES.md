# 第三方许可与来源声明

本项目代码采用 **AGPL-3.0-only**，全文见 [LICENSE](LICENSE)。以下第三方内容保留各自授权；本声明同时适用于 standalone 版本

## 代码与渲染资源

本地路径均相对于 `src/nonebot_plugin_parser_lite/`

| 来源                                                                                                                                                                     | 本地内容及修改                                                                                            | 原许可与署名                                                                                      |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| [fllesser/nonebot-plugin-parser](https://github.com/fllesser/nonebot-plugin-parser)、[LoCCai/nonebot-plugin-parser-m](https://github.com/LoCCai/nonebot-plugin-parser-m) | 原始项目及基础分支，经过重构和扩展                                                                        | MIT；Copyright (c) 2024 Les Freire                                                                |
| [YueHen14/skyland-auto-sign](https://github.com/YueHen14/skyland-auto-sign/blob/72b627a72c83250551115f7453ff226f972dec2d/SecuritySm.py)                                  | `parsers/heybox/sm.py`，修改配置和逻辑以适配小黑盒                                                        | MIT；Copyright (c) 2023 xxyz30                                                                    |
| [zly2006/zhihu-plus-plus](https://github.com/zly2006/zhihu-plus-plus/tree/master/rs-zse-sign)                                                                            | `parsers/zhihu/sign.py`，将签名算法移植为 Python 并适配请求调用                                           | AGPL-3.0-only；Copyright (C) 2024–2026 zly2006 <i@zly2006.me>                                     |
| [006lp/nonebot-plugin-kuwo](https://github.com/006lp/nonebot-plugin-kuwo/blob/47dfa17424d6685588ca6bd403771ac3880b01e6/src/qmc.rs)                                       | `parsers/qqmusic/qmc.rs`，选取并修改 QMC 实现，裁剪未使用代码、调整扩展接口和文件读写，加入 FLAC 尾部清理 | [GNU AGPL v3](https://github.com/006lp/nonebot-plugin-kuwo/blob/main/LICENSE)；006lp 及相关贡献者 |
| [Tailwind CSS v4.2.2](https://github.com/tailwindlabs/tailwindcss/tree/v4.2.2)                                                                                           | `render/templates/tailwind.css`，随模板发布的生成 CSS                                                     | MIT；Copyright (c) Tailwind Labs, Inc.                                                            |
| [Font Awesome Free](https://fontawesome.com/)                                                                                                                            | `render/templates/icon.css` 中的 SVG，嵌入 CSS mask 并调整尺寸、颜色和布局；保留图标内版本及署名          | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)；Copyright 2026 Fonticons, Inc.         |

MIT 许可原文及本项目此前的 MIT 版权声明（2025 molanp、2024 Les Freire）保留在 [LICENSES/MIT.txt](LICENSES/MIT.txt)，此前按 MIT 授予的权利继续有效。AGPL 全文见 [LICENSE](LICENSE)

Font Awesome 使用的是 SVG 图标，适用 [CC BY 4.0 法律文本](https://creativecommons.org/licenses/by/4.0/legalcode)；字体的 SIL OFL 许可不适用于这些 SVG。品牌商标归各自权利人所有

## Bilibili Protobuf

- 社区来源：[bilibili-API-collect](https://sessionhu.github.io/bilibili-API-collect/)，SocialSisterYi 及社区贡献者整理
- 获取渠道：[bilimiao2 的 proto 目录](https://github.com/10miaomiao/bilimiao2/tree/master/bilimiao-grpc/proto/src/main/proto)
- 本地范围：`utils/bilibili/bilibili/` 下的协议定义及生成的 Python 绑定
- 来源文档项目声明采用 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)，全文见 [LICENSES/CC-BY-NC-4.0.txt](LICENSES/CC-BY-NC-4.0.txt)
