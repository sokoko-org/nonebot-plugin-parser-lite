import { source } from '@/lib/source'
import { createFromSource } from 'fumadocs-core/search/server'

// 静态导出：构建时生成搜索索引，浏览器端加载后本地检索
export const revalidate = false

export const { staticGET: GET } = createFromSource(source)
