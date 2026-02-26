"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Message, Session } from "@/components/qa/types"
import { useLLMConfig } from "@/contexts/LLMConfigContext"
import { askQuestionV2 } from "@/lib/api"

function generateId(): string {
  return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

function generateTitle(content: string): string {
  const clean = content.replace(/\n/g, " ").replace(/\s+/g, " ").trim()
  return clean.length > 20 ? clean.slice(0, 20) + "..." : clean || "新会话"
}

const STORAGE_KEY = "qa_sessions"
const CURRENT_SESSION_KEY = "qa_current_session"

interface UseQASessionOptions {
  docId?: string
}

export function useQASession(options: UseQASessionOptions = {}) {
  const { docId } = options
  const { profileNames } = useLLMConfig()

  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [selectedProfile, setSelectedProfile] = useState<string>("")

  const abortControllerRef = useRef<AbortController | null>(null)

  // 从 localStorage 加载会话
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        const restored: Session[] = parsed.map((s: any) => ({
          ...s,
          createdAt: new Date(s.createdAt),
          updatedAt: new Date(s.updatedAt),
        }))
        setSessions(restored)
      }

      const savedCurrent = localStorage.getItem(CURRENT_SESSION_KEY)
      if (savedCurrent) {
        setCurrentSessionId(savedCurrent)
      }
    } catch {
      // 忽略错误
    }
  }, [])

  // 保存会话到 localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
    } catch {
      // 忽略错误
    }
  }, [sessions])

  // 保存当前会话 ID
  useEffect(() => {
    try {
      if (currentSessionId) {
        localStorage.setItem(CURRENT_SESSION_KEY, currentSessionId)
      } else {
        localStorage.removeItem(CURRENT_SESSION_KEY)
      }
    } catch {
      // 忽略错误
    }
  }, [currentSessionId])

  // 当前会话
  const currentSession = sessions.find((s) => s.id === currentSessionId) || null

  // 创建新会话
  const createSession = useCallback(() => {
    const newSession: Session = {
      id: generateId(),
      title: "新会话",
      createdAt: new Date(),
      updatedAt: new Date(),
      docId,
    }
    setSessions((prev) => [newSession, ...prev])
    setCurrentSessionId(newSession.id)
    setMessages([])
    return newSession.id
  }, [docId])

  // 切换会话
  const switchSession = useCallback(
    (sessionId: string) => {
      setCurrentSessionId(sessionId)
      // 加载该会话的消息
      const session = sessions.find((s) => s.id === sessionId)
      if (session) {
        // 这里可以从服务器加载历史消息
        setMessages([])
      }
    },
    [sessions]
  )

  // 删除会话
  const deleteSession = useCallback(
    (sessionId: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null)
        setMessages([])
      }
    },
    [currentSessionId]
  )

  // 发送消息
  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return

      // 确保有当前会话
      let sessionId = currentSessionId
      if (!sessionId) {
        sessionId = createSession()
      }

      // 添加用户消息
      const userMessage: Message = {
        id: generateId(),
        role: "user",
        content: content.trim(),
        timestamp: new Date(),
      }

      setMessages((prev) => [...prev, userMessage])
      setIsLoading(true)

      // 更新会话标题（如果是第一条消息）
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                title: s.title === "新会话" ? generateTitle(content) : s.title,
                updatedAt: new Date(),
              }
            : s
        )
      )

      try {
        // 创建 AbortController 用于取消请求
        abortControllerRef.current = new AbortController()

        const response = await askQuestionV2(
          {
            query: content.trim(),
            docId,
            sessionId: sessionId || undefined,
            options: { timeout_sec: 12, max_context_chars: 8000 },
          },
          abortControllerRef.current.signal,
        )

        const assistantMessage: Message = {
          id: generateId(),
          role: "assistant",
          content: response.answer || "",
          citations: (response.citations || []).map((citation) => ({
            text: citation.text,
            source: citation.chunkId,
          })),
          timestamp: new Date(),
          isStreaming: false,
        }

        setMessages((prev) => [...prev, assistantMessage])
      } catch (error: any) {
        if (error.name === "AbortError") {
          // 用户取消，不显示错误
          return
        }

        // 添加错误消息
        const errorMessage: Message = {
          id: generateId(),
          role: "assistant",
          content: `抱歉，发生了错误：${error.message || "未知错误"}`,
          timestamp: new Date(),
        }
        setMessages((prev) => [...prev, errorMessage])
      } finally {
        setIsLoading(false)
        abortControllerRef.current = null
      }
    },
    [
      currentSessionId,
      createSession,
      messages,
      selectedProfile,
      docId,
    ]
  )

  // 清除消息
  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  // 取消当前请求
  const cancelRequest = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsLoading(false)
    }
  }, [])

  return {
    sessions,
    currentSession,
    currentSessionId,
    messages,
    isLoading,
    selectedProfile,
    profileNames,
    setSelectedProfile,
    createSession,
    switchSession,
    deleteSession,
    sendMessage,
    clearMessages,
    cancelRequest,
  }
}
