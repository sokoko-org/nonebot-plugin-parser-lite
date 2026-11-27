import { DocsBody, DocsDescription, DocsPage, DocsTitle, EditOnGitHub } from 'fumadocs-ui/layouts/docs/page'
import { createRelativeLink } from 'fumadocs-ui/mdx'
import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { site } from '@/lib/site'
import { source } from '@/lib/source'
import { getMDXComponents } from '@/mdx-components'

interface PageProps {
  params: Promise<{ slug?: string[] }>
}

export default async function Page(props: PageProps) {
  const params = await props.params
  const page = source.getPage(params.slug)
  if (!page) notFound()

  const MDX = page.data.body

  return (
    <DocsPage toc={page.data.toc} full={page.data.full}>
      <DocsTitle>{page.data.title}</DocsTitle>
      <DocsDescription>{page.data.description}</DocsDescription>
      <DocsBody>
        <MDX components={getMDXComponents({ a: createRelativeLink(source, page) })} />
      </DocsBody>
      <EditOnGitHub href={`${site.repo}/blob/main/docs/content/docs/${page.path}`} />
    </DocsPage>
  )
}

export function generateStaticParams() {
  return source.generateParams()
}

export async function generateMetadata(props: PageProps): Promise<Metadata> {
  const params = await props.params
  const page = source.getPage(params.slug)
  if (!page) notFound()

  return {
    title: page.data.title,
    description: page.data.description
  }
}
