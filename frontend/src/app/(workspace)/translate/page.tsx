"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { UploadButton } from "@/components/UploadButton"
import { MarkdownViewer } from "@/components/MarkdownViewer"
import { LoadingState } from "@/components/LoadingState"
import { QAPanel } from "@/components/QAPanel"
import { TranslationProgress } from "@/components/TranslationProgress"
import {
  uploadPDF, cancelAllTasks, cancelTask, getTranslation,
  getTranslationResult,
} from "@/lib/api"
import { ModelConfig } from "@/types"
import { useLLMConfig } from "@/contexts/LLMConfigContext"
import { useTranslationSettings } from "@/contexts/TranslationSettingsContext"

export default function TranslatePage() {
  const [translationParam, setTranslationParam] = useState<string | null>(null)

  const [markdown, setMarkdown] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const { profileNames, profileMap, bindings } = useLLMConfig()
  const { systemPrompt } = useTranslationSettings()
  const [selectedProfile, setSelectedProfile] = useState("")
  const [enableOcr, setEnableOcr] = useState(false)
  const [ocrMarkdown, setOcrMarkdown] = useState("")
  const [viewTab, setViewTab] = useState<"llm" | "ocr">("llm")
  const [translationId, setTranslationId] = useState<string | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [qaWidth, setQaWidth] = useState(320)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!selectedProfile || !profileNames.includes(selectedProfile)) {
      const bound = bindings?.translation
      if (bound && profileNames.includes(bound)) setSelectedProfile(bound)
      else if (profileNames.length > 0) setSelectedProfile(profileNames[0])
    }
  }, [profileNames, bindings, selectedProfile])

  useEffect(() => {
    if (!isDragging) return
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const newWidth = rect.right - e.clientX
      setQaWidth(Math.max(200, Math.min(600, newWidth)))
    }
    const handleMouseUp = () => setIsDragging(false)
    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)
    document.body.style.cursor = "col-resize"
    document.body.style.userSelect = "none"
    return () => {
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
    }
  }, [isDragging])

  useEffect(() => {
    const readQuery = () => {
      const params = new URLSearchParams(window.location.search)
      setTranslationParam(params.get("translationId"))
    }

    readQuery()
    window.addEventListener("popstate", readQuery)
    return () => {
      window.removeEventListener("popstate", readQuery)
    }
  }, [])

  useEffect(() => {
    if (!translationParam) return

    let cancelled = false
    const loadHistoryDetail = async () => {
      try {
        setLoading(true)
        setError("")
        const data = await getTranslation(translationParam)
        if (cancelled) return
        setMarkdown(data.markdown || "")
        setOcrMarkdown(data.ocr_markdown || "")
        setTranslationId(translationParam)
        setViewTab("llm")
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "加载失败")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadHistoryDetail()
    return () => {
      cancelled = true
    }
  }, [translationParam])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleUpload = async (file: File) => {
    const profile = profileMap[selectedProfile]
    if (!profile) {
      setError("请先在配置页完成 LLM 档案配置")
      return
    }

    setLoading(true)
    setError("")
    setMarkdown("")
    setOcrMarkdown("")
    setTaskId(null)
    setTranslationId(null)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const config: ModelConfig = {
        provider: profile.provider as ModelConfig["provider"],
        model: profile.model,
      }
      const uploadResult = await uploadPDF(file, config, systemPrompt, enableOcr, controller.signal)
      const asyncTaskId = (uploadResult as any).task_id

      if (asyncTaskId && (uploadResult as any).status === "processing") {
        setTaskId(asyncTaskId)
      } else {
        const result = uploadResult as any
        setMarkdown(result.markdown || "")
        setOcrMarkdown(result.ocr_markdown || "")
        setTranslationId(result.translation_id || null)
        setViewTab("llm")
        setLoading(false)
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError("任务已停止")
      } else {
        setError(err instanceof Error ? err.message : "上传失败")
      }
      setLoading(false)
      setTaskId(null)
    } finally {
      abortRef.current = null
    }
  }

  const handleTranslationComplete = useCallback(async () => {
    if (!taskId) return
    try {
      const result = await getTranslationResult(taskId)
      setMarkdown(result.markdown || result.translated_md || "")
      setOcrMarkdown(result.ocr_markdown || "")
      setTranslationId(result.translation_id || null)
      setViewTab("llm")
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取翻译结果失败")
    } finally {
      setLoading(false)
      setTaskId(null)
    }
  }, [taskId])

  const handleTranslationError = useCallback((errorMsg: string) => {
    setError(errorMsg)
    setLoading(false)
    setTaskId(null)
  }, [])

  const handleCancel = async () => {
    abortRef.current?.abort()
    try {
      if (taskId) await cancelTask(taskId)
      else await cancelAllTasks()
    } catch {
    }
    setLoading(false)
    setTaskId(null)
  }

  return (
    <div ref={containerRef} className="flex h-full overflow-hidden">
      <main className="flex-1 flex flex-col min-w-0 bg-gray-50">
        <header className="h-14 flex items-center justify-between px-6 bg-white border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center gap-4">
            <h1 className="text-base font-semibold text-gray-800">文档翻译</h1>
            <div className="h-5 w-px bg-gray-200" />
            <select
              value={selectedProfile}
              onChange={(e) => setSelectedProfile(e.target.value)}
              className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg bg-gray-50 text-gray-600 hover:border-gray-300 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 outline-none transition"
            >
              <option value="">选择 LLM 档案</option>
              {profileNames.map((name) => (
                <option key={name} value={name}>
                  {name}{profileMap[name] ? ` · ${profileMap[name].provider}` : ""}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={enableOcr}
                onChange={(e) => setEnableOcr(e.target.checked)}
                className="rounded text-teal-600 focus:ring-teal-500"
              />
              <span className="text-xs text-gray-500">OCR</span>
            </label>
          </div>
          <UploadButton onUpload={handleUpload} disabled={loading} />
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          {loading && (
            <div className="space-y-4">
              <LoadingState onCancel={handleCancel} />
              {taskId && (
                <TranslationProgress
                  taskId={taskId}
                  onComplete={handleTranslationComplete}
                  onError={handleTranslationError}
                />
              )}
            </div>
          )}

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 text-red-600 rounded-xl text-sm mb-4">
              {error}
            </div>
          )}

          {!markdown && !loading && !error && (
            <div className="flex flex-col items-center justify-center h-full text-gray-300 select-none">
              <svg className="w-20 h-20 mb-5 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.8} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-sm font-medium text-gray-400">上传 PDF 文档开始翻译</p>
              <p className="text-xs text-gray-300 mt-1">支持学术论文、技术文档等</p>
            </div>
          )}

          {markdown && !loading && (
            <>
              {ocrMarkdown && (
                <div className="flex gap-1 mb-4">
                  <button
                    onClick={() => setViewTab("llm")}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
                      viewTab === "llm"
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                    }`}
                  >
                    双语翻译
                  </button>
                  <button
                    onClick={() => setViewTab("ocr")}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
                      viewTab === "ocr"
                        ? "bg-teal-600 text-white"
                        : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                    }`}
                  >
                    OCR 原文
                  </button>
                </div>
              )}
              <MarkdownViewer
                content={viewTab === "ocr" && ocrMarkdown ? ocrMarkdown : markdown}
                translationId={translationId}
              />
            </>
          )}
        </div>
      </main>

      <div
        onMouseDown={handleMouseDown}
        className={`w-1 flex-shrink-0 cursor-col-resize group relative transition-colors ${
          isDragging ? "bg-indigo-400" : "bg-gray-200 hover:bg-indigo-300"
        }`}
      >
        <div className="absolute inset-y-0 -left-1 -right-1 z-10" />
        <div
          className={`absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2 w-1 h-8 rounded-full transition-colors ${
            isDragging ? "bg-indigo-500" : "bg-gray-300 group-hover:bg-indigo-400"
          }`}
        />
      </div>

      <aside style={{ width: qaWidth }} className="flex-shrink-0 flex flex-col bg-white">
        <QAPanel />
      </aside>
    </div>
  )
}
