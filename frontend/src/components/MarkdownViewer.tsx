"use client"

import ReactMarkdown from "react-markdown"

interface Props {
  content: string
}

export function MarkdownViewer({ content }: Props) {
  return (
    <article className="mt-12 p-8 bg-white border border-slate-200 rounded shadow-sm">
      <div className="prose prose-slate max-w-none font-light">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </article>
  )
}
