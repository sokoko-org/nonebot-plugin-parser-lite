import './global.css'

import { RootProvider } from 'fumadocs-ui/provider/next'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { zhCN } from '@/lib/i18n'
import { site } from '@/lib/site'

export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: {
    default: `${site.name} 文档`,
    template: `%s | ${site.shortName}`
  },
  description:
    'NoneBot2 链接分享自动解析插件：B 站、抖音、微博、小红书等 30+ 平台，支持视频、图文、评论区与 Live Photo 渲染。'
}

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">
        <RootProvider
          i18n={{ locale: 'zh-CN', translations: zhCN }}
          search={{
            options: {
              type: 'static',
              api: '/api/search'
            }
          }}
        >
          {children}
        </RootProvider>
      </body>
    </html>
  )
}
