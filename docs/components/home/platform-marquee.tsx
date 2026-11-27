import { allPlatforms } from '@/lib/platforms'

function Row({ reverse = false }: { reverse?: boolean }) {
  const items = reverse ? [...allPlatforms].reverse() : allPlatforms
  return (
    <div className="marquee-row flex w-max gap-3" data-reverse={reverse || undefined}>
      {[...items, ...items].map((p, i) => (
        <span
          key={`${p.id}-${i}`}
          aria-hidden={i >= items.length}
          className="inline-flex items-center gap-2 rounded-full border bg-fd-card px-4 py-1.5 text-sm whitespace-nowrap"
        >
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          {p.name}
        </span>
      ))}
    </div>
  )
}

/** 两行反向无限滚动的平台跑马灯，悬停暂停 */
export function PlatformMarquee() {
  return (
    <div className="marquee group flex flex-col gap-3 overflow-hidden py-2">
      <Row />
      <Row reverse />
    </div>
  )
}
