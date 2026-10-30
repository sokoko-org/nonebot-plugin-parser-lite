# 第三方许可与来源声明

本项目自身代码采用 **MIT**，全文见 [LICENSE](LICENSE)。以下第三方内容保留各自授权；本声明同时适用于 standalone 版本

## 代码与渲染资源

本地路径均相对于 `src/nonebot_plugin_parser_lite/`

| 来源                                                                                                                                                                     | 本地内容及修改                                                                                   | 原许可与署名                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| [fllesser/nonebot-plugin-parser](https://github.com/fllesser/nonebot-plugin-parser)、[LoCCai/nonebot-plugin-parser-m](https://github.com/LoCCai/nonebot-plugin-parser-m) | 原始项目及基础分支，经过重构和扩展                                                               | MIT；Copyright (c) 2024 Les Freire                                                        |
| [YueHen14/skyland-auto-sign](https://github.com/YueHen14/skyland-auto-sign/blob/72b627a72c83250551115f7453ff226f972dec2d/SecuritySm.py)                                  | `parsers/heybox/sm.py`，修改配置和逻辑以适配小黑盒                                               | MIT；Copyright (c) 2023 xxyz30                                                            |
| [UnlockMusicProject/lib_um_crypto_rust](https://git.unlock-music.dev/um/lib_um_crypto_rust/src/commit/562ea1dc8a843d5eb32299dac14fb7b74587c4cd/um_crypto/qmc)            | `parsers/qqmusic/qmc.rs` 的 QMC 算法实现                                                         | Apache-2.0 / MIT 双许可，本项目选择 MIT；Copyright (c) 2024 Project Unlock Music          |
| [Tailwind CSS v4.2.2](https://github.com/tailwindlabs/tailwindcss/tree/v4.2.2)                                                                                           | `render/templates/tailwind.css`，随模板发布的生成 CSS                                            | MIT；Copyright (c) Tailwind Labs, Inc.                                                    |
| [Font Awesome Free](https://fontawesome.com/)                                                                                                                            | `render/templates/icon.css` 中的 SVG，嵌入 CSS mask 并调整尺寸、颜色和布局；保留图标内版本及署名 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)；Copyright 2026 Fonticons, Inc. |

Font Awesome 使用的是 SVG 图标，适用 [CC BY 4.0 法律文本](https://creativecommons.org/licenses/by/4.0/legalcode)；字体的 SIL OFL 许可不适用于这些 SVG。品牌商标归各自权利人所有

## Bilibili Protobuf

- 社区来源：[bilibili-API-collect](https://sessionhu.github.io/bilibili-API-collect/)，SocialSisterYi 及社区贡献者整理
- 本地范围：`utils/bilibili/bilibili/` 下的协议定义及生成的 Python 绑定
- 来源文档项目声明采用 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)，全文见 [CC BY-NC 4.0 法律文本](https://creativecommons.org/licenses/by-nc/4.0/legalcode)

## 原生扩展依赖

以下为原生扩展的普通库依赖；条件依赖按目标平台启用，均选择 MIT 许可。

| 组件                                         | 版权署名                                                                          |
| -------------------------------------------- | --------------------------------------------------------------------------------- |
| `base64` 0.22.1                              | Copyright (c) 2015 Alice Maz                                                      |
| `libc` 0.2.191                               | Copyright (c) The Rust Project Developers                                         |
| `once_cell` 1.21.4、`portable-atomic` 1.15.0 | 上游 MIT 许可文本未列单独版权署名                                                 |
| `pyo3`、`pyo3-ffi` 0.29.3                    | Copyright (c) 2023-present PyO3 Project and Contributors. https://github.com/PyO3 |
| QMC Rust 改写                                | Copyright (c) 2026 006lp                                                          |
