'use client'

import { type RefObject, useEffect, useState } from 'react'

/** 元素在「固定区段」内的滚动进度 0~1：顶部到达视口顶为 0，底部到达视口底为 1 */
export function useScrollProgress(ref: RefObject<HTMLElement | null>) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    let frame = 0
    const update = () => {
      frame = 0
      const el = ref.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const total = rect.height - window.innerHeight
      setProgress(total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 0)
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
    }
  }, [ref])

  return progress
}

/** 用户是否开启了「减少动态效果」 */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setReduced(query.matches)
    sync()
    query.addEventListener('change', sync)
    return () => query.removeEventListener('change', sync)
  }, [])
  return reduced
}

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
/** 把 [start, end] 区间映射到 0~1 */
export const segment = (v: number, start: number, end: number) => clamp01((v - start) / (end - start))
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t
