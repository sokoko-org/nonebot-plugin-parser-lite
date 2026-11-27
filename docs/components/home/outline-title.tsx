'use client'

import { useEffect, useId, useRef } from 'react'

/**
 * 背景巨型描边字：进场时笔画逐步描出，鼠标所到之处亮起品牌渐变
 * 通过直接改 SVG 属性跟随鼠标，不触发 React 重渲染
 */
export function OutlineTitle({ text = 'PARSER' }: { text?: string }) {
  const svgRef = useRef<SVGSVGElement>(null)
  const spotRef = useRef<SVGRadialGradientElement>(null)
  const id = useId().replace(/:/g, '')

  useEffect(() => {
    const move = (x: number, y: number) => {
      const svg = svgRef.current
      const spot = spotRef.current
      if (!svg || !spot) return
      const rect = svg.getBoundingClientRect()
      spot.setAttribute('cx', `${((x - rect.left) / rect.width) * 100}%`)
      spot.setAttribute('cy', `${((y - rect.top) / rect.height) * 100}%`)
    }
    const onMouse = (e: MouseEvent) => move(e.clientX, e.clientY)
    const onTouch = (e: TouchEvent) => e.touches[0] && move(e.touches[0].clientX, e.touches[0].clientY)
    window.addEventListener('mousemove', onMouse, { passive: true })
    window.addEventListener('touchmove', onTouch, { passive: true })
    return () => {
      window.removeEventListener('mousemove', onMouse)
      window.removeEventListener('touchmove', onTouch)
    }
  }, [])

  const width = text.length * 74 + 8
  const common = {
    x: '50%',
    y: '54%',
    textAnchor: 'middle' as const,
    dominantBaseline: 'middle' as const,
    fontSize: 100,
    fontWeight: 900,
    letterSpacing: 2,
    fill: 'transparent',
    strokeWidth: 0.6,
    style: { fontFamily: 'Inter, "Segoe UI", Helvetica, Arial, sans-serif' }
  }

  return (
    <svg ref={svgRef} viewBox={`0 0 ${width} 120`} className="h-auto w-full select-none" aria-hidden="true">
      <defs>
        <linearGradient id={`g-${id}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#1F9E95" />
          <stop offset=".5" stopColor="#4FD9CF" />
          <stop offset="1" stopColor="#F0447F" />
        </linearGradient>
        <radialGradient ref={spotRef} id={`s-${id}`} cx="50%" cy="50%" r="22%" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fff" />
          <stop offset="1" stopColor="#000" />
        </radialGradient>
        <mask id={`m-${id}`}>
          <rect width="100%" height="100%" fill={`url(#s-${id})`} />
        </mask>
      </defs>
      <text {...common} className="outline-draw stroke-neutral-300 dark:stroke-neutral-700">
        {text}
      </text>
      <text {...common} stroke={`url(#g-${id})`} strokeWidth={1.2} mask={`url(#m-${id})`}>
        {text}
      </text>
    </svg>
  )
}
