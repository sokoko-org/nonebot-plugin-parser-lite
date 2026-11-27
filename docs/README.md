# nonebot-plugin-parser-lite 文档站

线上地址：<https://parser-docs.sokoko.org>

基于 [Next.js](https://nextjs.org) + [Fumadocs](https://fumadocs.dev)，静态导出后部署在 Vercel。

```bash
cd docs
npm install
npm run dev      # http://localhost:5175
npm run build    # 静态导出到 out/
```

## 目录

| 路径 | 说明 |
| :--- | :--- |
| `content/docs/` | 文档正文（MDX），侧边栏顺序由各目录的 `meta.json` 决定 |
| `app/(home)/page.tsx` | 首页 |
| `lib/platforms.ts` | 平台支持矩阵，首页与「支持的平台」页共用，新增平台时改这里 |
| `lib/site.ts` | 站点名称、域名、仓库地址 |
| `lib/i18n.ts` | Fumadocs 界面文案的中文翻译 |
| `public/showcase/` | 渲染效果示例图 |

## 部署（Vercel）

1. Vercel 导入本仓库，**Root Directory** 设为 `docs`，其余保持默认（构建配置见 `vercel.json`）
2. 项目 **Settings → Domains** 添加 `parser-docs.sokoko.org`，按提示在 DNS 中添加 CNAME 记录
3. 之后推送即自动部署；`docs/` 目录没有变化的提交会被 `ignoreCommand` 跳过，不消耗构建次数

更换域名时同步修改 `lib/site.ts` 中的 `url` 与仓库根目录 README 中的链接。

依赖安装固定走 npm 官方源（见 `.npmrc`），本地如需镜像可执行 `npm install --registry=https://registry.npmmirror.com`，但不要提交被改写的 `package-lock.json`。
