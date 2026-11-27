import type { MetadataRoute } from 'next'

import { site } from '@/lib/site'
import { source } from '@/lib/source'

export const dynamic = 'force-static'

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${site.url}/` },
    ...source.getPages().map((page) => ({ url: `${site.url}${page.url}/` }))
  ]
}
