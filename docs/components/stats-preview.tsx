import { asset } from '@/lib/site'

/**
 * 解析统计图示例：随站点明暗主题切换对应的渲染图
 * 图片由插件内置 stats.html.jinja 使用示例数据渲染
 */
export function StatsPreview() {
  const img = 'w-full rounded-xl border shadow-sm'
  return (
    <figure className="not-prose mx-auto my-6 max-w-md">
      <a href={asset('/showcase/stats-light.webp')} target="_blank" rel="noreferrer" className="block dark:hidden">
        <img src={asset('/showcase/stats-light.webp')} alt="全局解析统计（浅色）" className={img} />
      </a>
      <a href={asset('/showcase/stats-dark.webp')} target="_blank" rel="noreferrer" className="hidden dark:block">
        <img src={asset('/showcase/stats-dark.webp')} alt="全局解析统计（深色）" className={img} />
      </a>
      <figcaption className="mt-2 text-center text-xs text-fd-muted-foreground">
        内置主题渲染的「全局解析统计 30」，数据为示例；浅色 / 深色随时间自动切换
      </figcaption>
    </figure>
  )
}
