export interface ModelConfig {
  provider: "zhipuai" | "openai" | "deepseek"
  model: string
  apiKey?: string
}

export interface ModelInfo {
  id: string
  name: string
  provider: string
  description: string
}

export interface LLMProfile {
  provider: string
  model: string
  api_key: string
  has_key?: boolean
  base_url: string | null
  temperature: number
  max_tokens: number
}

export interface LLMConfigData {
  profiles: Record<string, LLMProfile>
  bindings: Record<string, string>
}

export const AVAILABLE_MODELS: ModelInfo[] = [
  // ZhipuAI Models
  { id: "glm-4", name: "GLM-4", provider: "zhipuai", description: "Flagship model" },
  { id: "glm-4-flash", name: "GLM-4 Flash", provider: "zhipuai", description: "Fast & cost-effective" },
  { id: "glm-4v", name: "GLM-4V", provider: "zhipuai", description: "Multimodal" },
  // OpenAI Models
  { id: "gpt-4o", name: "GPT-4o", provider: "openai", description: "Latest flagship" },
  { id: "gpt-4o-mini", name: "GPT-4o Mini", provider: "openai", description: "Fast & affordable" },
  // DeepSeek Models
  { id: "deepseek-chat", name: "DeepSeek Chat", provider: "deepseek", description: "General conversation" },
  { id: "deepseek-reasoner", name: "DeepSeek Reasoner", provider: "deepseek", description: "Advanced reasoning" },
]

export const PROVIDERS = [
  { id: "zhipuai", name: "ZhipuAI (GLM)" },
  { id: "openai", name: "OpenAI" },
  { id: "deepseek", name: "DeepSeek" },
] as const

export interface OCRProfile {
  provider: string
  mode: string
  api_url: string
  token: string
  model: string
  use_chart_recognition: boolean
  use_doc_orientation_classify: boolean
  use_doc_unwarping: boolean
}

export interface OCRConfigData {
  profiles: Record<string, OCRProfile>
  bindings: Record<string, string>
}

export const OCR_PROVIDERS = [
  { id: "paddleocr", name: "PaddleOCR" },
  { id: "mineru", name: "MineRU" },
] as const

export const OCR_MODES = [
  { id: "sync", name: "同步模式", desc: "适合小文件，快速返回" },
  { id: "async", name: "异步模式", desc: "适合大文件，服务端异步处理" },
] as const

export const MINERU_MODEL_VERSIONS = [
  { id: "vlm", name: "VLM", desc: "视觉语言模型，精度更高" },
  { id: "doclayout_yolo", name: "DocLayout YOLO", desc: "传统布局检测，速度更快" },
] as const

export interface TranslationEntry {
  id: string
  filename: string
  display_name: string
  created_at: string
  has_ocr: boolean
  provider?: string
  model?: string
  enable_ocr?: boolean
}
