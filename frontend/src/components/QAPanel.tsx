"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { askQuestion, QAResponse } from "@/lib/api"
import { useLLMConfig } from "@/contexts/LLMConfigContext"

interface Citation {
  text: string
  source: string
}

interface Message {
  role: "user" | "assistant"
  content: string
  citations?: Citation[]
}

interface Props {
  docId?: string
}

function generateSessionId(): string {
  return "sess_" + Math.random().toString(36).substring(2, 15) + Date.now().toString(36)
}

export function QAPanel({ docId }: Props) {
  const { profileNames, bindings } = useLLMConfig()
  const [selectedProfile, setSelectedProfile] = useState("")
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const sessionId = useMemo(() => generateSessionId(), [])

  // 当 context 中的 profileNames/bindings 变化时，自动选中合适的档案
  useEffect(() => {
    if (!selectedProfile || !profileNames.includes(selectedProfile)) {
      const bound = bindings?.qa
      if (bound && profileNames.includes(bound)) setSelectedProfile(bound)
      else if (profileNames.length > 0) setSelectedProfile(profileNames[0])
    }
  }, [profileNames, bindings, selectedProfile])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleSend = async () => {
    const q = input.trim()
    if (!q || !selectedProfile || loading) return
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content: q }])
    setLoading(true)
    try {
      const res: QAResponse = await askQuestion(q, selectedProfile, undefined, sessionId, docId)
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: res.answer,
        citations: res.citations,
      }])
    } catch (err: any) {
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: `❌ 调用失败: ${err.message || "未知错误"}`,
      }])
    } finally { setLoading(false) }
  }

  return (
    <>
      {/* 顶栏 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-700">问答</h2>
        <select
          value={selectedProfile}
          onChange={(e) => setSelectedProfile(e.target.value)}
          className="px-2 py-1 text-xs border border-gray-200 rounded-md bg-gray-50 focus:ring-1 focus:ring-indigo-300 text-gray-600 max-w-[120px]"
        >
          <option value="">选择档案</option>
          {profileNames.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </div>

      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-300">
            <svg className="w-10 h-10 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <p className="text-xs">输入问题开始对话</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i}>
            <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed ${
                msg.role === "user"
                  ? "bg-indigo-600 text-white rounded-br-sm"
                  : "bg-gray-100 text-gray-700 rounded-bl-sm"
              }`}>
                <div className="whitespace-pre-wrap">{msg.content}</div>
              </div>
            </div>
            {/* 引用来源 */}
            {msg.role === "assistant" && msg.citations && msg.citations.length > 0 && (
              <div className="flex justify-start mt-1 ml-1">
                <div className="max-w-[85%] space-y-0.5">
                  <p className="text-[10px] text-gray-400 font-medium">引用来源:</p>
                  {msg.citations.map((cite, j) => (
                    <button
                      key={j}
                      className="block text-[10px] text-indigo-500 hover:text-indigo-700 hover:underline transition truncate max-w-full text-left"
                      title={cite.text}
                      onClick={() => {
                        // 滚动到引用或展示引用内容
                        alert(`引用来源: ${cite.source}\n\n${cite.text}`)
                      }}
                    >
                      📄 {cite.source}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 text-gray-400 px-3 py-2 rounded-xl rounded-bl-sm text-xs">
              <span className="inline-flex gap-1">
                <span className="animate-bounce">.</span>
                <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>.</span>
                <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>.</span>
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区域 */}
      <div className="border-t border-gray-200 p-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder="输入问题..."
            disabled={!selectedProfile}
            className="flex-1 px-3 py-2 text-xs border border-gray-200 rounded-lg focus:ring-1 focus:ring-indigo-300 bg-gray-50 disabled:bg-gray-100"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim() || !selectedProfile}
            className="px-3 py-2 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </div>
      </div>
    </>
  )
}
