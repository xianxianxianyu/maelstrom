"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Message, Session } from "@/components/qa/types"
import { useLLMConfig } from "@/contexts/LLMConfigContext"
import { askQuestion, QAResponse } from "@/lib/api"

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
  const { profileNames, bindings } = useLLMConfig()

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
        // 准备消息历史
        const messageHistory = [...messages, userMessage].map((m) => ({
          role: m.role,
          content: m.content,
        }))

        // 获取模型名称
        const modelName =
          selectedProfile && bindings[selectedProfile]
            ? bindings[selectedProfile].model
            : undefined

        // 创建 AbortController 用于取消请求
        abortControllerRef.current = new AbortController()

        // 添加空的 AI 消息用于流式输出
        const assistantMessage: Message = {
          id: generateId(),
          role: "assistant",
          content: "",
          timestamp: new Date(),
          isStreaming: true,
        }

        setMessages((prev) => [...prev, assistantMessage])

        // 调用 API
        const response = await askQuestion({
          question: content.trim(),
          messages: messageHistory,
          docId,
          profile: selectedProfile || undefined,
          model: modelName,
          signal: abortControllerRef.current.signal,
        })

        // 处理流式响应
        let fullContent = ""
        let citations: Array<{ text: string; source: string }> = []

        for await (const chunk of response) {
          if (chunk.content) {
            fullContent += chunk.content
            // 更新消息内容
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessage.id
                  ? { ...m, content: fullContent, isStreaming: true }
                  : m
              )
            )
          }

          if (chunk.citations) {
            citations = chunk.citations
          }
        }

        // 完成流式输出
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessage.id
              ? {
                  ...m,
                  content: fullContent,
                  citations,
                  isStreaming: false,
                }
              : m
          )
        )
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
      bindings,
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
