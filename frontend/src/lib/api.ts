import { ModelConfig } from "@/types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"

export interface UploadResponse {
  markdown: string
  provider_used: string
  model_used: string
}

export interface KeyStatus {
  provider: string
  has_key: boolean
}

/**
 * 设置 API Key 到后端内存缓存
 */
export async function setApiKey(provider: string, apiKey: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/keys/set`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ provider, api_key: apiKey }),
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to set API key: ${error}`)
  }
}

/**
 * 获取后端 Key 状态
 */
export async function getKeyStatus(): Promise<KeyStatus[]> {
  const response = await fetch(`${API_BASE}/api/keys/status`)
  if (!response.ok) {
    throw new Error(`Failed to get key status: ${response.statusText}`)
  }
  const data = await response.json()
  return data.keys
}

/**
 * 上传 PDF 并翻译
 */
export async function uploadPDF(file: File, config: ModelConfig): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("file", file)
  formData.append("provider", config.provider)
  formData.append("model", config.model)

  // 如果有 API Key，通过表单传递
  if (config.apiKey && config.apiKey.trim() !== "") {
    formData.append("api_key", config.apiKey.trim())
  }

  const response = await fetch(`${API_BASE}/api/pdf/upload`, {
    method: "POST",
    body: formData,
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Upload failed: ${response.statusText} - ${error}`)
  }

  return response.json()
}

/**
 * 获取可用模型列表
 */
export async function getAvailableModels(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/models/`)
  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.statusText}`)
  }
  return response.json()
}
