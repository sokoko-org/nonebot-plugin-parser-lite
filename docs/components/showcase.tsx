import { asset } from '@/lib/site'

const items = [
  { src: '/showcase/bilibili.webp', alt: 'B 站视频解析效果', label: 'B 站视频 · 评论区' },
  { src: '/showcase/rednote.webp', alt: '小红书笔记解析效果', label: '小红书笔记 · 楼中楼' }
]

/** 渲染效果预览：裁切顶部，点击查看原图 */
export function Showcase() {
  return (
    <div className="not-prose my-6 grid gap-4 sm:grid-cols-2">
      {items.map((item) => (
        <a
          key={item.src}
          href={asset(item.src)}
          target="_blank"
          rel="noreferrer"
          className="group overflow-hidden rounded-xl border bg-fd-card"
        >
          <img
            src={asset(item.src)}
            alt={item.alt}
            className="h-80 w-full object-cover object-top transition duration-300 group-hover:scale-[1.02]"
          />
          <span className="block border-t px-3 py-2 text-xs text-fd-muted-foreground">{item.label} · 点击查看完整卡片</span>
        </a>
      ))}
    </div>
  )
}
