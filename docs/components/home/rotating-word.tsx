'use client'

import { useEffect, useState } from 'react'

const words = [
  { text: 'B 站视频', color: '#FB7299' },
  { text: '小红书笔记', color: '#FF2442' },
  { text: '抖音短视频', color: '#FE2C55' },
  { text: '知乎回答', color: '#1772F6' },
  { text: '微博', color: '#E6162D' },
  { text: '网易云歌曲', color: '#E60026' },
  { text: '贴吧帖子', color: '#3388FF' },
  { text: '小黑盒动态', color: '#5B5BEF' }
]

/**
 * 轮播平台内容名。所有词叠在同一个 grid 单元里，
 * 宽度取最长的那个，切换时不会造成标题抖动
 */
export function RotatingWord() {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const timer = setInterval(() => setIndex((i) => (i + 1) % words.length), 2200)
    return () => clearInterval(timer)
  }, [])

  return (
    <span className="inline-grid align-bottom">
      {words.map((word, i) => (
        <span
          key={word.text}
          aria-hidden={i !== index}
          className={`col-start-1 row-start-1 transition-all duration-500 ease-out ${
            i === index ? 'translate-y-0 opacity-100 blur-0' : 'translate-y-[0.4em] opacity-0 blur-sm'
          }`}
          style={{ color: word.color }}
        >
          {word.text}
        </span>
      ))}
    </span>
  )
}
