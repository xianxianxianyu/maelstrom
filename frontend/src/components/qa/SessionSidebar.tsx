"use client"

import { useState, useCallback } from "react"
import { cn } from "@/lib/utils"
import type { Session } from "./types"

interface SessionSidebarProps {
  sessions: Session[]
  currentSessionId: string | null
  onCreateSession: () => void
  onSwitchSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
}

export function SessionSidebar({
  sessions,
  currentSessionId,
  onCreateSession,
  onSwitchSession,
  onDeleteSession,
}: SessionSidebarProps) {
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  const formatTime = (date: Date) => {
    const now = new Date()
    const diff = now.getTime() - new Date(date).getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return "刚刚"
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days < 7) return `${days}天前`
    return new Date(date).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
  }

  const handleDeleteClick = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    if (confirmDeleteId === sessionId) {
      onDeleteSession(sessionId)
      setConfirmDeleteId(null)
    } else {
      setConfirmDeleteId(sessionId)
      // 3秒后自动取消确认状态
      setTimeout(() => {
        setConfirmDeleteId((prev) => (prev === sessionId ? null : prev))
      }, 3000)
    }
  }

  return (
    <div className="w-64 flex-shrink-0 bg-gray-50 border-r border-gray-200 flex flex-col">
      {/* 头部 */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center gap-2 text-gray-700 mb-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
            <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-sm">会话历史</h3>
            <p className="text-xs text-gray-500">{sessions.length} 个会话</p>
          </div>
        </div>

        {/* 新建会话按钮 */}
        <button
          onClick={onCreateSession}
          className={cn(
            "w-full flex items-center justify-center gap-2 px-4 py-2.5",
            "bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg",
            "text-sm font-medium transition-colors"
          )}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          新建会话
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {sessions.length === 0 ? (
          <div className="text-center py-8 text-gray-400">
            <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-sm">暂无会话</p>
            <p className="text-xs mt-1">点击上方按钮开始</p>
          </div>
        ) : (
          sessions.map((session) => {
            const isActive = currentSessionId === session.id
            const isHovered = hoveredSessionId === session.id
            const isConfirmingDelete = confirmDeleteId === session.id

            return (
              <div
                key={session.id}
                onClick={() => onSwitchSession(session.id)}
                onMouseEnter={() => setHoveredSessionId(session.id)}
                onMouseLeave={() => setHoveredSessionId(null)}
                className={cn(
                  "group relative flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-all",
                  isActive
                    ? "bg-indigo-50 border border-indigo-200"
                    : "hover:bg-gray-100 border border-transparent"
                )}
              >
                {/* 会话图标 */}
                <div
                  className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0",
                    isActive ? "bg-indigo-200 text-indigo-700" : "bg-gray-200 text-gray-500"
                  )}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>

                {/* 会话信息 */}
                <div className="flex-1 min-w-0">
                  <p
                    className={cn(
                      "text-sm font-medium truncate",
                      isActive ? "text-indigo-900" : "text-gray-700"
                    )}
                  >
                    {session.title}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {formatTime(session.updatedAt)}
                  </p>
                </div>

                {/* 删除按钮 */}
                {(isHovered || isConfirmingDelete) && (
                  <button
                    onClick={(e) => handleDeleteClick(e, session.id)}
                    className={cn(
                      "absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg transition-colors",
                      isConfirmingDelete
                        ? "bg-red-100 text-red-600 hover:bg-red-200"
                        : "bg-white shadow-sm text-gray-400 hover:text-red-500 hover:bg-red-50"
                    )}
                    title={isConfirmingDelete ? "再次点击确认删除" : "删除会话"}
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                )}

                {/* 当前会话指示器 */}
                {isActive && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-indigo-500 rounded-r-full" />
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
