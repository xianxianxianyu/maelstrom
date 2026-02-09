import { ModelConfig } from "@/types"

const CONFIG_KEY = "pdf-translator-config"

/**
 * 保存模型配置到 localStorage（不含 API Key）
 */
export function saveConfig(config: ModelConfig): void {
  if (typeof window === "undefined") return
  const configWithoutKey = {
    provider: config.provider,
    model: config.model,
  }
  localStorage.setItem(CONFIG_KEY, JSON.stringify(configWithoutKey))
}

/**
 * 加载模型配置
 */
export function loadConfig(): ModelConfig | null {
  if (typeof window === "undefined") return null
  const stored = localStorage.getItem(CONFIG_KEY)
  if (stored) {
    try {
      return JSON.parse(stored) as ModelConfig
    } catch {
      return null
    }
  }
  return null
}

/**
 * 清除所有配置
 */
export function clearConfig(): void {
  if (typeof window === "undefined") return
  localStorage.removeItem(CONFIG_KEY)
}
