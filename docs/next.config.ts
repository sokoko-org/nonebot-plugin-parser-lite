import { createMDX } from 'fumadocs-mdx/next'
import type { NextConfig } from 'next'

const withMDX = createMDX()

const config: NextConfig = {
  // 纯静态导出：Vercel 直接托管 out/，不产生 Serverless 函数
  output: 'export',
  trailingSlash: true,
  reactStrictMode: true,
  turbopack: { root: import.meta.dirname },
  images: { unoptimized: true }
}

export default withMDX(config)
