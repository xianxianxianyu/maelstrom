"use client"

import { LLMConfigPanel } from "@/components/LLMConfigPanel"
import { OCRConfigPanel } from "@/components/OCRConfigPanel"
import { ReaderSettingsPanel } from "@/components/ReaderSettingsPanel"

export default function ConfigPage() {
  return (
    <div className="h-full overflow-y-auto bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="bg-white border border-gray-200 rounded-xl px-5 py-4">
          <h1 className="text-base font-semibold text-gray-800">配置中心</h1>
          <p className="text-xs text-gray-500 mt-1">统一管理 LLM、OCR 与阅读/翻译设置。</p>
        </header>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <section className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <LLMConfigPanel />
          </section>

          <section className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <OCRConfigPanel />
          </section>
        </div>

        <section className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <ReaderSettingsPanel />
        </section>
      </div>
    </div>
  )
}
