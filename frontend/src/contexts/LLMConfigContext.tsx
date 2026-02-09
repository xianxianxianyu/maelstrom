"use client"

import { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from "react"
import { getLLMConfig } from "@/lib/api"
import { LLMProfile } from "@/types"

interface LLMConfigState {
  /** 档案名列表 */
  profileNames: string[]
  /** 档案名 → {provider, model} 映射（不含 key） */
  profileMap: Record<string, { provider: string; model: string; has_key?: boolean }>
  /** 完整 profiles 数据（供编辑面板使用） */
  profiles: Record<string, LLMProfile>
  /** 功能绑定 */
  bindings: Record<string, string>
  /** 是否正在加载 */
  loading: boolean
  /** 重新从后端拉取配置（保存后调用） */
  refresh: () => Promise<void>
}

const LLMConfigContext = createContext<LLMConfigState | null>(null)

export function LLMConfigProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<Record<string, LLMProfile>>({})
  const [bindings, setBindings] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await getLLMConfig()
      setProfiles(data.profiles)
      setBindings(data.bindings || {})
    } catch {
      setProfiles({})
      setBindings({})
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const value = useMemo<LLMConfigState>(() => {
    const profileNames = Object.keys(profiles)
    const profileMap: Record<string, { provider: string; model: string; has_key?: boolean }> = {}
    for (const [name, cfg] of Object.entries(profiles)) {
      profileMap[name] = { provider: cfg.provider, model: cfg.model, has_key: cfg.has_key }
    }
    return { profileNames, profileMap, profiles, bindings, loading, refresh }
  }, [profiles, bindings, loading, refresh])

  return (
    <LLMConfigContext.Provider value={value}>
      {children}
    </LLMConfigContext.Provider>
  )
}

export function useLLMConfig(): LLMConfigState {
  const ctx = useContext(LLMConfigContext)
  if (!ctx) throw new Error("useLLMConfig must be used within LLMConfigProvider")
  return ctx
}
