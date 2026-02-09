"use client"

import { LLMConfigPanel } from "./LLMConfigPanel"
import { OCRConfigPanel } from "./OCRConfigPanel"
import { HistoryList } from "./HistoryList"
import { TranslationEntry } from "@/types"

type SidebarTab = "history" | "llm" | "ocr" | "settings"

interface Props {
  collapsed: boolean
  onToggle: () => void
  systemPrompt: string
  onSystemPromptChange: (v: string) => void
  outputFormat: "bilingual" | "target_only"
  onOutputFormatChange: (v: "bilingual" | "target_only") => void
  onSelectHistory: (entry: TranslationEntry) => void
  historyRefreshKey?: number
}

import { useState } from "react"

export function Sidebar({
  collapsed, onToggle,
  systemPrompt, onSystemPromptChange,
  outputFormat, onOutputFormatChange,
  onSelectHistory, historyRefreshKey,
}: Props) {
  const [activeTab, setActiveTab] = useState<SidebarTab>("history")

  return (
    <aside
      className={`relative flex-shrink-0 h-full bg-white border-r border-gray-200 flex flex-col transition-all duration-300 ease-in-out ${
        collapsed ? "w-14" : "w-72"
      }`}
    >
      {/* 折叠按钮 */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-5 z-10 w-6 h-6 bg-white border border-gray-200 rounded-full shadow-sm flex items-center justify-center hover:bg-gray-50 hover:shadow transition"
      >
        <svg
          className={`w-3 h-3 text-gray-400 transition-transform duration-300 ${collapsed ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {collapsed ? (
        /* 折叠态：只显示图标 */
        <div className="flex flex-col items-center pt-5 gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center mb-2">
            <span className="text-indigo-600 text-xs font-bold">P</span>
          </div>
          <button onClick={() => { onToggle(); setActiveTab("history") }}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition" title="历史记录">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
          <button onClick={() => { onToggle(); setActiveTab("llm") }}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition" title="LLM 档案">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            </svg>
          </button>
          <button onClick={() => { onToggle(); setActiveTab("ocr") }}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition" title="OCR 档案">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          </button>
          <button onClick={() => { onToggle(); setActiveTab("settings") }}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition" title="设置">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
            </svg>
          </button>
        </div>
      ) : (
        <>
          {/* 品牌标题 */}
          <div className="h-14 flex items-center gap-2.5 px-5 border-b border-gray-100 flex-shrink-0">
            <div className="w-7 h-7 rounded-lg bg-indigo-50 flex items-center justify-center">
              <span className="text-indigo-600 text-xs font-bold">P</span>
            </div>
            <span className="text-sm font-semibold text-gray-800 tracking-tight">PDF Translator</span>
          </div>

          {/* Tab 切换 */}
          <div className="flex border-b border-gray-100 px-4 flex-shrink-0">
            {([
              { key: "history" as SidebarTab, label: "历史" },
              { key: "llm" as SidebarTab, label: "LLM 档案" },
              { key: "ocr" as SidebarTab, label: "OCR 档案" },
              { key: "settings" as SidebarTab, label: "设置" },
            ]).map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex-1 py-2.5 text-xs font-medium text-center transition-all ${
                  activeTab === tab.key
                    ? "text-indigo-600 border-b-2 border-indigo-600"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab 内容 */}
          <div className="flex-1 overflow-y-auto">
            {activeTab === "history" && <HistoryList onSelect={onSelectHistory} refreshKey={historyRefreshKey} />}
            {activeTab === "llm" && <LLMConfigPanel />}
            {activeTab === "ocr" && <OCRConfigPanel />}
            {activeTab === "settings" && (
              <div className="p-4 space-y-5">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1.5">System Prompt</label>
                  <textarea
                    value={systemPrompt}
                    onChange={(e) => onSystemPromptChange(e.target.value)}
                    rows={6}
                    className="w-full px-3 py-2 text-xs leading-relaxed border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 outline-none resize-y bg-gray-50/50 transition"
                    placeholder="翻译系统提示词..."
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-2.5">输出格式</label>
                  <div className="space-y-2">
                    {([
                      { value: "bilingual" as const, label: "双语对照", desc: "原文与译文并排显示" },
                      { value: "target_only" as const, label: "仅目标语言", desc: "只显示翻译结果" },
                    ]).map((opt) => (
                      <label key={opt.value}
                        className={`flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition ${
                          outputFormat === opt.value
                            ? "border-indigo-200 bg-indigo-50/50"
                            : "border-gray-100 hover:border-gray-200"
                        }`}>
                        <input type="radio" name="outputFormat" value={opt.value}
                          checked={outputFormat === opt.value}
                          onChange={() => onOutputFormatChange(opt.value)}
                          className="mt-0.5 text-indigo-600 focus:ring-indigo-500"
                        />
                        <div>
                          <div className="text-xs font-medium text-gray-700">{opt.label}</div>
                          <div className="text-[10px] text-gray-400 mt-0.5">{opt.desc}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </aside>
  )
}
