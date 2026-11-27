import Link from 'next/link'

import { ChatDemo } from '@/components/home/chat-demo'
import { FeatureDeck } from '@/components/home/feature-deck'
import { OutlineTitle } from '@/components/home/outline-title'
import { PlatformMarquee } from '@/components/home/platform-marquee'
import { RotatingWord } from '@/components/home/rotating-word'
import { allPlatforms } from '@/lib/platforms'
import { site } from '@/lib/site'

export default function HomePage() {
  return (
    <main className="flex flex-1 flex-col">
      {/* ===== 首屏 ===== */}
      <section className="relative flex min-h-svh flex-col overflow-hidden">
        {/* 背景描边大字 */}
        <div className="pointer-events-none absolute inset-x-0 top-10 opacity-70 dark:opacity-50">
          <OutlineTitle text="PARSER" />
        </div>
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 -top-40 mx-auto h-[520px] max-w-4xl rounded-full opacity-25 blur-3xl dark:opacity-15"
          style={{ background: 'radial-gradient(closest-side, #39c5bb, #f0447f33 65%, transparent)' }}
        />

        <div className="hero-rise relative z-10 flex flex-1 flex-col items-center justify-center px-6 pt-24 pb-10 text-center">
          <p className="mb-6 inline-flex items-center gap-2 rounded-full border bg-fd-card/80 px-3 py-1 text-xs text-fd-muted-foreground backdrop-blur">
            <span className="size-1.5 rounded-full bg-emerald-500" />
            NoneBot2 插件 · 也提供独立版
          </p>
          <h1 className="text-4xl leading-tight font-bold tracking-tight md:text-6xl">
            群友分享的 <RotatingWord />
            <br />
            <span className="brand-gradient-text">直接在群里看</span>
          </h1>
          <p className="mt-6 max-w-2xl text-base text-fd-muted-foreground md:text-lg">
            自动识别 {allPlatforms.length} 个平台的分享链接，把视频、图文、音频与热评渲染成一张卡片，不用跳转也能看完。
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Link
              href="/docs/guide/quick-start"
              className="rounded-full bg-fd-primary px-7 py-3 font-medium text-fd-primary-foreground shadow-lg shadow-fd-primary/25 transition hover:opacity-90"
            >
              快速开始
            </Link>
            <a
              href={site.repo}
              target="_blank"
              rel="noreferrer noopener"
              className="rounded-full border bg-fd-card px-7 py-3 font-medium transition hover:bg-fd-accent"
            >
              GitHub
            </a>
          </div>
          <div className="mt-8 flex flex-wrap justify-center gap-5 text-xs text-fd-muted-foreground">
            <span>✓ MIT 开源</span>
            <span>✓ 零必填配置</span>
            <span>✓ 主题可替换</span>
            <span>✓ 日夜模式</span>
          </div>
        </div>

        <div className="relative z-10 pb-6">
          <PlatformMarquee />
        </div>
        <p className="scroll-hint relative z-10 pb-8 text-center font-mono text-xs tracking-[0.3em] text-fd-muted-foreground">
          SCROLL ↓
        </p>
      </section>

      {/* ===== 滚动演示：群聊里发生了什么 ===== */}
      <ChatDemo />

      {/* ===== 功能卡牌 ===== */}
      <FeatureDeck />

      <footer className="border-t py-10 text-center text-xs text-fd-muted-foreground">
        MIT License · 本项目与所列平台不存在隶属、授权或合作关系
      </footer>
    </main>
  )
}
