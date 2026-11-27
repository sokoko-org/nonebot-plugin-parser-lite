'use client'

import Link from 'next/link'
import { useRef } from 'react'

import { Logo } from '@/components/logo'

import { lerp, segment, useReducedMotion, useScrollProgress } from './use-scroll'

const cards = [
  { cn: '多平台', en: 'PLATFORMS', center: 'B站 · 抖音\n小红书 · 微博\n+ 28', bg: '#D3F5F1', fg: '#0F5A54' },
  { cn: '零指令', en: 'ZERO COMMAND', center: '发链接\n就解析', bg: '#FFE1EA', fg: '#8A1D45' },
  { cn: '评论区', en: 'COMMENTS', center: '热评\n楼中楼', bg: '#E4F7E9', fg: '#24603A' },
  { cn: '富文本', en: 'RICH CONTENT', center: '贴纸 · 投票\nLive Photo', bg: '#C9EEEA', fg: '#0D4F4A' },
  { cn: '发送组合', en: 'DELIVERY', center: '合并转发\n懒下载', bg: '#FDE8F0', fg: '#7E2148' },
  { cn: '渲染主题', en: 'THEMES', center: 'Jinja2\n+ CSS', bg: '#DCF3F6', fg: '#145660' },
  { cn: '解析统计', en: 'ANALYTICS', center: '趋势\n与排行', bg: '#EEF6E1', fg: '#3F5A1F' },
  { cn: '独立版', en: 'STANDALONE', center: '不止\nNoneBot', bg: '#E2EDEC', fg: '#1F3F3C' }
]

/** 展开后的倾斜角度 / 飞出时的倾斜角度 */
const tilt = [-9, -17, -4, 3, 7, 12, -11, 6]
const flyTilt = [-42, -55, -30, 28, 40, -26, 46, -38]

// 区段内的时间轴（单位：屏高 svh）
const ENTER = 50
const FLIP_AT = 75
const FLY_START = 110
const FLY_EACH = 45
const TOTAL = FLY_START + cards.length * FLY_EACH + 60

/** 一叠功能卡片：滚动进场 → 弹性翻面散开 → 依次飞走 → 浮出行动按钮 */
export function FeatureDeck() {
  const ref = useRef<HTMLElement>(null)
  const reduced = useReducedMotion()
  const p = useScrollProgress(ref)

  if (reduced) return <StaticGrid />

  const s = p * TOTAL
  const enter = segment(s, 0, ENTER)
  const flipped = s >= FLIP_AT
  const ctaIn = segment(s, FLY_START + (cards.length - 1) * FLY_EACH, FLY_START + cards.length * FLY_EACH)

  return (
    <section ref={ref} className="relative" style={{ height: `${TOTAL + 100}svh` }}>
      <div className="sticky top-0 h-svh overflow-hidden [perspective:1600px]">
        <p className="absolute inset-x-0 top-24 text-center font-mono text-xs tracking-[0.3em] text-fd-muted-foreground">
          FEATURES · {String(cards.length).padStart(2, '0')}
        </p>

        {cards.map((card, i) => {
          const fly = segment(s, FLY_START + i * FLY_EACH, FLY_START + (i + 1) * FLY_EACH)
          const y = lerp(70, 0, enter) * 1 // vh
          return (
            <div
              key={card.en}
              className="absolute top-1/2 left-1/2"
              style={{
                width: 'clamp(240px, 26vw, 340px)',
                aspectRatio: '4 / 5',
                zIndex: cards.length - i,
                transform: `translate(-50%, calc(-50% + ${y}vh + ${-fly * 130}vh)) rotate(${fly * (flyTilt[i] - tilt[i])}deg)`
              }}
            >
              <div
                className="ease-elastic relative size-full transition-transform duration-[1400ms] [transform-style:preserve-3d]"
                style={{
                  transform: `rotateZ(${flipped ? tilt[i] : 0}deg) rotateY(${flipped ? 180 : 0}deg)`,
                  transitionDelay: `${flipped ? i * 40 : 0}ms`
                }}
              >
                {/* 正面：牌背 */}
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 rounded-3xl border border-white/10 bg-[radial-gradient(circle_at_30%_20%,#1d5652,#0b1716_70%)] text-white shadow-2xl [backface-visibility:hidden]">
                  <Corner />
                  <Logo className="size-14" />
                  <p className="font-mono text-xs tracking-[0.35em] text-white/60">PARSER LITE</p>
                  <p className="text-sm text-white/80">继续滚动，翻开看看</p>
                </div>
                {/* 背面：功能 */}
                <div
                  className="absolute inset-0 flex flex-col justify-between rounded-3xl p-6 shadow-2xl [backface-visibility:hidden] [transform:rotateY(180deg)]"
                  style={{ background: card.bg, color: card.fg }}
                >
                  <div className="flex items-start justify-between font-mono">
                    <span className="text-sm tracking-widest">{card.cn}</span>
                    <span className="text-2xl font-bold">{String(i + 1).padStart(2, '0')}</span>
                  </div>
                  <p className="text-center text-[clamp(26px,2.6vw,38px)] leading-tight font-bold whitespace-pre-line">
                    {card.center}
                  </p>
                  <div className="flex items-end justify-between font-mono">
                    <span className="text-2xl font-bold">{String(i + 1).padStart(2, '0')}</span>
                    <span className="text-xs tracking-wider">{card.en}</span>
                  </div>
                </div>
              </div>
            </div>
          )
        })}

        {/* 行动按钮 */}
        <div
          className="absolute inset-0 z-20 flex items-center justify-center px-6"
          style={{
            opacity: ctaIn,
            transform: `translateY(${lerp(60, 0, ctaIn)}vh)`,
            pointerEvents: ctaIn > 0.9 ? 'auto' : 'none'
          }}
        >
          <CTA />
        </div>
      </div>
    </section>
  )
}

function Corner() {
  return (
    <>
      {['top-5 left-5', 'top-5 right-5', 'bottom-5 left-5', 'bottom-5 right-5'].map((pos) => (
        <span key={pos} className={`absolute ${pos} size-2 rotate-45 bg-white/30`} />
      ))}
    </>
  )
}

function CTA() {
  return (
    <div className="max-w-xl text-center">
      <h2 className="text-3xl font-bold tracking-tight md:text-4xl">让群聊里的每一条链接都好看起来</h2>
      <p className="mt-4 text-fd-muted-foreground">安装插件，在 NoneBot 中加载，然后发一条链接。所有配置都有默认值。</p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link
          href="/docs/guide/quick-start"
          className="rounded-full bg-fd-primary px-6 py-3 font-medium text-fd-primary-foreground transition hover:opacity-90"
        >
          快速开始
        </Link>
        <Link href="/docs" className="rounded-full border bg-fd-card px-6 py-3 font-medium transition hover:bg-fd-accent">
          阅读文档
        </Link>
      </div>
    </div>
  )
}

/** 减少动态效果时的静态版本 */
function StaticGrid() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card, i) => (
          <div key={card.en} className="flex aspect-[4/5] flex-col justify-between rounded-3xl p-6" style={{ background: card.bg, color: card.fg }}>
            <div className="flex justify-between font-mono">
              <span className="text-sm tracking-widest">{card.cn}</span>
              <span className="text-xl font-bold">{String(i + 1).padStart(2, '0')}</span>
            </div>
            <p className="text-center text-2xl leading-tight font-bold whitespace-pre-line">{card.center}</p>
            <span className="text-right font-mono text-xs tracking-wider">{card.en}</span>
          </div>
        ))}
      </div>
      <div className="mt-16">
        <CTA />
      </div>
    </section>
  )
}
