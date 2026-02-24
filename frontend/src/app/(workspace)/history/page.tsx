"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { HistoryList } from "@/components/HistoryList"
import { TranslationEntry } from "@/types"

export default function HistoryPage() {
  const router = useRouter()
  const [refreshKey, setRefreshKey] = useState(0)

  const handleSelect = (entry: TranslationEntry) => {
    router.push(`/translate?translationId=${entry.id}`)
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <header className="h-14 flex items-center justify-between px-6 bg-white border-b border-gray-200 flex-shrink-0">
        <h1 className="text-base font-semibold text-gray-800">历史记录</h1>
        <button
          onClick={() => setRefreshKey((v) => v + 1)}
          className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg bg-gray-50 text-gray-600 hover:border-gray-300"
        >
          刷新
        </button>
      </header>
      <div className="flex-1 overflow-y-auto p-4">
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <HistoryList onSelect={handleSelect} refreshKey={refreshKey} />
        </div>
      </div>
    </div>
  )
}
