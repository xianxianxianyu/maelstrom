"use client"

import { useState, useEffect } from "react"
import { getQualityReport, QualityReport as QualityReportData } from "@/lib/api"

interface Props {
  translationId: string
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 80
      ? "bg-green-50 text-green-700 border-green-200"
      : score >= 60
        ? "bg-yellow-50 text-yellow-700 border-yellow-200"
        : "bg-red-50 text-red-700 border-red-200"
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-lg border text-sm font-bold ${color}`}>
      {score}
    </span>
  )
}

function CollapsibleSection({
  title,
  count,
  defaultOpen = false,
  children,
}: {
  title: string
  count: number
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  if (count === 0) return null
  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition text-xs font-medium text-gray-600"
      >
        <span>{title} ({count})</span>
        <svg
          className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div className="p-3">{children}</div>}
    </div>
  )
}

export function QualityReportPanel({ translationId }: Props) {
  const [report, setReport] = useState<QualityReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getQualityReport(translationId)
        if (!cancelled) setReport(data)
      } catch (err: any) {
        if (!cancelled) setError(err.message || "加载失败")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [translationId])

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <p className="text-xs text-gray-400 text-center">加载质量报告...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <p className="text-xs text-red-400 text-center">{error}</p>
      </div>
    )
  }

  if (!report) return null

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
      {/* 标题和评分 */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-700">质量报告</h3>
        <ScoreBadge score={report.score} />
      </div>

      {/* 术语问题 */}
      <CollapsibleSection title="术语问题" count={report.terminology_issues.length} defaultOpen>
        <div className="space-y-2">
          {report.terminology_issues.map((issue, i) => (
            <div key={i} className="text-xs space-y-0.5">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-700">{issue.english_term}</span>
                <span className="text-gray-300">→</span>
                <span className="text-yellow-600">{issue.translations.join(" / ")}</span>
              </div>
              <div className="text-[10px] text-gray-400">
                建议: <span className="text-indigo-600">{issue.suggested}</span>
                {issue.locations.length > 0 && (
                  <span className="ml-2">位置: {issue.locations.join(", ")}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </CollapsibleSection>

      {/* 格式问题 */}
      <CollapsibleSection title="格式问题" count={report.format_issues.length}>
        <div className="space-y-2">
          {report.format_issues.map((issue, i) => (
            <div key={i} className="text-xs space-y-0.5">
              <div className="flex items-center gap-2">
                <span className="px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded text-[10px]">
                  {issue.issue_type}
                </span>
                <span className="text-gray-600">{issue.description}</span>
              </div>
              <div className="text-[10px] text-gray-400">位置: {issue.location}</div>
            </div>
          ))}
        </div>
      </CollapsibleSection>

      {/* 未翻译段落 */}
      <CollapsibleSection title="未翻译段落" count={report.untranslated.length}>
        <div className="space-y-1">
          {report.untranslated.map((text, i) => (
            <div key={i} className="text-xs text-gray-500 bg-gray-50 px-2 py-1.5 rounded truncate">
              {text}
            </div>
          ))}
        </div>
      </CollapsibleSection>

      {/* 改进建议 */}
      <CollapsibleSection title="改进建议" count={report.suggestions.length}>
        <ul className="space-y-1">
          {report.suggestions.map((s, i) => (
            <li key={i} className="text-xs text-gray-600 flex items-start gap-1.5">
              <span className="text-indigo-400 mt-0.5">•</span>
              {s}
            </li>
          ))}
        </ul>
      </CollapsibleSection>

      {/* 时间戳 */}
      <div className="text-[10px] text-gray-300 text-right">
        {new Date(report.timestamp).toLocaleString("zh-CN")}
      </div>
    </div>
  )
}
