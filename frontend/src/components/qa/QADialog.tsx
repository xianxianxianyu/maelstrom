"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { cn } from "@/lib/utils"
import { SessionSidebar } from "./SessionSidebar"
import { ChatArea } from "./ChatArea"
import type { Message, Session } from "./types"

interface QADialogProps {
  isOpen: boolean
  isMinimized: boolean
  onClose: () => void
  onMinimize: () => void
  sessions: Session[]
  currentSession: Session | null
  messages: Message[]
  isLoading: boolean
  selectedProfile: string
  profileNames: string[]
  onProfileChange: (profile: string) => void
  onCreateSession: () => void
  onSwitchSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
  onSendMessage: (content: string) => void
  onRetryExecution?: (traceId: string) => void
  docId?: string
}

const DEFAULT_WIDTH = 900
const DEFAULT_HEIGHT = 600
const MIN_WIDTH = 600
const MIN_HEIGHT = 400

export function QADialog({
  isOpen,
  isMinimized,
  onClose,
  onMinimize,
  sessions,
  currentSession,
  messages,
  isLoading,
  selectedProfile,
  profileNames,
  onProfileChange,
  onCreateSession,
  onSwitchSession,
  onDeleteSession,
  onSendMessage,
  onRetryExecution,
  docId,
}: QADialogProps) {
  const [size, setSize] = useState({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT })
  const [isResizing, setIsResizing] = useState(false)
  const [showWelcome, setShowWelcome] = useState(true)
  const dialogRef = useRef<HTMLDivElement>(null)

  // 从 localStorage 恢复窗口大小
  useEffect(() => {
    const saved = localStorage.getItem("qa_dialog_size")
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        setSize({
          width: Math.max(MIN_WIDTH, Math.min(window.innerWidth * 0.9, parsed.width)),
          height: Math.max(MIN_HEIGHT, Math.min(window.innerHeight * 0.9, parsed.height)),
        })
      } catch {
        // 忽略解析错误
      }
    }
  }, [])

  // 保存窗口大小到 localStorage
  useEffect(() => {
    if (!isResizing) {
      localStorage.setItem("qa_dialog_size", JSON.stringify(size))
    }
  }, [size, isResizing])

  // 调整大小处理
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
    const startX = e.clientX
    const startY = e.clientY
    const startWidth = size.width
    const startHeight = size.height

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = Math.max(MIN_WIDTH, startWidth + e.clientX - startX)
      const newHeight = Math.max(MIN_HEIGHT, startHeight + e.clientY - startY)
      setSize({ width: newWidth, height: newHeight })
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)
  }, [size])

  // 计算对话框位置（居中显示）
  const getDialogPosition = () => {
    const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 1200
    const viewportHeight = typeof window !== "undefined" ? window.innerHeight : 800
    
    return {
      left: Math.max(20, (viewportWidth - size.width) / 2),
      top: Math.max(20, (viewportHeight - size.height) / 2),
    }
  }

  const dialogPos = getDialogPosition()

  if (isMinimized || !isOpen) return null

  return (
    <>
      {/* 遮罩层 */}
      <div
        className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40"
        onClick={onMinimize}
      />

      {/* 对话框 */}
      <div
        ref={dialogRef}
        className={cn(
          "fixed z-50 bg-white rounded-xl shadow-2xl overflow-hidden flex flex-col",
          isResizing && "select-none"
        )}
        style={{
          left: dialogPos.left,
          top: dialogPos.top,
          width: size.width,
          height: size.height,
        }}
      >
        {/* 标题栏 */}
        <div
          className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white flex-shrink-0"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-sm">文档问答助手</h3>
              <p className="text-xs text-indigo-200">基于当前文档内容回答</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* LLM 档案选择 */}
            <select
              value={selectedProfile}
              onChange={(e) => onProfileChange(e.target.value)}
              className="px-2 py-1 text-xs bg-white/10 border border-white/20 rounded text-white focus:outline-none focus:ring-2 focus:ring-white/30"
            >
              <option value="" className="text-gray-800">选择模型</option>
              {profileNames.map((name) => (
                <option key={name} value={name} className="text-gray-800">
                  {name}
                </option>
              ))}
            </select>

            {/* 最小化按钮 */}
            <button
              onClick={onMinimize}
              className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
              title="最小化"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
              </svg>
            </button>

            {/* 关闭按钮 */}
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-white/20 rounded-lg transition-colors"
              title="关闭"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 主内容区 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 左侧会话列表 */}
          <SessionSidebar
            sessions={sessions}
            currentSessionId={currentSession?.id || null}
            onCreateSession={onCreateSession}
            onSwitchSession={onSwitchSession}
            onDeleteSession={onDeleteSession}
          />

          {/* 右侧聊天区域 */}
          <ChatArea
            messages={messages}
            isLoading={isLoading}
            onSendMessage={onSendMessage}
            onRetryExecution={onRetryExecution}
            selectedProfile={selectedProfile}
          />
        </div>

        {/* 调整大小手柄 */}
        <div
          className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize z-10"
          onMouseDown={handleResizeStart}
          title="调整大小"
        >
          <svg
            className="w-full h-full text-gray-400"
            fill="currentColor"
            viewBox="0 0 16 16"
          >
            <path d="M10 10l6-6v6h-6z" />
          </svg>
        </div>
      </div>
    </>
  )
}
