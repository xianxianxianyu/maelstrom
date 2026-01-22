"use client"

import { useState, useEffect } from "react"
import { ModelConfig, AVAILABLE_MODELS } from "@/types"
import { saveConfig, loadConfig, saveApiKey } from "@/lib/storage"
import { setApiKey as setBackendApiKey } from "@/lib/api"

interface Props {
  onConfigChange: (config: ModelConfig) => void
  currentProvider?: string
  currentModel?: string
}

export function ModelSettings({ onConfigChange, currentProvider, currentModel }: Props) {
  const [isOpen, setIsOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>("")
  const [config, setConfig] = useState<ModelConfig>({
    provider: "deepseek",
    model: "deepseek-chat",
    apiKey: ""
  })

  useEffect(() => {
    const saved = loadConfig()
    if (saved) {
      setConfig(saved)
      onConfigChange(saved)
    }
  }, [onConfigChange])

  const handleSave = async () => {
    setError("")
    setSaving(true)

    try {
      // 保存到本地存储
      saveConfig(config)

      // 如果有 API Key，同步到后端内存缓存
      if (config.apiKey && config.apiKey.trim()) {
        await setBackendApiKey(config.provider, config.apiKey.trim())
        saveApiKey(config.provider, config.apiKey.trim())
      }

      onConfigChange(config)
      setIsOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  const filteredModels = AVAILABLE_MODELS.filter(m => m.provider === config.provider)

  return (
    <div className="fixed top-4 right-4 z-50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="p-2 bg-white border border-slate-200 rounded shadow hover:bg-slate-50"
        title="Model Settings"
      >
        <svg className="w-5 h-5 text-slate-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-white border border-slate-200 rounded-lg shadow-lg p-6">
          <h3 className="text-lg font-medium mb-4">Translation Model Settings</h3>

          {error && (
            <div className="mb-4 p-2 bg-red-50 border border-red-200 text-red-700 text-sm rounded">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Provider</label>
              <select
                value={config.provider}
                onChange={(e) => {
                  const newProvider = e.target.value as any
                  const newModels = AVAILABLE_MODELS.filter(m => m.provider === newProvider)
                  setConfig({
                    ...config,
                    provider: newProvider,
                    model: newModels[0]?.id || "",
                    apiKey: "" // 切换 provider 时清空 key
                  })
                }}
                className="w-full px-3 py-2 border border-slate-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="zhipuai">ZhipuAI (GLM)</option>
                <option value="openai">OpenAI</option>
                <option value="deepseek">DeepSeek</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Model</label>
              <select
                value={config.model}
                onChange={(e) => setConfig({ ...config, model: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {filteredModels.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} - {m.description}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                API Key
                <span className="text-xs text-slate-500 ml-1">(required)</span>
              </label>
              <input
                type="password"
                value={config.apiKey || ""}
                onChange={(e) => setConfig({ ...config, apiKey: e.target.value })}
                placeholder="Enter your API key"
                className="w-full px-3 py-2 border border-slate-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="mt-1 text-xs text-slate-500">
                Key stored in memory only, cleared on browser close
              </p>
            </div>

            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSave}
                disabled={saving || !config.apiKey?.trim()}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed"
              >
                {saving ? "Saving..." : "Save"}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="flex-1 px-4 py-2 bg-slate-200 text-slate-700 rounded hover:bg-slate-300"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
