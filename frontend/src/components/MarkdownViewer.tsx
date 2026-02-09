"use client"

import ReactMarkdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import remarkGfm from "remark-gfm"
import { useMemo } from "react"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:3301"

interface Props {
  content: string
  translationId?: string | null
}

export function MarkdownViewer({ content, translationId }: Props) {
  // 将 ./images/xxx 替换为 API URL
  const processedContent = useMemo(() => {
    if (!translationId) return content
    return content.replace(
      /\.\/(images\/[^\s)]+)/g,
      `${API_BASE}/api/translations/${translationId}/$1`
    )
  }, [content, translationId])
  return (
    <article className="p-6 bg-white border border-gray-200 rounded-lg shadow-sm">
      <div className="prose prose-gray prose-sm max-w-none font-light
        prose-headings:font-semibold
        prose-h1:text-2xl prose-h1:border-b prose-h1:border-gray-200 prose-h1:pb-2
        prose-h2:text-xl prose-h2:mt-8
        prose-h3:text-lg prose-h3:mt-6
        prose-img:rounded-lg prose-img:shadow-md prose-img:mx-auto prose-img:max-w-full
        prose-table:text-xs
      ">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={{
            img: ({ src, alt, ...props }) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={src}
                alt={alt || "figure"}
                loading="lazy"
                className="rounded-lg shadow-md mx-auto max-w-full"
                {...props}
              />
            ),
          }}
        >
          {processedContent}
        </ReactMarkdown>
      </div>
    </article>
  )
}
