export const site = {
  name: 'nonebot-plugin-parser-lite',
  shortName: 'Parser Lite',
  description: 'NoneBot2 通用媒体链接分享解析插件',
  url: 'https://parser-docs.sokoko.org',
  repo: 'https://github.com/sokoko-org/nonebot-plugin-parser-lite',
  themesRepo: 'https://github.com/sokoko-org/nonebot-plugin-parser-themes'
}

/** public 目录资源路径（站点部署在域名根路径，原样返回；保留此函数便于将来迁移到子路径） */
export function asset(path: string) {
  return path
}
