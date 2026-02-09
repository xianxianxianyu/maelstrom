"use client"

import { useState, useEffect } from "react"
import { OCR_PROVIDERS, OCR_MODES, MINERU_MODEL_VERSIONS, OCRProfile } from "@/types"
import { getOCRConfig, saveOCRConfig } from "@/lib/api"

interface OCRProfileFormState {
  provider: string
  mode: string
  api_url: string
  token: string
  model: string
  use_chart_recognition: boolean
  use_doc_orientation_classify: boolean
  use_doc_unwarping: boolean
}

const DEFAULT_OCR_PROFILE: OCRProfileFormState = {
  provider: "paddleocr",
  mode: "sync",
  api_url: "https://i8i44al2jfmfg1p3.aistudio-app.com/layout-parsing",
  token: "",
  model: "",
  use_chart_recognition: false,
  use_doc_orientation_classify: false,
  use_doc_unwarping: false,
}

// 默认 API URL 配置（MineRU 的 base URL 固定，不需要用户配置）
const DEFAULT_URLS: Record<string, Record<string, string>> = {
  paddleocr: {
    sync: "https://i8i44al2jfmfg1p3.aistudio-app.com/layout-parsing",
    async: "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs",
  },
}

// 各 provider 的默认配置模板，切换时自动填充
const PROVIDER_DEFAULTS: Record<string, Partial<OCRProfileFormState>> = {
  paddleocr: {
    mode: "sync",
    api_url: "https://i8i44al2jfmfg1p3.aistudio-app.com/layout-parsing",
    model: "",
    token: "",
  },
  mineru: {
    mode: "async",
    api_url: "",  // MineRU base URL 固定在后端，不需要用户填
    model: "vlm",
  },
}

const OCR_BINDING_KEYS = ["ocr"]

export function OCRConfigPanel() {
  const [profiles, setProfiles] = useState<Record<string, OCRProfileFormState>>({})
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
      const data = await getOCRConfig()
      const loaded: Record<string, OCRProfileFormState> = {}
      for (const [name, cfg] of Object.entries(data.profiles)) {
        loaded[name] = {
          provider: cfg.provider, mode: cfg.mode,
          api_url: cfg.api_url || "", token: cfg.token || "",
          model: cfg.model || "",
          use_chart_recognition: cfg.use_chart_recognition,
          use_doc_orientation_classify: cfg.use_doc_orientation_classify,
          use_doc_unwarping: cfg.use_doc_unwarping,
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
    setProfiles((p) => ({ ...p, [name]: { ...DEFAULT_OCR_PROFILE } }))
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

  const updateProfile = (name: string, field: keyof OCRProfileFormState, value: string | boolean) => {
    setProfiles((p) => ({ ...p, [name]: { ...p[name], [field]: value } }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload: Record<string, OCRProfile> = {}
      for (const [name, s] of Object.entries(profiles)) {
        payload[name] = {
          provider: s.provider, mode: s.mode,
          api_url: s.api_url, token: s.token, model: s.model,
          use_chart_recognition: s.use_chart_recognition,
          use_doc_orientation_classify: s.use_doc_orientation_classify,
          use_doc_unwarping: s.use_doc_unwarping,
        }
      }
      await saveOCRConfig(payload, bindings)
      setToast({ type: "success", msg: "已保存" })
    } catch (err) {
      setToast({ type: "error", msg: err instanceof Error ? err.message : "保存失败" })
    } finally { setSaving(false) }
  }

  if (loading) return <div className="p-4 text-xs text-gray-400">加载中...</div>

  const names = Object.keys(profiles)

  return (
    <div className="p-3 space-y-3">
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
          placeholder="新 OCR 档案名..."
          className="flex-1 px-2 py-1.5 text-xs border border-gray-200 rounded-md focus:ring-1 focus:ring-teal-300 bg-gray-50"
        />
        <button onClick={addProfile} disabled={!newName.trim()}
          className="px-2.5 py-1.5 text-xs font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:bg-gray-300 whitespace-nowrap"
        >+ 新建</button>
      </div>

      {/* 档案列表 */}
      {names.map((name) => {
        const s = profiles[name]
        const isOpen = editing === name
        return (
          <div key={name} className="border border-gray-200 rounded-lg overflow-hidden bg-white">
            <div className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors"
              onClick={() => setEditing(isOpen ? null : name)}>
              <div className="min-w-0">
                <div className="text-xs font-medium text-gray-700 truncate">{name}</div>
                <div className="text-[10px] text-gray-400">{s.provider}/{s.mode}</div>
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
                  <select value={s.provider} onChange={(e) => {
                    const newProvider = e.target.value
                    // 切换 provider 时，用该 provider 的默认模板重置相关字段
                    const defaults = PROVIDER_DEFAULTS[newProvider] || {}
                    setProfiles((p) => ({
                      ...p,
                      [name]: {
                        ...p[name],
                        provider: newProvider,
                        mode: defaults.mode ?? p[name].mode,
                        api_url: defaults.api_url ?? "",
                        model: defaults.model ?? "",
                        // 保留 token（用户可能已经填了）
                        use_chart_recognition: newProvider === "paddleocr" ? p[name].use_chart_recognition : false,
                        use_doc_orientation_classify: newProvider === "paddleocr" ? p[name].use_doc_orientation_classify : false,
                        use_doc_unwarping: newProvider === "paddleocr" ? p[name].use_doc_unwarping : false,
                      },
                    }))
                  }}
                    className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-teal-300">
                    {OCR_PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>

                {/* PaddleOCR 模式选择 */}
                {s.provider === "paddleocr" && (
                  <div>
                    <label className="block text-[10px] font-medium text-gray-500 mb-0.5">模式</label>
                    <select value={s.mode} onChange={(e) => {
                      const newMode = e.target.value
                      updateProfile(name, "mode", newMode)
                      const urls = DEFAULT_URLS.paddleocr
                      if (urls?.[newMode]) {
                        updateProfile(name, "api_url", urls[newMode])
                      }
                    }}
                      className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-teal-300">
                      {OCR_MODES.map((m) => <option key={m.id} value={m.id}>{m.name} - {m.desc}</option>)}
                    </select>
                  </div>
                )}

                {/* MineRU 模型版本选择 */}
                {s.provider === "mineru" && (
                  <div>
                    <label className="block text-[10px] font-medium text-gray-500 mb-0.5">模型版本</label>
                    <select value={s.model || "vlm"} onChange={(e) => updateProfile(name, "model", e.target.value)}
                      className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-teal-300">
                      {MINERU_MODEL_VERSIONS.map((m) => <option key={m.id} value={m.id}>{m.name} - {m.desc}</option>)}
                    </select>
                  </div>
                )}

                {/* MineRU: API URL 固定在后端，不需要用户配置 */}
                {s.provider === "paddleocr" && (
                  <div>
                    <label className="block text-[10px] font-medium text-gray-500 mb-0.5">API URL</label>
                    <input type="text" value={s.api_url}
                      onChange={(e) => updateProfile(name, "api_url", e.target.value)}
                      placeholder="留空使用默认地址"
                      className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-teal-300"
                    />
                  </div>
                )}
                <div>
                  <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Token</label>
                  <input type="password" value={s.token}
                    onChange={(e) => updateProfile(name, "token", e.target.value)}
                    placeholder={s.provider === "mineru" ? "MineRU JWT Token（mineru.net 个人中心获取）" : "PaddleOCR API Token（可选）"}
                    autoComplete="new-password"
                    data-lpignore="true"
                    data-1p-ignore
                    className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-teal-300"
                  />
                  {s.provider === "mineru" && !s.token && (
                    <p className="text-[10px] text-amber-500 mt-0.5">⚠ MineRU 必须填写 Token 才能使用</p>
                  )}
                </div>

                {/* PaddleOCR 高级选项 */}
                {s.provider === "paddleocr" && (
                  <div className="space-y-1.5 pt-1">
                    <div className="text-[10px] font-medium text-gray-500">高级选项</div>
                    {([
                      { key: "use_chart_recognition" as const, label: "图表识别" },
                      { key: "use_doc_orientation_classify" as const, label: "文档方向分类" },
                      { key: "use_doc_unwarping" as const, label: "文档去弯曲" },
                    ]).map((opt) => (
                      <label key={opt.key} className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={s[opt.key] as boolean}
                          onChange={(e) => updateProfile(name, opt.key, e.target.checked)}
                          className="rounded text-teal-600 focus:ring-teal-500"
                        />
                        <span className="text-xs text-gray-600">{opt.label}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}

      {/* Bindings — 清晰显示当前激活的引擎 */}
      {names.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">功能绑定</div>
          {OCR_BINDING_KEYS.map((key) => {
            const boundProfile = bindings[key]
            const boundConfig = boundProfile ? profiles[boundProfile] : null
            return (
              <div key={key}>
                <div className="flex items-center gap-2">
                  <span className="w-20 text-xs text-gray-500 capitalize">{key}</span>
                  <select value={bindings[key] || ""}
                    onChange={(e) => setBindings((p) => ({ ...p, [key]: e.target.value }))}
                    className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:ring-1 focus:ring-teal-300">
                    <option value="">--</option>
                    {names.map((n) => (
                      <option key={n} value={n}>{n} ({profiles[n]?.provider})</option>
                    ))}
                  </select>
                </div>
                {boundConfig && (
                  <p className="text-[10px] text-teal-600 mt-0.5 ml-[5.5rem]">
                    ✓ 当前引擎: {boundConfig.provider === "mineru" ? "MineRU" : "PaddleOCR"}
                    {boundConfig.provider === "paddleocr" ? ` / ${boundConfig.mode}` : ` / ${boundConfig.model || "vlm"}`}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Save */}
      <button onClick={handleSave} disabled={saving}
        className="w-full py-2 text-xs font-medium text-white bg-teal-600 rounded-lg hover:bg-teal-700 disabled:bg-gray-300 transition-colors">
        {saving ? "保存中..." : "保存配置"}
      </button>
    </div>
  )
}
