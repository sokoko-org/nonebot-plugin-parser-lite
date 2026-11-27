import { useId, type SVGProps } from 'react'

/** 路径与 app/icon.svg、assets/readme/banner.svg 保持一致 */
const MARK = 'M11 4H21A6 6 0 0 1 27 10V15A6 6 0 0 1 21 21H12V24.5A3.5 3.5 0 0 1 5 24.5V10A6 6 0 0 1 11 4ZM14.25 8.5H21.75A1.25 1.25 0 0 1 21.75 11H14.25A1.25 1.25 0 0 1 14.25 8.5ZM14.25 13.5H18.75A1.25 1.25 0 0 1 18.75 16H14.25A1.25 1.25 0 0 1 14.25 13.5Z'

/**
 * 品牌标志：字母 P 的上半部是一个聊天气泡，里面两行短线代表渲染出的卡片内容，
 * 右下角的粉点是 bot 贴上的表情回应。
 * 布局会同时渲染桌面端与移动端两份，渐变 id 用 useId 保证每份唯一，
 * 否则被隐藏的那一份会「抢走」定义导致不显示
 */
export function Logo({ className = '', ...props }: SVGProps<SVGSVGElement>) {
  const id = useId()
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={`shrink-0 ${className}`} {...props}>
      <defs>
        <linearGradient id={id} x1="5" y1="4" x2="27" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4FD9CF" />
          <stop offset="1" stopColor="#1F9E95" />
        </linearGradient>
      </defs>
      <path fill={`url(#${id})`} fillRule="evenodd" d={MARK} />
      <circle cx="24" cy="25.5" r="3.5" fill="#F0447F" />
    </svg>
  )
}
