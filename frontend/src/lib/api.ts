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

export interface AsyncUploadResponse {
  task_id: string
  status: "processing"
}

// ── SSE 事件类型 ──

export interface TranslationSSEEvent {
  agent: string
  stage: string
  progress: number
  detail?: {
    message?: string
    doc_type?: string
    pipeline?: string
    current_block?: number
    total_blocks?: number
    current?: number
    total?: number
    domain?: string
    term_count?: number
    score?: number | string
    new_score?: number | string
    [key: string]: unknown
  }
}

// ── 术语类型 ──

export interface TermEntry {
  english: string
  chinese: string
  keep_english: boolean
  domain: string
  source: string
  updated_at: string
}

// ── 质量报告类型 ──

export interface QualityReport {
  score: number
  terminology_issues: Array<{
    english_term: string
    translations: string[]
    locations: string[]
    suggested: string
  }>
  format_issues: Array<{
    issue_type: string
    location: string
    description: string
  }>
  untranslated: string[]
  suggestions: string[]
  timestamp: string
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

export interface PaperRecord {
  id: string
  task_id: string
  title: string
  title_zh: string
  authors: string[]
  abstract: string
  domain: string
  research_problem: string
  methodology: string
  contributions: string[]
  keywords: string[]
  tags: string[]
  base_models: string[]
  year: number | null
  venue: string
  quality_score: number | null
  filename: string
  created_at: string
}

export interface PaperDetailResponse {
  paper: PaperRecord
  sections: Record<string, string>
}

export async function getPaperDetail(taskId: string): Promise<PaperDetailResponse> {
  const response = await fetch(`${API_BASE}/api/papers/${encodeURIComponent(taskId)}`)
  if (!response.ok) {
    throw new Error(`Failed to get paper detail: ${response.statusText}`)
  }
  return response.json()
}

export async function updatePaperSection(
  taskId: string,
  section: string,
  content: string,
): Promise<PaperDetailResponse> {
  const response = await fetch(
    `${API_BASE}/api/papers/${encodeURIComponent(taskId)}/sections/${encodeURIComponent(section)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  )
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to update paper section: ${error}`)
  }
  return response.json()
}

export async function updatePaperRaw(
  taskId: string,
  raw: Record<string, unknown> | string,
): Promise<PaperDetailResponse> {
  const response = await fetch(`${API_BASE}/api/papers/${encodeURIComponent(taskId)}/raw`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw }),
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to update paper raw payload: ${error}`)
  }
  return response.json()
}


// ── Agent QA API ──

export interface QAResponse {
  answer: string
  profile_used: string
  citations?: Array<{
    text: string
    source: string
  }>
}

export interface QAV2Citation {
  chunkId: string
  text: string
  score: number
}

export interface QAV2ContextBlock {
  type: string
  data?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface QAV2Response {
  answer: string
  citations: QAV2Citation[]
  confidence: number
  route: string
  traceId: string
  contextBlocks: QAV2ContextBlock[]
}

export interface QAV2Options {
  timeout_sec?: number
  max_context_chars?: number
}

export async function askQuestionV2(
  params: {
    query: string
    docId?: string
    sessionId?: string
    options?: QAV2Options
  },
  signal?: AbortSignal,
): Promise<QAV2Response> {
  const response = await fetch(`${API_BASE}/api/agent/qa/v2`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: params.query,
      docId: params.docId || undefined,
      sessionId: params.sessionId || undefined,
      options: params.options || undefined,
    }),
    signal,
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`QA v2 failed: ${error}`)
  }

  return response.json()
}

export async function askQuestion(
  question: string,
  profileName?: string,
  context?: string,
  sessionId?: string,
  docId?: string,
): Promise<QAResponse> {
  const response = await fetch(`${API_BASE}/api/agent/qa`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      profile_name: profileName || undefined,
      context: context || undefined,
      session_id: sessionId || undefined,
      doc_id: docId || undefined,
    }),
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`QA failed: ${error}`)
  }
  return response.json()
}


// ── SSE 连接 ──

export function connectTranslationSSE(
  taskId: string,
  onEvent: (event: TranslationSSEEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  const url = `${API_BASE}/api/sse/translation/${taskId}`
  const es = new EventSource(url)
  es.onmessage = (e) => {
    try {
      const data: TranslationSSEEvent = JSON.parse(e.data)
      onEvent(data)
    } catch { /* ignore parse errors */ }
  }
  if (onError) {
    es.onerror = onError
  }
  return es
}

// ── 术语 CRUD API ──

export async function getTerminology(domain: string): Promise<TermEntry[]> {
  const response = await fetch(`${API_BASE}/api/terminology/${encodeURIComponent(domain)}`)
  if (!response.ok) {
    throw new Error(`Failed to get terminology: ${response.statusText}`)
  }
  const data = await response.json()
  return data.entries ?? data
}

export async function searchTerminology(query: string): Promise<TermEntry[]> {
  const response = await fetch(`${API_BASE}/api/terminology/search?q=${encodeURIComponent(query)}`)
  if (!response.ok) {
    throw new Error(`Failed to search terminology: ${response.statusText}`)
  }
  const data = await response.json()
  return data.results ?? data
}

export async function updateTerm(
  domain: string,
  term: string,
  chinese: string,
  keepEnglish?: boolean,
): Promise<TermEntry> {
  const response = await fetch(
    `${API_BASE}/api/terminology/${encodeURIComponent(domain)}/${encodeURIComponent(term)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chinese,
        keep_english: keepEnglish ?? false,
      }),
    },
  )
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to update term: ${error}`)
  }
  return response.json()
}

export async function deleteTerm(domain: string, term: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/terminology/${encodeURIComponent(domain)}/${encodeURIComponent(term)}`,
    { method: "DELETE" },
  )
  if (!response.ok) {
    throw new Error(`Failed to delete term: ${response.statusText}`)
  }
}

// ── 质量报告 API ──

export async function getQualityReport(translationId: string): Promise<QualityReport> {
  const response = await fetch(`${API_BASE}/api/translations/${encodeURIComponent(translationId)}/quality`)
  if (!response.ok) {
    throw new Error(`Failed to get quality report: ${response.statusText}`)
  }
  return response.json()
}

// ── 翻译结果（异步上传后获取） ──

export async function getTranslationResult(taskId: string): Promise<any> {
  const response = await fetch(`${API_BASE}/api/pdf/result/${encodeURIComponent(taskId)}`)
  if (!response.ok) {
    throw new Error(`Failed to get translation result: ${response.statusText}`)
  }
  return response.json()
}
