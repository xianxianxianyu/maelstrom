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
  status: "completed" | "clarification_pending"
  answer: string
  citations: QACitation[]
  confidence: number
  route: string
  traceId: string
  contextBlocks: QAContextBlock[]
  execution?: QAExecutionSnapshot
  sessionId?: string
  turnId?: string
  clarification?: {
    threadId: string
    question: string
    options: string[]
  }
}

export interface QACitation {
  chunkId: string
  text: string
  score: number
}

export interface QAContextBlock {
  type: string
  data?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface QAExecutionProblem {
  sub_problem_id?: string
  question?: string
  intent?: string
  route_type?: string
  agent_capability?: string
  depends_on?: string[]
}

export interface QAExecutionWorkerDescriptor {
  workerId: string
  role: string
  identityPrompt: string
  capabilities: string[]
}

export interface QAExecutionRun {
  sub_problem_id?: string
  node_id?: string
  capability?: string
  agent?: string
  role?: string
  success?: boolean
  error?: string | null
  output?: Record<string, unknown>
  status?: string
  attempt?: number
  latency_ms?: number
  identity_prompt?: string
  task_prompt?: string
  progress?: number
  artifact_preview?: string
}

export interface QAExecutionSnapshot {
  traceId: string
  manager: {
    query?: string
    stage1?: Record<string, unknown>
    problems?: QAExecutionProblem[]
  }
  plan: {
    planId?: string
    metadata?: Record<string, unknown>
    nodes?: Record<string, unknown>[]
    workers?: QAExecutionWorkerDescriptor[]
  }
  workers: QAExecutionRun[]
  summary: {
    fallbackUsed?: boolean
    finalStatus?: string
    confidence?: number
  }
}

export interface QAExecutionEvent {
  type: string
  trace_id?: string
  traceId?: string
  node_id?: string
  worker?: string
  role?: string
  capability?: string
  identity_prompt?: string
  task_prompt?: string
  progress?: number
  error?: string
  artifact_preview?: string
  plan?: Record<string, unknown>
  problems?: QAExecutionProblem[]
  timestamp?: string
  seq?: number
  [key: string]: unknown
}

export interface QAOptions {
  timeout_sec?: number
  max_context_chars?: number
}

interface QAV1RawResponse {
  status: string
  session_id: string
  turn_id: string
  trace_id: string
  answer?: string
  confidence?: number
  citations?: Array<{ source?: string; text?: string; score?: number }>
  intent_tag?: string
  stage1_result?: Record<string, unknown>
  stage2_result?: Record<string, unknown>
  execution?: QAExecutionSnapshot
  clarification?: {
    thread_id?: string
    question?: string
    options?: string[]
  }
}

function mapQAV1RawResponse(raw: QAV1RawResponse): QAResponse {
  const base = {
    status: raw.status === "clarification_pending" ? "clarification_pending" : "completed",
    confidence: raw.confidence ?? 0.7,
    route: raw.intent_tag || (raw.status === "clarification_pending" ? "clarification_pending" : "DOC_QA"),
    traceId: raw.trace_id,
    sessionId: raw.session_id,
    turnId: raw.turn_id,
    contextBlocks: [
      { type: "stage1", data: raw.stage1_result || {} },
      { type: "stage2", data: raw.stage2_result || {} },
    ],
    execution: raw.execution,
  } satisfies Omit<QAResponse, "answer" | "citations">

  if (raw.status === "clarification_pending") {
    const question = raw.clarification?.question || "请补充更多信息后重试。"
    const options = raw.clarification?.options || []
    const threadId = raw.clarification?.thread_id || ""
    return {
      ...base,
      answer: question,
      citations: (raw.citations || []).map((item) => ({
        chunkId: item.source || "unknown",
        text: item.text || "",
        score: Number(item.score || 0),
      })),
      clarification: threadId
        ? {
            threadId,
            question,
            options,
          }
        : undefined,
    }
  }

  return {
    ...base,
    answer: raw.answer || "",
    citations: (raw.citations || []).map((item) => ({
      chunkId: item.source || "unknown",
      text: item.text || "",
      score: Number(item.score || 0),
    })),
  }
}

export async function askQuestion(
  params: {
    query: string
    docId?: string
    sessionId?: string
    traceId?: string
    options?: QAOptions
  },
  signal?: AbortSignal,
): Promise<QAResponse> {
  const response = await fetch(`${API_BASE}/api/qa/v1/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: params.query,
      docScope: params.docId ? [params.docId] : [],
      sessionId: params.sessionId || null,
      traceId: params.traceId || null,
      options: params.options || undefined,
    }),
    signal,
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`QA failed: ${error}`)
  }

  const raw: QAV1RawResponse = await response.json()
  return mapQAV1RawResponse(raw)
}

export async function answerClarification(
  params: {
    threadId: string
    sessionId: string
    answer: string
  },
  signal?: AbortSignal,
): Promise<QAResponse> {
  const response = await fetch(`${API_BASE}/api/qa/v1/clarify/${encodeURIComponent(params.threadId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sessionId: params.sessionId,
      answer: params.answer,
    }),
    signal,
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`QA clarification failed: ${error}`)
  }

  const raw: QAV1RawResponse = await response.json()
  return mapQAV1RawResponse(raw)
}

export async function retryExecution(
  traceId: string,
  signal?: AbortSignal,
): Promise<QAResponse> {
  const response = await fetch(`${API_BASE}/api/qa/v1/execution/${encodeURIComponent(traceId)}/retry`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    signal,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`QA retry API error ${response.status}: ${errorText}`)
  }

  const raw: QAV1RawResponse = await response.json()
  return mapQAV1RawResponse(raw)
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

export function connectQAExecutionSSE(
  traceId: string,
  onEvent: (event: QAExecutionEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  const url = `${API_BASE}/api/sse/qa/${encodeURIComponent(traceId)}`
  const es = new EventSource(url)
  es.onmessage = (e) => {
    try {
      const data: QAExecutionEvent = JSON.parse(e.data)
      onEvent(data)
    } catch (error) {
      onEvent({
        type: "stream.parse_error",
        error: error instanceof Error ? error.message : String(error),
      })
    }
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
