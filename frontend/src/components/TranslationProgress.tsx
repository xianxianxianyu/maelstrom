"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { connectTranslationSSE, TranslationSSEEvent } from "@/lib/api"

interface Props {
  taskId: string
  onComplete?: () => void
  onError?: (error: string) => void
}

// Agent 阶段定义
interface AgentPhase {
  id: string
  label: string
  icon: string
  progressRange: [number, number] // [start, end]
}

const AGENT_PHASES: AgentPhase[] = [
  { id: "terminology", label: "术语准备", icon: "📚", progressRange: [0, 15] },
  { id: "ocr", label: "文档解析", icon: "📄", progressRange: [16, 25] },
  { id: "translation", label: "翻译", icon: "🌐", progressRange: [26, 70] },
  { id: "review", label: "质量审校", icon: "✅", progressRange: [71, 85] },
  { id: "saving", label: "保存", icon: "💾", progressRange: [86, 100] },
]

const AGENT_LABELS: Record<string, string> = {
  system: "系统",
  orchestrator: "编排",
  ocr: "解析",
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
  parsing: "解析 PDF",
  preprocessing: "预处理",
  ocr_recognizing: "OCR 识别",
  skip: "复用缓存",
  prompt_generation: "生成 Prompt",
  translating: "翻译中",
  review: "质量审校",
  terminology_check: "检查术语一致性",
  format_check: "检查格式完整性",
  untranslated_check: "检测未翻译段落",
  auto_fix: "自动修正",
  saving: "保存结果",
  complete: "已完成",
  error: "出错",
}

interface LogEntry {
  time: string
  agent: string
  message: string
}

const MAX_LOG_ENTRIES = 50

export function TranslationProgress({ taskId, onComplete, onError }: Props) {
  const [event, setEvent] = useState<TranslationSSEEvent | null>(null)
  const [connected, setConnected] = useState(false)
  const [complete, setComplete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [currentPhaseIndex, setCurrentPhaseIndex] = useState(0)
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

  // 根据 agent 更新当前阶段
  const updatePhase = useCallback((agent: string, progress: number) => {
    const phaseMap: Record<string, number> = {
      terminology: 0,
      ocr: 1,
      translation: 2,
      review: 3,
    }
    if (agent in phaseMap) {
      setCurrentPhaseIndex(phaseMap[agent])
    } else if (agent === "orchestrator") {
      // orchestrator 的 saving 阶段
      if (progress >= 86) {
        setCurrentPhaseIndex(4)
      }
    }
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

        // 更新阶段
        updatePhase(data.agent, data.progress)

        // 构建日志
        const agentLabel = AGENT_LABELS[data.agent] || data.agent
        const stageLabel = STAGE_LABELS[data.stage] || data.stage
        const detailMsg = data.detail?.message
        const logMsg = detailMsg || `[${stageLabel}] ${data.progress >= 0 ? data.progress + "%" : ""}`
        addLog(agentLabel, logMsg)

        if (data.stage === "complete" && data.agent === "orchestrator") {
          setComplete(true)
          setCurrentPhaseIndex(AGENT_PHASES.length)
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
        if (retriesRef.current < 3 && !complete) {
          const delay = 1000 * Math.pow(2, retriesRef.current)
          retriesRef.current += 1
          setTimeout(connect, delay)
        } else if (retriesRef.current >= 3) {
          setError("连接已断开，重试次数已用尽")
        }
      },
    )
    esRef.current = es
  }, [taskId, complete, addLog, updatePhase, onComplete, onError])

  useEffect(() => {
    connect()
    return () => { esRef.current?.close() }
  }, [connect])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs])

  const progress = event ? (event.progress >= 0 ? event.progress : (complete ? 100 : 0)) : 0
  const statusMessage = event?.detail?.message || STAGE_LABELS[event?.stage || ""] || "等待连接"

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-4 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">翻译进度</h3>
        <span className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${
              complete ? "bg-green-500" : connected ? "bg-green-400 animate-pulse" : error ? "bg-red-400" : "bg-yellow-400 animate-pulse"
            }`}
          />
          <span className="text-xs text-gray-400">
            {complete ? "完成" : connected ? "已连接" : error ? "断开" : "连接中"}
          </span>
        </span>
      </div>

      {/* Agent Phase Steps */}
      <div className="flex items-center justify-between px-2">
        {AGENT_PHASES.map((phase, idx) => {
          const isActive = idx === currentPhaseIndex
          const isDone = idx < currentPhaseIndex || complete

          return (
            <div key={phase.id} className="flex flex-col items-center flex-1">
              {/* Step indicator */}
              <div className="flex items-center w-full">
                {idx > 0 && (
                  <div className={`flex-1 h-0.5 ${isDone ? "bg-green-400" : "bg-gray-200"}`} />
                )}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm transition-all ${
                    isDone
                      ? "bg-green-100 text-green-600"
                      : isActive
                        ? "bg-indigo-100 text-indigo-600 ring-2 ring-indigo-400 ring-offset-1"
                        : "bg-gray-100 text-gray-400"
                  }`}
                >
                  {isDone ? "✓" : phase.icon}
                </div>
                {idx < AGENT_PHASES.length - 1 && (
                  <div className={`flex-1 h-0.5 ${isDone ? "bg-green-400" : "bg-gray-200"}`} />
                )}
              </div>
              {/* Label */}
              <span
                className={`mt-1.5 text-xs font-medium ${
                  isDone ? "text-green-600" : isActive ? "text-indigo-600" : "text-gray-400"
                }`}
              >
                {phase.label}
              </span>
            </div>
          )
        })}
      </div>

      {/* Status message */}
      <div className="text-sm text-gray-800 font-medium min-h-[1.5rem] text-center">
        {statusMessage}
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${
            complete ? "bg-green-500" : error ? "bg-red-400" : "bg-indigo-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Progress percentage */}
      <div className="flex justify-between text-xs text-gray-500">
        <span>
          Agent: <span className="font-medium text-gray-700">{AGENT_LABELS[event?.agent || ""] || "—"}</span>
        </span>
        <span className="font-semibold text-gray-700">{progress}%</span>
      </div>

      {/* Event log (collapsible) */}
      <details className="group">
        <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1">
          <svg className="w-3 h-3 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          事件日志 ({logs.length})
        </summary>
        <div className="mt-2 max-h-40 overflow-y-auto rounded border border-gray-100 bg-gray-50 p-2 text-xs font-mono space-y-0.5">
          {logs.map((log, i) => (
            <div key={i} className="flex gap-2 leading-relaxed">
              <span className="text-gray-400 flex-shrink-0">{log.time}</span>
              <span className="text-indigo-500 flex-shrink-0 w-8 text-right">{log.agent}</span>
              <span className="text-gray-600 break-all">{log.message}</span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </details>

      {/* Error */}
      {error && <p className="text-xs text-red-500">{error}</p>}

      {/* Complete */}
      {complete && (
        <div className="flex items-center justify-center gap-1.5 text-sm text-green-600 font-medium">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          翻译完成
        </div>
      )}
    </div>
  )
}
