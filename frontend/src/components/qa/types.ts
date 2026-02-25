export interface Session {
  id: string
  title: string
  createdAt: Date
  updatedAt: Date
  docId?: string
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  citations?: Array<{
    text: string
    source: string
  }>
  timestamp: Date
  isStreaming?: boolean
}

export interface Citation {
  text: string
  source: string
}
