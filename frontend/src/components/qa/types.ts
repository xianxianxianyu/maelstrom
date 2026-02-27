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
  execution?: QAExecutionSnapshot
}

export interface Citation {
  text: string
  source: string
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
