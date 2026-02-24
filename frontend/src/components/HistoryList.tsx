"use client"

import { useEffect, useMemo, useState } from "react"

import { deleteTranslation, getTranslationList } from "@/lib/api"
import { PaperMetadataDrawer } from "@/components/PaperMetadataDrawer"
import { TranslationEntry } from "@/types"

interface Props {
  onSelect: (entry: TranslationEntry) => void
  refreshKey?: number
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "刚刚"
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  return `${days}天前`
}

function normalizeTags(entry: TranslationEntry): string[] {
  if (Array.isArray(entry.paper_tags)) {
    return entry.paper_tags.filter(Boolean)
  }
  return []
}

function normalizeKeywords(entry: TranslationEntry): string[] {
  if (Array.isArray(entry.paper_keywords)) {
    return entry.paper_keywords.filter(Boolean)
  }
  return []
}

export function HistoryList({ onSelect, refreshKey }: Props) {
  const [entries, setEntries] = useState<TranslationEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTag, setActiveTag] = useState<string | null>(null)
  const [drawerEntry, setDrawerEntry] = useState<TranslationEntry | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      const list = await getTranslationList()
      setEntries(list)
    } catch {
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [refreshKey])

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm("确定删除此翻译记录？")) return
    try {
      await deleteTranslation(id)
      setEntries((prev) => prev.filter((x) => x.id !== id))
      if (drawerEntry?.id === id) {
        setDrawerEntry(null)
      }
    } catch {
    }
  }

  const allTags = useMemo(() => {
    const tagSet = new Set<string>()
    for (const entry of entries) {
      normalizeTags(entry).forEach((tag) => tagSet.add(tag))
    }
    return Array.from(tagSet)
  }, [entries])

  const visibleEntries = useMemo(() => {
    if (!activeTag) {
      return entries
    }
    return entries.filter((entry) => normalizeTags(entry).includes(activeTag))
  }, [activeTag, entries])

  if (loading) {
    return <div className="p-4 text-center text-xs text-gray-400">加载中...</div>
  }

  if (entries.length === 0) {
    return <div className="p-4 text-center text-xs text-gray-400">暂无翻译记录</div>
  }

  return (
    <>
      <div className="p-3 border-b border-gray-100 bg-gray-50/80">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-gray-400">Tag 分类:</span>
          <button
            onClick={() => setActiveTag(null)}
            className={`px-2 py-1 text-[11px] rounded-md border ${
              !activeTag
                ? "border-indigo-200 bg-indigo-50 text-indigo-600"
                : "border-gray-200 bg-white text-gray-500 hover:border-gray-300"
            }`}
          >
            全部
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setActiveTag(tag)}
              className={`px-2 py-1 text-[11px] rounded-md border ${
                activeTag === tag
                  ? "border-indigo-200 bg-indigo-50 text-indigo-600"
                  : "border-gray-200 bg-white text-gray-500 hover:border-gray-300"
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      </div>

      <div className="p-3 space-y-3">
        {visibleEntries.map((entry) => {
          const title = entry.paper_title || entry.display_name
          const keywords = normalizeKeywords(entry)
          const tags = normalizeTags(entry)

          return (
            <article key={entry.id} className="group border border-gray-200 rounded-xl bg-white p-3 hover:border-indigo-200 transition">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <button
                    onClick={() => onSelect(entry)}
                    className="text-left text-sm font-semibold text-gray-800 hover:text-indigo-600 line-clamp-2"
                    title="跳转到文档翻译页面"
                  >
                    {title}
                  </button>

                  <div className="mt-1 text-[11px] text-gray-400 flex items-center gap-2 flex-wrap">
                    <span>{timeAgo(entry.created_at)}</span>
                    {entry.model && <span>{entry.model}</span>}
                    {entry.paper_domain && <span>领域: {entry.paper_domain}</span>}
                    {entry.paper_year && <span>年份: {entry.paper_year}</span>}
                    {entry.has_ocr && (
                      <span className="text-[10px] px-1 py-0.5 bg-teal-50 text-teal-600 rounded">OCR</span>
                    )}
                    {entry.index_status && (
                      <span className="text-[10px] px-1 py-0.5 bg-amber-50 text-amber-600 rounded">{entry.index_status}</span>
                    )}
                  </div>

                  {keywords.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {keywords.map((keyword) => (
                        <span key={keyword} className="px-1.5 py-0.5 text-[10px] rounded bg-slate-100 text-slate-600">
                          {keyword}
                        </span>
                      ))}
                    </div>
                  )}

                  {tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {tags.map((tag) => (
                        <button
                          key={tag}
                          onClick={() => setActiveTag(tag)}
                          className="px-2 py-0.5 text-[10px] rounded-full border border-indigo-200 bg-indigo-50 text-indigo-600 hover:bg-indigo-100"
                          title="按 tag 筛选"
                        >
                          {tag}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setDrawerEntry(entry)}
                    disabled={!entry.task_id}
                    className="px-2 py-1 text-[11px] rounded-md border border-gray-200 text-gray-500 hover:border-indigo-200 hover:text-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed"
                    title={entry.task_id ? "查看元数据" : "缺少 task_id，无法打开元数据"}
                  >
                    元数据
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, entry.id)}
                    className="p-1 text-gray-300 hover:text-red-500 transition"
                    title="删除"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            </article>
          )
        })}
      </div>

      <PaperMetadataDrawer
        open={!!drawerEntry}
        taskId={drawerEntry?.task_id || null}
        displayName={drawerEntry?.paper_title || drawerEntry?.display_name || ""}
        onClose={() => setDrawerEntry(null)}
        onSaved={(patch) => {
          if (!drawerEntry) {
            return
          }
          setEntries((prev) => prev.map((entry) => {
            if (entry.id !== drawerEntry.id) {
              return entry
            }
            return {
              ...entry,
              ...patch,
            }
          }))
        }}
      />
    </>
  )
}
