"use client"

import { useState, useEffect, useCallback } from "react"
import {
  getTerminology,
  searchTerminology,
  updateTerm,
  deleteTerm,
  TermEntry,
} from "@/lib/api"

interface Props {
  domain?: string
}

export function TerminologyPanel({ domain = "general" }: Props) {
  const [terms, setTerms] = useState<TermEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [editingTerm, setEditingTerm] = useState<string | null>(null)
  const [editValue, setEditValue] = useState("")
  const [error, setError] = useState<string | null>(null)

  // 新增术语表单
  const [showAdd, setShowAdd] = useState(false)
  const [newEnglish, setNewEnglish] = useState("")
  const [newChinese, setNewChinese] = useState("")

  const loadTerms = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTerminology(domain)
      setTerms(data)
    } catch (err: any) {
      setError(err.message || "加载失败")
    } finally {
      setLoading(false)
    }
  }, [domain])

  useEffect(() => {
    if (!searchQuery.trim()) {
      loadTerms()
    }
  }, [loadTerms, searchQuery])

  const handleSearch = async () => {
    const q = searchQuery.trim()
    if (!q) {
      loadTerms()
      return
    }
    setLoading(true)
    setError(null)
    try {
      const results = await searchTerminology(q)
      setTerms(results)
    } catch (err: any) {
      setError(err.message || "搜索失败")
    } finally {
      setLoading(false)
    }
  }

  const handleEdit = (term: TermEntry) => {
    setEditingTerm(term.english)
    setEditValue(term.chinese)
  }

  const handleSaveEdit = async (english: string) => {
    try {
      await updateTerm(domain, english, editValue)
      setEditingTerm(null)
      setEditValue("")
      // 刷新列表
      if (searchQuery.trim()) {
        handleSearch()
      } else {
        loadTerms()
      }
    } catch (err: any) {
      setError(err.message || "更新失败")
    }
  }

  const handleCancelEdit = () => {
    setEditingTerm(null)
    setEditValue("")
  }

  const handleDelete = async (english: string) => {
    if (!confirm(`确定删除术语 "${english}"？`)) return
    try {
      await deleteTerm(domain, english)
      setTerms((prev) => prev.filter((t) => t.english !== english))
    } catch (err: any) {
      setError(err.message || "删除失败")
    }
  }

  const handleAdd = async () => {
    const eng = newEnglish.trim()
    const chn = newChinese.trim()
    if (!eng || !chn) return
    try {
      await updateTerm(domain, eng, chn)
      setNewEnglish("")
      setNewChinese("")
      setShowAdd(false)
      loadTerms()
    } catch (err: any) {
      setError(err.message || "添加失败")
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
      {/* 标题行 */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-700">
          术语管理
          <span className="ml-1.5 text-[10px] font-normal text-gray-400">({domain})</span>
        </h3>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="text-[10px] px-2 py-1 text-indigo-600 hover:bg-indigo-50 rounded transition"
        >
          {showAdd ? "取消" : "+ 添加"}
        </button>
      </div>

      {/* 新增表单 */}
      {showAdd && (
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="block text-[10px] text-gray-400 mb-0.5">英文</label>
            <input
              type="text"
              value={newEnglish}
              onChange={(e) => setNewEnglish(e.target.value)}
              className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-md bg-gray-50 focus:ring-1 focus:ring-indigo-300"
              placeholder="English term"
            />
          </div>
          <div className="flex-1">
            <label className="block text-[10px] text-gray-400 mb-0.5">中文</label>
            <input
              type="text"
              value={newChinese}
              onChange={(e) => setNewChinese(e.target.value)}
              className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-md bg-gray-50 focus:ring-1 focus:ring-indigo-300"
              placeholder="中文翻译"
            />
          </div>
          <button
            onClick={handleAdd}
            disabled={!newEnglish.trim() || !newChinese.trim()}
            className="px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:bg-gray-300 transition"
          >
            添加
          </button>
        </div>
      )}

      {/* 搜索栏 */}
      <div className="flex gap-2">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSearch() }}
          className="flex-1 px-2.5 py-1.5 text-xs border border-gray-200 rounded-md bg-gray-50 focus:ring-1 focus:ring-indigo-300"
          placeholder="搜索术语..."
        />
        <button
          onClick={handleSearch}
          className="px-3 py-1.5 text-xs text-gray-600 border border-gray-200 rounded-md hover:bg-gray-50 transition"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </button>
      </div>

      {/* 错误提示 */}
      {error && (
        <p className="text-[10px] text-red-400">{error}</p>
      )}

      {/* 术语列表 */}
      {loading ? (
        <p className="text-xs text-gray-400 text-center py-4">加载中...</p>
      ) : terms.length === 0 ? (
        <p className="text-xs text-gray-400 text-center py-4">暂无术语</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-100">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 text-gray-500">
                <th className="text-left px-3 py-2 font-medium">英文</th>
                <th className="text-left px-3 py-2 font-medium">中文</th>
                <th className="text-right px-3 py-2 font-medium w-20">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {terms.map((term) => (
                <tr key={term.english} className="hover:bg-gray-50/50 transition">
                  <td className="px-3 py-2 text-gray-700 font-medium">{term.english}</td>
                  <td className="px-3 py-2">
                    {editingTerm === term.english ? (
                      <div className="flex items-center gap-1">
                        <input
                          type="text"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveEdit(term.english)
                            if (e.key === "Escape") handleCancelEdit()
                          }}
                          autoFocus
                          className="flex-1 px-1.5 py-0.5 text-xs border border-indigo-300 rounded bg-white focus:ring-1 focus:ring-indigo-300"
                        />
                        <button
                          onClick={() => handleSaveEdit(term.english)}
                          className="text-green-600 hover:text-green-700 p-0.5"
                          title="保存"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          className="text-gray-400 hover:text-gray-600 p-0.5"
                          title="取消"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ) : (
                      <span
                        className="text-gray-600 cursor-pointer hover:text-indigo-600 transition"
                        onClick={() => handleEdit(term)}
                        title="点击编辑"
                      >
                        {term.chinese}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {editingTerm !== term.english && (
                      <button
                        onClick={() => handleDelete(term.english)}
                        className="text-gray-300 hover:text-red-400 transition p-0.5"
                        title="删除"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
