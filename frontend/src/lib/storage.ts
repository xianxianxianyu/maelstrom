import { ModelConfig } from "@/types"

const CONFIG_KEY = "pdf-translator-config"
const KEY_PREFIX = "pdf-translator-key-"

/**
 * 保存模型配置（不含 API Key）到 localStorage
 */
export function saveConfig(config: ModelConfig): void {
  if (typeof window === "undefined") return

  // 保存配置（不含 key）
  const configWithoutKey = {
    provider: config.provider,
    model: config.model
  }
  localStorage.setItem(CONFIG_KEY, JSON.stringify(configWithoutKey))

  // API Key 单独存到 sessionStorage（浏览器关闭即清除）
  if (config.apiKey && config.apiKey.trim()) {
    sessionStorage.setItem(`${KEY_PREFIX}${config.provider}`, config.apiKey.trim())
  }
}

/**
 * 加载模型配置
 */
export function loadConfig(): ModelConfig | null {
  if (typeof window === "undefined") return null

  const stored = localStorage.getItem(CONFIG_KEY)
  if (stored) {
    try {
      const config = JSON.parse(stored) as ModelConfig
      // 尝试从 sessionStorage 恢复 API Key
      const savedKey = sessionStorage.getItem(`${KEY_PREFIX}${config.provider}`)
      if (savedKey) {
        config.apiKey = savedKey
      }
      return config
    } catch {
      return null
    }
  }
  return null
}

/**
 * 保存 API Key 到 sessionStorage（浏览器关闭即清除）
 */
export function saveApiKey(provider: string, apiKey: string): void {
  if (typeof window === "undefined") return
  if (apiKey && apiKey.trim()) {
    sessionStorage.setItem(`${KEY_PREFIX}${provider}`, apiKey.trim())
  }
}

/**
 * 获取 API Key
 */
export function getApiKey(provider: string): string | null {
  if (typeof window === "undefined") return null
  return sessionStorage.getItem(`${KEY_PREFIX}${provider}`)
}

/**
 * 清除指定 provider 的 API Key
 */
export function clearApiKey(provider: string): void {
  if (typeof window === "undefined") return
  sessionStorage.removeItem(`${KEY_PREFIX}${provider}`)
}

/**
 * 清除所有配置
 */
export function clearConfig(): void {
  if (typeof window === "undefined") return
  localStorage.removeItem(CONFIG_KEY)
  // 清除所有 provider 的 key
  const providers = ["zhipuai", "openai", "deepseek"]
  providers.forEach(p => sessionStorage.removeItem(`${KEY_PREFIX}${p}`))
}
