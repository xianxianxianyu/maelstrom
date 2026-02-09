"use client"

import { useState, useEffect } from "react"
import { TranslationEntry } from "@/types"
import { getTranslationList, deleteTranslation } from "@/lib/api"

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

export function HistoryList({ onSelect, refreshKey }: Props) {
  const [entries, setEntries] = useState<TranslationEntry[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      setLoading(true)
      const list = await getTranslationList()
      setEntries(list)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [refreshKey])

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm("确定删除此翻译记录？")) return
    try {
      await deleteTranslation(id)
      setEntries(prev => prev.filter(x => x.id !== id))
    } catch { /* ignore */ }
  }

  if (loading) {
    return (
      <div className="p-4 text-center text-xs text-gray-400">加载中...</div>
    )
  }

  if (entries.length === 0) {
    return (
      <div className="p-4 text-center text-xs text-gray-400">暂无翻译记录</div>
    )
  }

  return (
    <div className="p-2 space-y-1">
      {entries.map(entry => (
        <div
          key={entry.id}
          onClick={() => onSelect(entry)}
          className="group flex items-start gap-2 p-2.5 rounded-lg cursor-pointer hover:bg-gray-50 transition"
        >
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium text-gray-700 truncate">
              {entry.display_name}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] text-gray-400">
                {timeAgo(entry.created_at)}
              </span>
              {entry.model && (
                <span className="text-[10px] text-gray-300">
                  {entry.model}
                </span>
              )}
              {entry.has_ocr && (
                <span className="text-[10px] px-1 py-0.5 bg-teal-50 text-teal-600 rounded">
                  OCR
                </span>
              )}
            </div>
          </div>
          <button
            onClick={(e) => handleDelete(e, entry.id)}
            className="opacity-0 group-hover:opacity-100 p-1 text-gray-300 hover:text-red-400 transition"
            title="删除"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  )
}
