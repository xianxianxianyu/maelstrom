"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { connectTranslationSSE, TranslationSSEEvent } from "@/lib/api"

interface Props {
  taskId: string
  onComplete?: () => void
  onError?: (error: string) => void
}

const AGENT_LABELS: Record<string, string> = {
  system: "系统",
  orchestrator: "编排",
  translation: "翻译",
  review: "审校",
  terminology: "术语",
  pipeline: "管线",
}

const STAGE_LABELS: Record<string, string> = {
  connected: "已连接",
  heartbeat: "等待中",
  terminology: "术语准备",
  analysis: "文档分析",
  pipeline_selection: "选择管线",
  prompt_generation: "生成 Prompt",
  translating: "翻译中",
  review: "质量审校",
  auto_fix: "自动修正",
  saving: "保存结果",
  complete: "已完成",
  error: "出错",
  timeout: "超时",
  // pipeline-level stages
  ocr_start: "OCR 识别",
  ocr_done: "OCR 完成",
  preprocess: "预处理",
  prompt_generating: "分析术语",
  prompt_ready: "Prompt 就绪",
  segmented: "文本分段",
  pipeline_done: "管线完成",
  pdf_parsing: "解析 PDF",
  pdf_parsed: "PDF 已解析",
  translation: "翻译阶段",
}

interface LogEntry {
  time: string
  agent: string
  message: string
}

const MAX_RETRIES = 3
const BASE_DELAY = 1000
const MAX_LOG_ENTRIES = 30

export function TranslationProgress({ taskId, onComplete, onError }: Props) {
  const [event, setEvent] = useState<TranslationSSEEvent | null>(null)
  const [connected, setConnected] = useState(false)
  const [complete, setComplete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const retriesRef = useRef(0)
  const esRef = useRef<EventSource | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  const addLog = useCallback((agent: string, message: string) => {
    const now = new Date()
    const time = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`
    setLogs((prev) => {
      const next = [...prev, { time, agent, message }]
      return next.length > MAX_LOG_ENTRIES ? next.slice(-MAX_LOG_ENTRIES) : next
    })
  }, [])

  const connect = useCallback(() => {
    if (complete) return

    const es = connectTranslationSSE(
      taskId,
      (data) => {
        if (data.stage === "heartbeat") return
        setEvent(data)
        setConnected(true)
        setError(null)
        retriesRef.current = 0

        // Build log message
        const agentLabel = AGENT_LABELS[data.agent] || data.agent
        const stageLabel = STAGE_LABELS[data.stage] || data.stage
        const detailMsg = data.detail?.message
        const logMsg = detailMsg || `[${stageLabel}] ${data.progress >= 0 ? data.progress + "%" : ""}`
        addLog(agentLabel, logMsg)

        if (data.stage === "complete" && data.agent === "orchestrator") {
          setComplete(true)
          es.close()
          onComplete?.()
        }
        if (data.stage === "error") {
          setError(data.detail?.message || "翻译出错")
          es.close()
          onError?.(data.detail?.message || "翻译出错")
        }
      },
      () => {
        setConnected(false)
        es.close()
        if (retriesRef.current < MAX_RETRIES && !complete) {
          const delay = BASE_DELAY * Math.pow(2, retriesRef.current)
          retriesRef.current += 1
          setTimeout(connect, delay)
        } else if (retriesRef.current >= MAX_RETRIES) {
          setError("连接已断开，重试次数已用尽")
        }
      },
    )
    esRef.current = es
  }, [taskId, complete, addLog, onComplete, onError])

  useEffect(() => {
    connect()
    return () => { esRef.current?.close() }
  }, [connect])

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs])

  const progress = event ? (event.progress >= 0 ? event.progress : (complete ? 100 : 0)) : 0
  const agentLabel = event ? (AGENT_LABELS[event.agent] || event.agent) : "—"
  const stageLabel = event ? (STAGE_LABELS[event.stage] || event.stage) : "等待连接"
  const statusMessage = event?.detail?.message || stageLabel

  // Extract structured info from latest event
  const currentCount = event?.detail?.current
  const totalCount = event?.detail?.total

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">翻译进度</h3>
        <span className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${
              complete
                ? "bg-green-500"
                : connected
                  ? "bg-green-400 animate-pulse"
                  : error
                    ? "bg-red-400"
                    : "bg-yellow-400 animate-pulse"
            }`}
          />
          <span className="text-xs text-gray-400">
            {complete ? "完成" : connected ? "已连接" : error ? "断开" : "连接中"}
          </span>
        </span>
      </div>

      {/* Main status message */}
      <div className="text-sm text-gray-800 font-medium min-h-[1.5rem]">
        {statusMessage}
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${
            complete ? "bg-green-500" : error ? "bg-red-400" : "bg-indigo-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Info row */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <div className="flex items-center gap-3">
          <span>
            Agent: <span className="font-medium text-gray-700">{agentLabel}</span>
          </span>
          <span className="text-gray-300">|</span>
          <span>
            阶段: <span className="font-medium text-gray-700">{stageLabel}</span>
          </span>
          {currentCount !== undefined && totalCount !== undefined && (
            <>
              <span className="text-gray-300">|</span>
              <span className="font-medium text-indigo-600">
                {currentCount}/{totalCount}
              </span>
            </>
          )}
        </div>
        <span className="font-semibold text-gray-700">{progress}%</span>
      </div>

      {/* Event log */}
      {logs.length > 0 && (
        <div className="mt-2 max-h-36 overflow-y-auto rounded border border-gray-100 bg-gray-50 p-2 text-xs font-mono space-y-0.5">
          {logs.map((log, i) => (
            <div key={i} className="flex gap-2 leading-relaxed">
              <span className="text-gray-400 flex-shrink-0">{log.time}</span>
              <span className="text-indigo-500 flex-shrink-0 w-8 text-right">{log.agent}</span>
              <span className="text-gray-600 break-all">{log.message}</span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-500 mt-1">{error}</p>
      )}

      {/* Complete */}
      {complete && (
        <div className="flex items-center gap-1.5 text-xs text-green-600 mt-1">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          翻译完成
        </div>
      )}
    </div>
  )
}
