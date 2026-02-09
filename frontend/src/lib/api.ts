import { ModelConfig, LLMConfigData, LLMProfile, OCRConfigData, OCRProfile, TranslationEntry } from "@/types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:3301"

export interface PromptProfileInfo {
  domain: string
  terminology_count: number
  keep_english: string[]
  generated_prompt: string
}

export interface UploadResponse {
  markdown: string
  ocr_markdown: string | null
  translation_id: string
  provider_used: string
  model_used: string
  prompt_profile: PromptProfileInfo | null
}

export interface KeyStatus {
  provider: string
  has_key: boolean
}

export async function setApiKey(provider: string, apiKey: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/keys/set`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, api_key: apiKey }),
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to set API key: ${error}`)
  }
}

export async function getKeyStatus(): Promise<KeyStatus[]> {
  const response = await fetch(`${API_BASE}/api/keys/status`)
  if (!response.ok) {
    throw new Error(`Failed to get key status: ${response.statusText}`)
  }
  const data = await response.json()
  return data.keys
}

export async function uploadPDF(
  file: File,
  config: ModelConfig,
  systemPrompt?: string,
  enableOcr?: boolean,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("file", file)
  formData.append("provider", config.provider)
  formData.append("model", config.model)
  if (config.apiKey && config.apiKey.trim() !== "") {
    formData.append("api_key", config.apiKey.trim())
  }
  if (systemPrompt && systemPrompt.trim() !== "") {
    formData.append("system_prompt", systemPrompt.trim())
  }
  if (enableOcr) {
    formData.append("enable_ocr", "true")
  }

  const response = await fetch(`${API_BASE}/api/pdf/upload`, {
    method: "POST",
    body: formData,
    signal,
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Upload failed: ${response.statusText} - ${error}`)
  }
  return response.json()
}

export async function cancelAllTasks(): Promise<void> {
  await fetch(`${API_BASE}/api/pdf/cancel-all`, { method: "POST" })
}

export async function cancelTask(taskId: string): Promise<void> {
  await fetch(`${API_BASE}/api/pdf/cancel/${taskId}`, { method: "POST" })
}

export async function getAvailableModels(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/models/`)
  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.statusText}`)
  }
  return response.json()
}

export async function getLLMConfig(): Promise<LLMConfigData> {
  const response = await fetch(`${API_BASE}/api/llm-config`)
  if (!response.ok) {
    throw new Error(`Failed to get LLM config: ${response.statusText}`)
  }
  return response.json()
}

export async function saveLLMConfig(
  profiles: Record<string, LLMProfile>,
  bindings: Record<string, string>,
): Promise<{ message: string; saved_profiles: string[] }> {
  const response = await fetch(`${API_BASE}/api/llm-config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profiles, bindings }),
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to save LLM config: ${error}`)
  }
  return response.json()
}

export async function reloadLLMConfig(): Promise<{ message: string; loaded_profiles: string[] }> {
  const response = await fetch(`${API_BASE}/api/llm-config/reload`, {
    method: "POST",
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to reload LLM config: ${error}`)
  }
  return response.json()
}

export async function getOCRConfig(): Promise<OCRConfigData> {
  const response = await fetch(`${API_BASE}/api/ocr-config`)
  if (!response.ok) {
    throw new Error(`Failed to get OCR config: ${response.statusText}`)
  }
  return response.json()
}

export async function saveOCRConfig(
  profiles: Record<string, OCRProfile>,
  bindings: Record<string, string>,
): Promise<{ message: string; saved_profiles: string[] }> {
  const response = await fetch(`${API_BASE}/api/ocr-config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profiles, bindings }),
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to save OCR config: ${error}`)
  }
  return response.json()
}


// ── 翻译历史 API ──

export async function getTranslationList(): Promise<TranslationEntry[]> {
  const response = await fetch(`${API_BASE}/api/translations`)
  if (!response.ok) {
    throw new Error(`Failed to get translations: ${response.statusText}`)
  }
  const data = await response.json()
  return data.entries
}

export async function getTranslation(id: string): Promise<{
  markdown: string
  ocr_markdown?: string
  meta?: TranslationEntry
}> {
  const response = await fetch(`${API_BASE}/api/translations/${id}`)
  if (!response.ok) {
    throw new Error(`Failed to get translation: ${response.statusText}`)
  }
  return response.json()
}

export async function deleteTranslation(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/translations/${id}`, {
    method: "DELETE",
  })
  if (!response.ok) {
    throw new Error(`Failed to delete translation: ${response.statusText}`)
  }
}

export function getTranslationImageUrl(tid: string, filename: string): string {
  return `${API_BASE}/api/translations/${tid}/images/${filename}`
}


// ── Agent QA API ──

export interface QAResponse {
  answer: string
  profile_used: string
}

export async function askQuestion(
  question: string,
  profileName?: string,
  context?: string,
): Promise<QAResponse> {
  const response = await fetch(`${API_BASE}/api/agent/qa`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      profile_name: profileName || undefined,
      context: context || undefined,
    }),
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`QA failed: ${error}`)
  }
  return response.json()
}
