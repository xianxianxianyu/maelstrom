"use client"

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

export type OutputFormat = "bilingual" | "target_only"

interface TranslationSettingsState {
  systemPrompt: string
  outputFormat: OutputFormat
  setSystemPrompt: (value: string) => void
  setOutputFormat: (value: OutputFormat) => void
  reset: () => void
}

export const DEFAULT_SYSTEM_PROMPT =
  "You are a professional English-to-Chinese translator for academic papers.\n" +
  "RULES:\n" +
  "1. Translate the given English text into Chinese. Do NOT explain, summarize, or expand the content.\n" +
  "2. Output format: first the original English paragraph, then immediately below it the Chinese translation.\n" +
  "3. Preserve all Markdown formatting: headings (#, ##, ###), bold, italic, lists, tables, math formulas.\n" +
  "4. Do NOT add any content that is not in the original text.\n" +
  "5. Do NOT wrap output in code fences.\n" +
  "6. For short fragments (author names, figure labels, references), just translate directly without explanation.\n" +
  "7. Keep proper nouns, model names, and technical terms (e.g. Transformer, KV Cache, LLM) in English within the Chinese translation."

const DEFAULT_STATE: Pick<TranslationSettingsState, "systemPrompt" | "outputFormat"> = {
  systemPrompt: DEFAULT_SYSTEM_PROMPT,
  outputFormat: "bilingual",
}

const STORAGE_KEY = "translation-settings"

const TranslationSettingsContext = createContext<TranslationSettingsState | null>(null)

function loadFromStorage() {
  if (typeof window === "undefined") {
    return DEFAULT_STATE
  }

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return DEFAULT_STATE
    }
    const parsed = JSON.parse(raw)
    return {
      ...DEFAULT_STATE,
      ...parsed,
    }
  } catch {
    return DEFAULT_STATE
  }
}

function saveToStorage(value: Pick<TranslationSettingsState, "systemPrompt" | "outputFormat">) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
  }
}

export function TranslationSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(DEFAULT_STATE)

  useEffect(() => {
    setSettings(loadFromStorage())
  }, [])

  useEffect(() => {
    saveToStorage(settings)
  }, [settings])

  const value = useMemo<TranslationSettingsState>(() => ({
    systemPrompt: settings.systemPrompt,
    outputFormat: settings.outputFormat,
    setSystemPrompt: (next) => setSettings((prev) => ({ ...prev, systemPrompt: next })),
    setOutputFormat: (next) => setSettings((prev) => ({ ...prev, outputFormat: next })),
    reset: () => setSettings(DEFAULT_STATE),
  }), [settings])

  return (
    <TranslationSettingsContext.Provider value={value}>
      {children}
    </TranslationSettingsContext.Provider>
  )
}

export function useTranslationSettings() {
  const context = useContext(TranslationSettingsContext)
  if (!context) {
    throw new Error("useTranslationSettings must be used within TranslationSettingsProvider")
  }
  return context
}
