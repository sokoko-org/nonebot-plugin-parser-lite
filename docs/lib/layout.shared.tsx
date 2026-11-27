import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared'

import { Logo } from '@/components/logo'
import { site } from '@/lib/site'

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <span className="inline-flex items-center gap-2">
          <Logo className="size-7" />
          <span className="flex flex-col items-start">
            <span className="text-[10px] font-semibold tracking-wide uppercase opacity-70">nonebot-plugin</span>
            <span className="text-base leading-tight font-bold">parser-lite</span>
          </span>
        </span>
      )
    },
    githubUrl: site.repo,
    links: [
      { text: '文档', url: '/docs', active: 'nested-url' },
      { text: '主题商店', url: site.themesRepo, external: true }
    ]
  }
}
