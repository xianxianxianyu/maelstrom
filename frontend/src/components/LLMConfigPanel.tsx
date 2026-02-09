"use client"

import { useState, useEffect } from "react"
import { AVAILABLE_MODELS, PROVIDERS, LLMProfile } from "@/types"
import { getLLMConfig, saveLLMConfig } from "@/lib/api"

interface ProfileFormState {
  provider: string
  model: string
  api_key: string
  base_url: string
  temperature: number
  max_tokens: number
}

const DEFAULT_PROFILE: ProfileFormState = {
  provider: "deepseek",
  model: "deepseek-chat",
  api_key: "",
  base_url: "",
  temperature: 0.3,
  max_tokens: 4096,
}

const BINDING_KEYS = ["translation", "qa", "summarization"]

export function LLMConfigPanel() {
  const [profiles, setProfiles] = useState<Record<string, ProfileFormState>>({})
  const [bindings, setBindings] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<{ type: "success" | "error"; msg: string } | null>(null)
  const [newName, setNewName] = useState("")
  const [editing, setEditing] = useState<string | null>(null)

  useEffect(() => { loadConfig() }, [])
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 2500)
      return () => clearTimeout(t)
    }
  }, [toast])

  const loadConfig = async () => {
    try {
      const data = await getLLMConfig()
      const loaded: Record<string, ProfileFormState> = {}
      for (const [name, cfg] of Object.entries(data.profiles)) {
        loaded[name] = {
          provider: cfg.provider, model: cfg.model,
          api_key: cfg.api_key || "", base_url: cfg.base_url || "",
          temperature: cfg.temperature, max_tokens: cfg.max_tokens,
        }
      }
      setProfiles(loaded)
      setBindings(data.bindings || {})
    } catch {
      setProfiles({}); setBindings({})
    } finally { setLoading(false) }
  }

  const addProfile = () => {
    const name = newName.trim().toLowerCase().replace(/\s+/g, "-")
    if (!name || profiles[name]) return
    setProfiles((p) => ({ ...p, [name]: { ...DEFAULT_PROFILE } }))
    setEditing(name); setNewName("")
  }

  const deleteProfile = (name: string) => {
    setProfiles((p) => { const n = { ...p }; delete n[name]; return n })
    setBindings((p) => {
      const n = { ...p }
      for (const [k, v] of Object.entries(n)) { if (v === name) delete n[k] }
      return n
    })
    if (editing === name) setEditing(null)
  }

  const updateProfile = (name: string, field: keyof ProfileFormState, value: string | number) => {
    setProfiles((p) => {
      const u = { ...p[name], [field]: value }
      if (field === "provider") {
        u.model = AVAILABLE_MODELS.filter((m) => m.provider === value)[0]?.id || ""
      }
      return { ...p, [name]: u }
    })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload: Record<string, LLMProfile> = {}
      for (const [name, s] of Object.entries(profiles)) {
        payload[name] = {
          provider: s.provider, model: s.model, api_key: s.api_key,
          base_url: s.base_url || null, temperature: s.temperature, max_tokens: s.max_tokens,
        }
      }
      await saveLLMConfig(payload, bindings)
      setToast({ type: "success", msg: "已保存" })
    } catch (err) {
      setToast({ type: "error", msg: err instanceof Error ? err.message : "保存失败" })
    } finally { setSaving(false) }
  }

  if (loading) return <div className="p-4 text-xs text-gray-400">加载中...</div>

  const names = Object.keys(profiles)

  return (
    <div className="p-3 space-y-3">
      {/* Toast */}
      {toast && (
        <div className={`px-2.5 py-1.5 rounded text-xs ${
          toast.type === "success" ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
            : "bg-red-50 text-red-600 border border-red-200"
        }`}>{toast.msg}</div>
      )}

      {/* 新建 */}
      <div className="flex gap-1.5">
        <input type="text" value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addProfile()}
          placeholder="新档案名..."
          className="flex-1 px-2 py-1.5 text-xs border border-gray-200 rounded-md focus:ring-1 focus:ring-indigo-300 bg-gray-50"
        />
        <button onClick={addProfile} disabled={!newName.trim()}
          className="px-2.5 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:bg-gray-300 whitespace-nowrap"
        >+ 新建</button>
      </div>

      {/* 档案列表 */}
      {names.map((name) => {
        const s = profiles[name]
        const isOpen = editing === name
        const models = AVAILABLE_MODELS.filter((m) => m.provider === s.provider)
        return (
          <div key={name} className="border border-gray-200 rounded-lg overflow-hidden bg-white">
            <div className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors"
              onClick={() => setEditing(isOpen ? null : name)}>
              <div className="min-w-0">
                <div className="text-xs font-medium text-gray-700 truncate">{name}</div>
                <div className="text-[10px] text-gray-400">{s.provider}/{s.model}</div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button onClick={(e) => { e.stopPropagation(); deleteProfile(name) }}
                  className="text-[10px] text-red-400 hover:text-red-600 px-1">删除</button>
                <svg className={`w-3 h-3 text-gray-300 transition-transform ${isOpen ? "rotate-180" : ""}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>
            {isOpen && (
              <div className="px-3 pb-3 pt-2 space-y-2 border-t border-gray-100">
                <div>
                  <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Provider</label>
                  <select value={s.provider} onChange={(e) => updateProfile(name, "provider", e.target.value)}
                    className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-indigo-300">
                    {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Model</label>
                  <select value={s.model} onChange={(e) => updateProfile(name, "model", e.target.value)}
                    className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-indigo-300">
                    {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-medium text-gray-500 mb-0.5">API Key</label>
                  <input type="password" value={s.api_key}
                    onChange={(e) => updateProfile(name, "api_key", e.target.value)}
                    placeholder="留空使用 KeyStore"
                    className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-indigo-300"
                  />
                </div>
                <div className="flex gap-2">
                  <div className="flex-1">
                    <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Temp ({s.temperature})</label>
                    <input type="range" min="0" max="2" step="0.1" value={s.temperature}
                      onChange={(e) => updateProfile(name, "temperature", parseFloat(e.target.value))}
                      className="w-full h-1.5" />
                  </div>
                  <div className="w-20">
                    <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Tokens</label>
                    <input type="number" value={s.max_tokens}
                      onChange={(e) => updateProfile(name, "max_tokens", parseInt(e.target.value) || 4096)}
                      className="w-full px-1.5 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-indigo-300"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        )
      })}

      {/* Bindings */}
      {names.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">功能绑定</div>
          {BINDING_KEYS.map((key) => (
            <div key={key} className="flex items-center gap-2">
              <span className="w-20 text-xs text-gray-500 capitalize">{key}</span>
              <select value={bindings[key] || ""}
                onChange={(e) => setBindings((p) => ({ ...p, [key]: e.target.value }))}
                className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-indigo-300">
                <option value="">--</option>
                {names.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}

      {/* Save */}
      <button onClick={handleSave} disabled={saving}
        className="w-full py-2 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 transition-colors">
        {saving ? "保存中..." : "保存配置"}
      </button>
    </div>
  )
}
