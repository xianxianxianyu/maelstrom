"use client"

import ReactMarkdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import { useMemo, type ReactNode } from "react"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:3301"

interface Props {
  content: string
  translationId?: string | null
}

export function MarkdownViewer({ content, translationId }: Props) {
  const processedContent = useMemo(() => {
    let text = content
    if (translationId) {
      text = text.replace(
        /\.\/(images\/[^\s)]+)/g,
        `${API_BASE}/api/translations/${translationId}/$1`
      )
    }
    return text
  }, [content, translationId])

  return (
    <article className="markdown-viewer p-6 md:p-8 bg-white border border-gray-200 rounded-lg shadow-sm">
      <div className="prose prose-gray prose-sm max-w-none
        prose-headings:font-semibold prose-headings:tracking-tight
        prose-h1:text-2xl prose-h1:border-b prose-h1:border-gray-200 prose-h1:pb-2 prose-h1:mb-6
        prose-h2:text-xl prose-h2:mt-10 prose-h2:mb-3
        prose-h3:text-lg prose-h3:mt-8 prose-h3:mb-2
        prose-h4:text-base prose-h4:mt-6
        prose-p:leading-[1.8] prose-p:mb-4 prose-p:text-gray-700
        prose-a:text-indigo-600 prose-a:no-underline hover:prose-a:underline
        prose-strong:text-gray-900
        prose-blockquote:border-l-indigo-300 prose-blockquote:bg-indigo-50/50 prose-blockquote:py-1 prose-blockquote:text-gray-600 prose-blockquote:not-italic
        prose-code:text-sm prose-code:bg-gray-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none
        prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:rounded-lg prose-pre:shadow-sm
        prose-img:rounded-lg prose-img:shadow-md prose-img:mx-auto prose-img:max-w-full prose-img:my-6
        prose-table:text-xs prose-table:border-collapse
        prose-th:bg-gray-50 prose-th:font-semibold prose-th:text-gray-700 prose-th:border prose-th:border-gray-200 prose-th:px-3 prose-th:py-2
        prose-td:border prose-td:border-gray-200 prose-td:px-3 prose-td:py-2
      ">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeRaw, rehypeKatex]}
          components={{
            img: ({ src, alt, ...props }) => (
              <figure className="my-8 text-center">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={src}
                  alt={alt || "figure"}
                  loading="lazy"
                  className="rounded-lg shadow-md mx-auto max-w-full border border-gray-100"
                  {...props}
                />
                {alt && alt !== "figure" && alt !== "Image" && (
                  <figcaption className="text-center text-xs text-gray-500 mt-3 px-6 leading-relaxed max-w-2xl mx-auto">
                    {alt}
                  </figcaption>
                )}
              </figure>
            ),
            blockquote: ({ children, ...props }) => (
              <blockquote
                className="border-l-4 border-indigo-300 bg-indigo-50/50 pl-4 pr-3 py-2 my-4 rounded-r-lg text-sm text-gray-600 not-italic leading-relaxed"
                {...props}
              >
                {children}
              </blockquote>
            ),
            table: ({ children, ...props }) => (
              <div className="overflow-x-auto my-6 rounded-lg border border-gray-200 shadow-sm">
                <table className="min-w-full text-xs leading-relaxed" {...props}>
                  {children}
                </table>
              </div>
            ),
            pre: ({ children, ...props }) => (
              <pre
                className="bg-gray-900 text-gray-100 rounded-lg p-4 my-4 overflow-x-auto text-sm shadow-sm"
                {...props}
              >
                {children}
              </pre>
            ),
            sup: ({ children, ...props }) => (
              <sup
                className="text-indigo-600 text-[0.7em] font-normal cursor-default hover:text-indigo-800 transition-colors"
                {...props}
              >
                {children}
              </sup>
            ),
            // figcaption div from backend postprocess
            div: ({ className, children, ...props }) => {
              if (className === "figcaption") {
                return (
                  <div
                    className="text-center text-xs text-gray-500 my-2 px-6 leading-relaxed max-w-3xl mx-auto"
                    {...props}
                  >
                    {children}
                  </div>
                )
              }
              return <div className={className} {...props}>{children}</div>
            },
          }}
        >
          {processedContent}
        </ReactMarkdown>
      </div>
    </article>
  )
}
