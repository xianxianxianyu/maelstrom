"use client"

import { useEffect, useMemo, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { getPaperDetail, PaperDetailResponse, updatePaperRaw, updatePaperSection } from "@/lib/api"

interface HistorySummaryPatch {
  paper_title: string
  paper_keywords: string[]
  paper_tags: string[]
  paper_domain: string
  paper_year: number | null
}

interface Props {
  open: boolean
  taskId: string | null
  displayName: string
  onClose: () => void
  onSaved: (patch: Partial<HistorySummaryPatch>) => void
}

const SECTION_ORDER = [
  "title_zh",
  "title",
  "abstract",
  "research_problem",
  "methodology",
  "contributions",
  "keywords",
  "tags",
  "authors",
  "base_models",
  "domain",
  "year",
  "venue",
  "filename",
  "quality_score",
  "sql_raw",
] as const

const SECTION_LABELS: Record<string, string> = {
  title_zh: "论文中文标题",
  title: "论文英文标题",
  abstract: "摘要",
  research_problem: "研究问题",
  methodology: "方法",
  contributions: "贡献点",
  keywords: "关键词",
  tags: "Tag 分类",
  authors: "作者",
  base_models: "基础模型",
  domain: "领域",
  year: "年份",
  venue: "会议/期刊",
  filename: "文件名",
  quality_score: "质量分",
  sql_raw: "SQL 信息（原始记录）",
}

function asMarkdownText(input: string | undefined) {
  if (!input) {
    return ""
  }
  return input
}

export function PaperMetadataDrawer({ open, taskId, displayName, onClose, onSaved }: Props) {
  const [detail, setDetail] = useState<PaperDetailResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [draft, setDraft] = useState("")

  useEffect(() => {
    if (!open || !taskId) {
      return
    }

    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError("")
      try {
        const response = await getPaperDetail(taskId)
        if (!cancelled) {
          setDetail(response)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载元数据失败")
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [open, taskId])

  const availableSections = useMemo(() => {
    if (!detail) {
      return []
    }
    return SECTION_ORDER.filter((key) => key in detail.sections)
  }, [detail])

  if (!open) {
    return null
  }

  const startEdit = (section: string) => {
    const current = detail?.sections?.[section] ?? ""
    setEditingKey(section)
    setDraft(current)
  }

  const cancelEdit = () => {
    setEditingKey(null)
    setDraft("")
  }

  const applySummaryPatch = (next: PaperDetailResponse) => {
    onSaved({
      paper_title: next.paper.title_zh || next.paper.title || displayName,
      paper_keywords: next.paper.keywords || [],
      paper_tags: next.paper.tags || [],
      paper_domain: next.paper.domain || "",
      paper_year: next.paper.year,
    })
  }

  const saveEdit = async () => {
    if (!taskId || !editingKey) {
      return
    }

    setSaving(true)
    setError("")

    try {
      const next = editingKey === "sql_raw"
        ? await updatePaperRaw(taskId, draft)
        : await updatePaperSection(taskId, editingKey, draft)

      setDetail(next)
      applySummaryPatch(next)
      cancelEdit()
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/25" onClick={onClose} />
      <div className="relative w-full max-w-3xl h-full bg-white border-l border-gray-200 shadow-2xl flex flex-col">
        <header className="h-14 px-5 flex items-center justify-between border-b border-gray-200">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-gray-800 truncate">{displayName}</div>
            <div className="text-[11px] text-gray-400 truncate">任务 ID: {taskId || "-"}</div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
            title="关闭"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-gray-50">
          {loading && <div className="text-sm text-gray-400">元数据加载中...</div>}
          {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">{error}</div>}

          {!loading && detail && availableSections.map((section) => {
            const sectionLabel = SECTION_LABELS[section] || section
            const content = detail.sections[section] || ""
            const editing = editingKey === section

            return (
              <section key={section} className="bg-white border border-gray-200 rounded-xl">
                <header className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-700">{sectionLabel}</h3>
                  {!editing && (
                    <button
                      onClick={() => startEdit(section)}
                      className="text-xs px-2.5 py-1 rounded-md border border-gray-200 text-gray-500 hover:text-indigo-600 hover:border-indigo-200"
                    >
                      编辑
                    </button>
                  )}
                </header>

                <div className="p-4">
                  {editing ? (
                    <>
                      <textarea
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        rows={section === "sql_raw" ? 18 : 10}
                        className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg bg-gray-50 font-mono focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 outline-none"
                      />
                      <div className="mt-3 flex items-center justify-end gap-2">
                        <button
                          onClick={cancelEdit}
                          className="px-3 py-1.5 text-xs rounded-md border border-gray-200 text-gray-500 hover:bg-gray-50"
                        >
                          取消
                        </button>
                        <button
                          onClick={saveEdit}
                          disabled={saving}
                          className="px-3 py-1.5 text-xs rounded-md bg-indigo-600 text-white disabled:opacity-60"
                        >
                          {saving ? "保存中..." : "保存"}
                        </button>
                      </div>
                    </>
                  ) : section === "sql_raw" ? (
                    <pre className="text-xs leading-6 bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto">{asMarkdownText(content)}</pre>
                  ) : (
                    <article className="prose prose-sm max-w-none prose-headings:mt-0 prose-p:my-2 prose-li:my-1">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{asMarkdownText(content) || "_暂无内容_"}</ReactMarkdown>
                    </article>
                  )}
                </div>
              </section>
            )
          })}
        </div>
      </div>
    </div>
  )
}
