'use client'

import { useRef } from 'react'

import { asset } from '@/lib/site'

import { lerp, segment, useReducedMotion, useScrollProgress } from './use-scroll'

const steps = [
  { title: '发一条链接', desc: '群友分享 B 站、小红书、微博……任意受支持平台的链接、短链或卡片', at: 0 },
  { title: '自动识别', desc: '无需指令，插件识别后先贴上 🔨 表示正在解析', at: 0.2 },
  { title: '渲染成卡片', desc: '标题、封面、互动数据排进一张图，完成后再贴一个 🍼（失败则贴 ❌）', at: 0.36 },
  { title: '评论区一并送达', desc: '热评、楼中楼直接画进卡片，不用点开也能看到讨论', at: 0.56 }
]

const CARD_W = 248
const CARD_H = Math.round((CARD_W * 1686) / 720)
const CARD_WINDOW = 400

/** 随滚动播放的「群聊里发生了什么」演示，区段固定在视口中 */
export function ChatDemo() {
  const ref = useRef<HTMLElement>(null)
  const reduced = useReducedMotion()
  const raw = useScrollProgress(ref)
  const p = reduced ? 1 : raw

  const linkIn = segment(p, 0.06, 0.16)
  const reacting = p >= 0.2
  const cardIn = segment(p, 0.34, 0.46)
  const done = p >= 0.46
  const cardScroll = segment(p, 0.56, 0.95)
  const active = steps.reduce((acc, s, i) => (p >= s.at ? i : acc), 0)

  return (
    <section ref={ref} className="relative" style={{ height: reduced ? 'auto' : '340svh' }}>
      <div className={`${reduced ? '' : 'sticky top-0 h-svh'} flex items-center overflow-hidden`}>
        <div className="mx-auto grid w-full max-w-6xl items-center gap-10 px-6 py-16 md:grid-cols-[1fr_auto]">
          {/* 步骤说明 */}
          <div>
            <p className="font-mono text-xs tracking-[0.3em] text-fd-muted-foreground">HOW IT WORKS</p>
            <h2 className="mt-3 text-3xl font-bold tracking-tight md:text-4xl">在群里，它是这样工作的</h2>
            <ol className="mt-10 space-y-6">
              {steps.map((step, i) => (
                <li
                  key={step.title}
                  className={`flex gap-4 transition-opacity duration-300 ${i === active ? 'opacity-100' : 'opacity-35'}`}
                >
                  <span
                    className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border font-mono text-sm transition-colors ${
                      i <= active ? 'border-transparent bg-fd-primary text-fd-primary-foreground' : ''
                    }`}
                  >
                    {i + 1}
                  </span>
                  <div>
                    <h3 className="font-semibold">{step.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-fd-muted-foreground">{step.desc}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-10 hidden h-1 w-48 overflow-hidden rounded-full bg-fd-muted md:block">
              <div className="h-full rounded-full bg-fd-primary" style={{ width: `${p * 100}%` }} />
            </div>
          </div>

          {/* 手机里的群聊 */}
          <div className="mx-auto w-[300px] rounded-[2.2rem] border-[6px] border-neutral-800 bg-[#f1f2f6] shadow-2xl dark:border-neutral-700 dark:bg-[#111214]">
            <div className="flex items-center justify-between rounded-t-[1.8rem] border-b border-black/5 bg-white/80 px-4 py-3 text-sm font-semibold text-neutral-800 dark:border-white/5 dark:bg-neutral-900/80 dark:text-neutral-100">
              <span>‹</span>
              <span>摸鱼交流群（128）</span>
              <span>≡</span>
            </div>
            <div className="relative h-[540px] overflow-hidden px-3 pt-3">
              <div
                className="space-y-3"
                style={{ transform: `translateY(${-lerp(0, 150, cardIn)}px)` }}
              >
                <Message name="绒布球" avatar="linear-gradient(135deg, #F5E6D3, #C9A98B)" text="今天有什么好看的" />
                <Message name="三花猫" avatar="linear-gradient(135deg, #FFFFFF 0%, #F7B267 50%, #3A3A3A 100%)" text="稍等我找找" />

                <div style={{ opacity: linkIn, transform: `translateY(${lerp(16, 0, linkIn)}px)` }}>
                  <Message name="三花猫" avatar="linear-gradient(135deg, #FFFFFF 0%, #F7B267 50%, #3A3A3A 100%)" text="https://b23.tv/BV1CtYu6DE11" link>
                    <span className="mt-1 flex gap-1">
                      <Reaction emoji="🔨" show={reacting} />
                      <Reaction emoji="🍼" show={done} />
                    </span>
                  </Message>
                </div>

                <div
                  className="flex gap-2"
                  style={{ opacity: cardIn, transform: `translateY(${lerp(40, 0, cardIn)}px)` }}
                >
                  <span
                    aria-label="复读寄"
                    className="size-8 shrink-0 rounded-full"
                    style={{ background: 'linear-gradient(135deg, #4FD9CF 0%, #39C5BB 50%, #F0447F 100%)' }}
                  />
                  <div>
                    <p className="mb-1 text-[11px] text-neutral-500">复读寄</p>
                    <div
                      className="overflow-hidden rounded-xl shadow-md"
                      style={{ width: CARD_W, height: CARD_WINDOW }}
                    >
                      <img
                        src={asset('/showcase/bilibili.webp')}
                        alt="B 站视频解析卡片"
                        width={CARD_W}
                        height={CARD_H}
                        style={{ transform: `translateY(${-lerp(0, CARD_H - CARD_WINDOW, cardScroll)}px)` }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/** 消息下方的表情回应，回应会累加而不是替换 */
function Reaction({ emoji, show }: { emoji: string; show: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs shadow-sm transition-all duration-300 dark:bg-neutral-800"
      style={{ opacity: show ? 1 : 0, transform: `scale(${show ? 1 : 0.6})` }}
    >
      {emoji} 1
    </span>
  )
}

function Message({
  name,
  avatar,
  text,
  link = false,
  children
}: {
  name: string
  avatar: string
  text: string
  link?: boolean
  children?: React.ReactNode
}) {
  return (
    <div className="flex gap-2">
      <span className="size-8 shrink-0 rounded-full" style={{ background: avatar }} />
      <div className="min-w-0">
        <p className="mb-1 text-[11px] text-neutral-500">{name}</p>
        <p
          className={`inline-block max-w-[210px] rounded-xl rounded-tl-sm bg-white px-3 py-2 text-[13px] break-all shadow-sm dark:bg-neutral-800 ${
            link ? 'text-[#1772F6] underline' : 'text-neutral-800 dark:text-neutral-100'
          }`}
        >
          {text}
        </p>
        {children && <div>{children}</div>}
      </div>
    </div>
  )
}
