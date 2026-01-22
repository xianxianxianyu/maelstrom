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