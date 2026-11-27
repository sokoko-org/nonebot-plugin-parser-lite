import { Accordion, Accordions } from 'fumadocs-ui/components/accordion'
import { File, Files, Folder } from 'fumadocs-ui/components/files'
import { ImageZoom } from 'fumadocs-ui/components/image-zoom'
import { Step, Steps } from 'fumadocs-ui/components/steps'
import { Tab, Tabs } from 'fumadocs-ui/components/tabs'
import defaultMdxComponents from 'fumadocs-ui/mdx'
import type { MDXComponents } from 'mdx/types'

import { PlatformMatrix } from '@/components/platform-matrix'
import { Showcase } from '@/components/showcase'
import { StatsPreview } from '@/components/stats-preview'
import { asset } from '@/lib/site'

export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    Tab,
    Tabs,
    Step,
    Steps,
    Accordion,
    Accordions,
    File,
    Files,
    Folder,
    PlatformMatrix,
    Showcase,
    StatsPreview,
    // 站内绝对路径图片经 asset() 处理，外链图片保持原样
    img: (props) => {
      const src = typeof props.src === 'string' && props.src.startsWith('/') ? asset(props.src) : props.src
      return <ImageZoom {...(props as any)} src={src} />
    },
    ...components
  }
}
