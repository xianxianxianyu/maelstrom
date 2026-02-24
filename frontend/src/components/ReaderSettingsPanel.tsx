"use client"

import { useReaderSettings, FONT_OPTIONS, ContentWidth } from "@/contexts/ReaderSettingsContext"
import { useTranslationSettings } from "@/contexts/TranslationSettingsContext"

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

export function ReaderSettingsPanel() {
  const reader = useReaderSettings()
  const { systemPrompt, outputFormat, setSystemPrompt, setOutputFormat } = useTranslationSettings()

  const grouped = FONT_OPTIONS.reduce<Record<string, typeof FONT_OPTIONS>>((acc, font) => {
    (acc[font.category] ??= []).push(font)
    return acc
  }, {})

  return (
    <div className="p-4 space-y-5">
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-gray-700 tracking-wide">阅读偏好</span>
          <button
            onClick={reader.reset}
            className="text-[10px] text-gray-400 hover:text-indigo-500 transition"
          >
            恢复默认
          </button>
        </div>

        <label className="block text-[11px] font-medium text-gray-500 mb-1">字体</label>
        <select
          value={reader.fontValue}
          onChange={(e) => reader.setFontValue(e.target.value)}
          className="w-full px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50/50 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 outline-none transition mb-3"
        >
          {Object.entries(grouped).map(([category, fonts]) => (
            <optgroup key={category} label={CATEGORY_LABELS[category] || category}>
              {fonts.map((font) => (
                <option key={font.value} value={font.value}>{font.label}</option>
              ))}
            </optgroup>
          ))}
        </select>

        <div
          className="px-3 py-2 mb-3 rounded-lg border border-gray-100 bg-gray-50/50 text-gray-600 leading-relaxed"
          style={{ fontFamily: reader.fontFamily, fontSize: reader.fontSize, lineHeight: reader.lineHeight }}
        >
          <span className="text-[10px] text-gray-400 block mb-1" style={{ fontFamily: "inherit" }}>预览</span>
          The quick brown fox jumps over the lazy dog.
          <br />
          中文排版效果：量子纠缠与贝尔不等式。
        </div>

        <label className="block text-[11px] font-medium text-gray-500 mb-1">
          字号 <span className="text-gray-400 font-normal">{reader.fontSize}px</span>
        </label>
        <input
          type="range"
          min={12}
          max={24}
          step={1}
          value={reader.fontSize}
          onChange={(e) => reader.setFontSize(Number(e.target.value))}
          className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-indigo-500 mb-3"
        />

        <label className="block text-[11px] font-medium text-gray-500 mb-1">
          行高 <span className="text-gray-400 font-normal">{reader.lineHeight.toFixed(1)}</span>
        </label>
        <input
          type="range"
          min={1.4}
          max={2.4}
          step={0.1}
          value={reader.lineHeight}
          onChange={(e) => reader.setLineHeight(Number(e.target.value))}
          className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-indigo-500 mb-3"
        />

        <label className="block text-[11px] font-medium text-gray-500 mb-1.5">内容宽度</label>
        <div className="flex gap-1.5">
          {WIDTH_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => reader.setContentWidth(option.value)}
              className={`flex-1 py-1.5 text-[10px] font-medium rounded-lg border transition ${
                reader.contentWidth === option.value
                  ? "border-indigo-200 bg-indigo-50 text-indigo-600"
                  : "border-gray-100 text-gray-400 hover:border-gray-200 hover:text-gray-500"
              }`}
            >
              {option.label}
              <span className="block text-[9px] font-normal opacity-60">{option.desc}</span>
            </button>
          ))}
        </div>
      </div>

      <hr className="border-gray-100" />

      <div>
        <span className="block text-xs font-semibold text-gray-700 tracking-wide mb-3">翻译设置</span>

        <label className="block text-[11px] font-medium text-gray-500 mb-1.5">System Prompt</label>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={6}
          className="w-full px-3 py-2 text-xs leading-relaxed border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 outline-none resize-y bg-gray-50/50 transition"
          placeholder="翻译系统提示词..."
        />

        <label className="block text-[11px] font-medium text-gray-500 mt-3 mb-2">输出格式</label>
        <div className="space-y-2">
          {([
            { value: "bilingual" as const, label: "双语对照", desc: "原文与译文并排显示" },
            { value: "target_only" as const, label: "仅目标语言", desc: "只显示翻译结果" },
          ]).map((option) => (
            <label
              key={option.value}
              className={`flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition ${
                outputFormat === option.value
                  ? "border-indigo-200 bg-indigo-50/50"
                  : "border-gray-100 hover:border-gray-200"
              }`}
            >
              <input
                type="radio"
                name="outputFormat"
                value={option.value}
                checked={outputFormat === option.value}
                onChange={() => setOutputFormat(option.value)}
                className="mt-0.5 text-indigo-600 focus:ring-indigo-500"
              />
              <div>
                <div className="text-xs font-medium text-gray-700">{option.label}</div>
                <div className="text-[10px] text-gray-400 mt-0.5">{option.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
