"use client"

import { useState, useRef, useEffect } from "react"
import { cn } from "@/lib/utils"

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  citations?: Array<{
    text: string
    source: string
  }>
  timestamp: Date
}

interface ChatAreaProps {
  messages: Message[]
  isLoading: boolean
  onSendMessage: (content: string) => void
  selectedProfile: string
}

export function ChatArea({
  messages,
  isLoading,
  onSendMessage,
  selectedProfile,
}: ChatAreaProps) {
  const [input, setInput] = useState("")
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // 自动调整文本框高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`
    }
  }, [input])

  const handleSend = () => {
    const content = input.trim()
    if (!content || isLoading || !selectedProfile) return

    onSendMessage(content)
    setInput("")

    // 重置文本框高度
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex-1 flex flex-col bg-white min-w-0">
      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-500">开始新的对话</p>
            <p className="text-xs text-gray-400 mt-1">输入问题，我帮你解答</p>
          </div>
        ) : (
          messages.map((message, index) => (
            <MessageBubble
              key={message.id}
              message={message}
              isLast={index === messages.length - 1}
            />
          ))
        )}

        {/* 加载状态 */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入区域 */}
      <div className="border-t border-gray-200 p-4">
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={selectedProfile ? "输入问题，Enter 发送，Shift+Enter 换行..." : "请先选择模型档案..."}
              disabled={!selectedProfile || isLoading}
              rows={1}
              className={cn(
                "w-full px-4 py-3 pr-10 bg-gray-50 border border-gray-200 rounded-xl",
                "text-sm text-gray-800 placeholder:text-gray-400",
                "focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500",
                "resize-none overflow-hidden",
                (!selectedProfile || isLoading) && "opacity-60 cursor-not-allowed"
              )}
              style={{ minHeight: "48px", maxHeight: "120px" }}
            />

            {/* 发送按钮 */}
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading || !selectedProfile}
              className={cn(
                "absolute right-2 bottom-2 p-2 rounded-lg transition-all",
                input.trim() && selectedProfile && !isLoading
                  ? "bg-indigo-600 text-white hover:bg-indigo-700 shadow-md"
                  : "bg-gray-200 text-gray-400 cursor-not-allowed"
              )}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>

        {/* 提示文字 */}
        <p className="text-xs text-gray-400 mt-2 text-center">
          基于当前文档内容进行问答 · AI 生成内容仅供参考
        </p>
      </div>
    </div>
  )
}

// 消息气泡组件
interface MessageBubbleProps {
  message: Message
  isLast: boolean
}

function MessageBubble({ message, isLast }: MessageBubbleProps) {
  const isUser = message.role === "user"
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // 忽略复制错误
    }
  }

  // 简单的 Markdown 渲染
  const renderContent = (content: string) => {
    // 处理代码块
    const parts = content.split(/(```[\s\S]*?```)/g)
    
    return parts.map((part, index) => {
      if (part.startsWith('```') && part.endsWith('```')) {
        // 代码块
        const code = part.slice(3, -3).trim()
        const firstLine = code.split('\n')[0]
        const language = firstLine && !code.startsWith(firstLine + '\n') ? firstLine : ''
        const codeContent = language ? code.slice(language.length).trim() : code
        
        return (
          <pre key={index} className="bg-gray-900 text-gray-100 p-3 rounded-lg overflow-x-auto my-2 text-xs">
            {language && <div className="text-gray-400 mb-1">{language}</div>}
            <code>{codeContent}</code>
          </pre>
        )
      }
      
      // 普通文本 - 处理行内代码
      const formatted = part
        .split(/(`[^`]+`)/g)
        .map((segment, segIndex) => {
          if (segment.startsWith('`') && segment.endsWith('`')) {
            return (
              <code key={segIndex} className={cn(
                "px-1 py-0.5 rounded text-xs font-mono",
                isUser ? "bg-white/20" : "bg-gray-200"
              )}>
                {segment.slice(1, -1)}
              </code>
            )
          }
          return segment
        })
      
      return <span key={index}>{formatted}</span>
    })
  }

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] group",
          isUser ? "items-end" : "items-start"
        )}
      >
        {/* 消息头部信息 */}
        <div className={cn("flex items-center gap-2 mb-1", isUser ? "justify-end" : "justify-start")}>
          {!isUser && (
            <div className="w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
          )}
          <span className="text-xs text-gray-400">
            {isUser ? "你" : "AI 助手"}
          </span>
          <span className="text-xs text-gray-300">
            {new Date(message.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>

        {/* 消息内容气泡 */}
        <div
          className={cn(
            "relative rounded-2xl px-4 py-3 text-sm leading-relaxed",
            isUser
              ? "bg-indigo-600 text-white rounded-br-md"
              : "bg-gray-100 text-gray-800 rounded-bl-md"
          )}
        >
          {/* 消息内容 */}
          <div className="whitespace-pre-wrap break-words">
            {renderContent(message.content)}
          </div>

          {/* 引用来源 */}
          {!isUser && message.citations && message.citations.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-200/50">
              <p className="text-xs text-gray-500 mb-2">引用来源：</p>
              <div className="flex flex-wrap gap-2">
                {message.citations.map((citation, index) => (
                  <button
                    key={index}
                    onClick={() => {
                      // TODO: 跳转到文档对应位置
                      alert(`来源：${citation.source}\n\n${citation.text}`)
                    }}
                    className="text-xs px-2 py-1 bg-white/50 hover:bg-white text-indigo-600 rounded transition-colors"
                  >
                    📄 {citation.source}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 操作按钮（复制） */}
          <div
            className={cn(
              "absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity",
              isUser ? "text-white/70 hover:text-white" : "text-gray-400 hover:text-gray-600"
            )}
          >
            <button
              onClick={handleCopy}
              className="p-1.5 rounded-md hover:bg-black/10 transition-colors"
              title={copied ? "已复制" : "复制内容"}
            >
              {copied ? (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
