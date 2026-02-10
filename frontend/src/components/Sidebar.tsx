"use client"

import { LLMConfigPanel } from "./LLMConfigPanel"
import { OCRConfigPanel } from "./OCRConfigPanel"
import { HistoryList } from "./HistoryList"
import { TranslationEntry } from "@/types"
import { useReaderSettings, FONT_OPTIONS, ContentWidth } from "@/contexts/ReaderSettingsContext"

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
            <span className="text-indigo-600 text-xs font-bold">M</span>
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
              <span className="text-indigo-600 text-xs font-bold">M</span>
            </div>
            <span className="text-sm font-semibold text-gray-800 tracking-tight">Maelstrom</span>
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
              <SettingsPanel
                systemPrompt={systemPrompt}
                onSystemPromptChange={onSystemPromptChange}
                outputFormat={outputFormat}
                onOutputFormatChange={onOutputFormatChange}
              />
            )}
          </div>
        </>
      )}
    </aside>
  )
}

/* ── 设置面板（阅读偏好 + 翻译设置） ── */

const WIDTH_OPTIONS: { value: ContentWidth; label: string; desc: string }[] = [
  { value: "compact", label: "紧凑", desc: "680px" },
  { value: "standard", label: "标准", desc: "860px" },
  { value: "wide", label: "宽屏", desc: "不限制" },
]

const CATEGORY_LABELS: Record<string, string> = {
  system: "系统",
  sans: "无衬线",
  serif: "衬线",
  mono: "等宽",
}

function SettingsPanel({
  systemPrompt, onSystemPromptChange,
  outputFormat, onOutputFormatChange,
}: {
  systemPrompt: string
  onSystemPromptChange: (v: string) => void
  outputFormat: "bilingual" | "target_only"
  onOutputFormatChange: (v: "bilingual" | "target_only") => void
}) {
  const rs = useReaderSettings()

  // 按 category 分组
  const grouped = FONT_OPTIONS.reduce<Record<string, typeof FONT_OPTIONS>>((acc, f) => {
    (acc[f.category] ??= []).push(f)
    return acc
  }, {})

  return (
    <div className="p-4 space-y-5">
      {/* ── 阅读偏好 ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-gray-700 tracking-wide">阅读偏好</span>
          <button onClick={rs.reset}
            className="text-[10px] text-gray-400 hover:text-indigo-500 transition">
            恢复默认
          </button>
        </div>

        {/* 字体选择 */}
        <label className="block text-[11px] font-medium text-gray-500 mb-1">字体</label>
        <select
          value={rs.fontValue}
          onChange={(e) => rs.setFontValue(e.target.value)}
          className="w-full px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50/50 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 outline-none transition mb-3"
        >
          {Object.entries(grouped).map(([cat, fonts]) => (
            <optgroup key={cat} label={CATEGORY_LABELS[cat] || cat}>
              {fonts.map(f => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </optgroup>
          ))}
        </select>

        {/* 字体预览 */}
        <div
          className="px-3 py-2 mb-3 rounded-lg border border-gray-100 bg-gray-50/50 text-gray-600 leading-relaxed"
          style={{ fontFamily: rs.fontFamily, fontSize: rs.fontSize, lineHeight: rs.lineHeight }}
        >
          <span className="text-[10px] text-gray-400 block mb-1" style={{ fontFamily: 'inherit' }}>预览</span>
          The quick brown fox jumps over the lazy dog.
          <br />
          中文排版效果：量子纠缠与贝尔不等式。
        </div>

        {/* 字体大小 */}
        <label className="block text-[11px] font-medium text-gray-500 mb-1">
          字号 <span className="text-gray-400 font-normal">{rs.fontSize}px</span>
        </label>
        <input type="range" min={12} max={24} step={1}
          value={rs.fontSize}
          onChange={(e) => rs.setFontSize(Number(e.target.value))}
          className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-indigo-500 mb-3"
        />

        {/* 行高 */}
        <label className="block text-[11px] font-medium text-gray-500 mb-1">
          行高 <span className="text-gray-400 font-normal">{rs.lineHeight.toFixed(1)}</span>
        </label>
        <input type="range" min={1.4} max={2.4} step={0.1}
          value={rs.lineHeight}
          onChange={(e) => rs.setLineHeight(Number(e.target.value))}
          className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-indigo-500 mb-3"
        />

        {/* 内容宽度 */}
        <label className="block text-[11px] font-medium text-gray-500 mb-1.5">内容宽度</label>
        <div className="flex gap-1.5">
          {WIDTH_OPTIONS.map(opt => (
            <button key={opt.value}
              onClick={() => rs.setContentWidth(opt.value)}
              className={`flex-1 py-1.5 text-[10px] font-medium rounded-lg border transition ${
                rs.contentWidth === opt.value
                  ? "border-indigo-200 bg-indigo-50 text-indigo-600"
                  : "border-gray-100 text-gray-400 hover:border-gray-200 hover:text-gray-500"
              }`}
            >
              {opt.label}
              <span className="block text-[9px] font-normal opacity-60">{opt.desc}</span>
            </button>
          ))}
        </div>
      </div>

      <hr className="border-gray-100" />

      {/* ── 翻译设置 ── */}
      <div>
        <span className="block text-xs font-semibold text-gray-700 tracking-wide mb-3">翻译设置</span>

        <label className="block text-[11px] font-medium text-gray-500 mb-1.5">System Prompt</label>
        <textarea
          value={systemPrompt}
          onChange={(e) => onSystemPromptChange(e.target.value)}
          rows={6}
          className="w-full px-3 py-2 text-xs leading-relaxed border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 outline-none resize-y bg-gray-50/50 transition"
          placeholder="翻译系统提示词..."
        />

        <label className="block text-[11px] font-medium text-gray-500 mt-3 mb-2">输出格式</label>
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
  )
}
