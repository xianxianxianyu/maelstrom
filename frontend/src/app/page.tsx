"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Sidebar } from "@/components/Sidebar"
import { UploadButton } from "@/components/UploadButton"
import { MarkdownViewer } from "@/components/MarkdownViewer"
import { LoadingState } from "@/components/LoadingState"
import { QAPanel } from "@/components/QAPanel"
import { TranslationProgress } from "@/components/TranslationProgress"
import {
  uploadPDF, cancelAllTasks, cancelTask, getTranslation,
  getTranslationResult,
} from "@/lib/api"
import { ModelConfig, TranslationEntry } from "@/types"
import { useLLMConfig } from "@/contexts/LLMConfigContext"

export default function Home() {
  const [markdown, setMarkdown] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const { profileNames, profileMap, bindings } = useLLMConfig()
  const [selectedProfile, setSelectedProfile] = useState("")
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a professional English-to-Chinese translator for academic papers.\n" +
    "RULES:\n" +
    "1. Translate the given English text into Chinese. Do NOT explain, summarize, or expand the content.\n" +
    "2. Output format: first the original English paragraph, then immediately below it the Chinese translation.\n" +
    "3. Preserve all Markdown formatting: headings (#, ##, ###), bold, italic, lists, tables, math formulas.\n" +
    "4. Do NOT add any content that is not in the original text.\n" +
    "5. Do NOT wrap output in code fences.\n" +
    "6. For short fragments (author names, figure labels, references), just translate directly without explanation.\n" +
    "7. Keep proper nouns, model names, and technical terms (e.g. Transformer, KV Cache, LLM) in English within the Chinese translation."
  )
  const [outputFormat, setOutputFormat] = useState<"bilingual" | "target_only">("bilingual")
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [enableOcr, setEnableOcr] = useState(false)
  const [ocrMarkdown, setOcrMarkdown] = useState("")
  const [viewTab, setViewTab] = useState<"llm" | "ocr">("llm")

  // 翻译历史
  const [translationId, setTranslationId] = useState<string | null>(null)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)

  // 异步翻译任务
  const [taskId, setTaskId] = useState<string | null>(null)

  // 可拖拽分隔条
  const [qaWidth, setQaWidth] = useState(320)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // 当 context 中的 profileNames/bindings 变化时，自动选中合适的档案
  useEffect(() => {
    if (!selectedProfile || !profileNames.includes(selectedProfile)) {
      const bound = bindings?.translation
      if (bound && profileNames.includes(bound)) setSelectedProfile(bound)
      else if (profileNames.length > 0) setSelectedProfile(profileNames[0])
    }
  }, [profileNames, bindings, selectedProfile])

  // 拖拽事件
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

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

  const handleUpload = async (file: File) => {
    const prof = profileMap[selectedProfile]
    if (!prof) { setError("请先在侧边栏配置并选择 LLM 档案"); return }
    setLoading(true); setError(""); setMarkdown(""); setOcrMarkdown("")
    setTaskId(null); setTranslationId(null)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const config: ModelConfig = {
        provider: prof.provider as ModelConfig["provider"],
        model: prof.model,
      }
      const uploadResult = await uploadPDF(file, config, systemPrompt, enableOcr, controller.signal)

      // 新的异步模式：后端返回 {task_id, status: "processing"}
      const tid = (uploadResult as any).task_id
      if (tid && (uploadResult as any).status === "processing") {
        // 设置 taskId，TranslationProgress 组件会自动连接 SSE
        setTaskId(tid)
      } else {
        // 兼容旧的同步模式（如果后端返回了 markdown）
        const result = uploadResult as any
        setMarkdown(result.markdown || "")
        setOcrMarkdown(result.ocr_markdown || "")
        setTranslationId(result.translation_id || null)
        setViewTab("llm")
        setHistoryRefreshKey(k => k + 1)
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

  // SSE 完成回调：获取翻译结果
  const handleTranslationComplete = useCallback(async () => {
    if (!taskId) return
    try {
      const result = await getTranslationResult(taskId)
      setMarkdown(result.markdown || result.translated_md || "")
      setOcrMarkdown(result.ocr_markdown || "")
      setTranslationId(result.translation_id || null)
      setViewTab("llm")
      setHistoryRefreshKey(k => k + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取翻译结果失败")
    } finally {
      setLoading(false)
      setTaskId(null)
    }
  }, [taskId])

  // SSE 错误回调
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
    } catch { /* ignore */ }
    setLoading(false)
    setTaskId(null)
  }

  const handleSelectHistory = async (entry: TranslationEntry) => {
    try {
      setLoading(true)
      setError("")
      const data = await getTranslation(entry.id)
      setMarkdown(data.markdown || "")
      setOcrMarkdown(data.ocr_markdown || "")
      setTranslationId(entry.id)
      setViewTab("llm")
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div ref={containerRef} className="flex h-screen overflow-hidden">
      {/* ── 侧边栏 ── */}
      <Sidebar
        collapsed={!sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        systemPrompt={systemPrompt}
        onSystemPromptChange={setSystemPrompt}
        outputFormat={outputFormat}
        onOutputFormatChange={setOutputFormat}
        onSelectHistory={handleSelectHistory}
        historyRefreshKey={historyRefreshKey}
      />

      {/* ── 文档区域（自适应剩余宽度） ── */}
      <main className="flex-1 flex flex-col min-w-0 bg-gray-50">
        {/* 顶栏 */}
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
              {profileNames.map((n) => (
                <option key={n} value={n}>
                  {n}{profileMap[n] ? ` · ${profileMap[n].provider}` : ""}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={enableOcr}
                onChange={(e) => setEnableOcr(e.target.checked)}
                className="rounded text-teal-600 focus:ring-teal-500"
              />
              <span className="text-xs text-gray-500">OCR</span>
            </label>
          </div>
          <UploadButton onUpload={handleUpload} disabled={loading} />
        </header>

        {/* 文档内容 */}
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
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.8}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-sm font-medium text-gray-400">上传 PDF 文档开始翻译</p>
              <p className="text-xs text-gray-300 mt-1">支持学术论文、技术文档等</p>
            </div>
          )}

          {markdown && !loading && (
            <>
              {ocrMarkdown && (
                <div className="flex gap-1 mb-4">
                  <button onClick={() => setViewTab("llm")}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
                      viewTab === "llm"
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                    }`}>双语翻译</button>
                  <button onClick={() => setViewTab("ocr")}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
                      viewTab === "ocr"
                        ? "bg-teal-600 text-white"
                        : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                    }`}>OCR 原文</button>
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

      {/* ── 可拖拽分隔条 ── */}
      <div
        onMouseDown={handleMouseDown}
        className={`w-1 flex-shrink-0 cursor-col-resize group relative transition-colors ${
          isDragging ? "bg-indigo-400" : "bg-gray-200 hover:bg-indigo-300"
        }`}
      >
        <div className="absolute inset-y-0 -left-1 -right-1 z-10" />
        <div className={`absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2 w-1 h-8 rounded-full transition-colors ${
          isDragging ? "bg-indigo-500" : "bg-gray-300 group-hover:bg-indigo-400"
        }`} />
      </div>

      {/* ── QA 问答面板（可拖拽宽度） ── */}
      <aside
        style={{ width: qaWidth }}
        className="flex-shrink-0 flex flex-col bg-white"
      >
        <QAPanel />
      </aside>
    </div>
  )
}
