"use client"

import { createContext, useContext, useState, useEffect, useMemo, ReactNode } from "react"

export interface FontOption {
  label: string
  value: string
  /** CSS font-family 值 */
  family: string
  category: "sans" | "serif" | "mono" | "system"
}

export const FONT_OPTIONS: FontOption[] = [
  // 系统默认
  { label: "系统默认", value: "system", family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', category: "system" },
  // 无衬线
  { label: "Inter", value: "inter", family: '"Inter", "Segoe UI", sans-serif', category: "sans" },
  { label: "Noto Sans SC", value: "noto-sans", family: '"Noto Sans SC", "Microsoft YaHei", sans-serif', category: "sans" },
  { label: "Source Han Sans", value: "source-han-sans", family: '"Source Han Sans SC", "Noto Sans SC", "Microsoft YaHei", sans-serif', category: "sans" },
  { label: "Helvetica Neue", value: "helvetica", family: '"Helvetica Neue", Helvetica, Arial, sans-serif', category: "sans" },
  // 衬线 — 阅读友好
  { label: "Georgia", value: "georgia", family: 'Georgia, "Times New Roman", serif', category: "serif" },
  { label: "Noto Serif SC", value: "noto-serif", family: '"Noto Serif SC", "Songti SC", "SimSun", serif', category: "serif" },
  { label: "Source Han Serif", value: "source-han-serif", family: '"Source Han Serif SC", "Noto Serif SC", "Songti SC", serif', category: "serif" },
  { label: "Palatino", value: "palatino", family: '"Palatino Linotype", Palatino, "Book Antiqua", serif', category: "serif" },
  { label: "Charter", value: "charter", family: 'Charter, "Bitstream Charter", Georgia, serif', category: "serif" },
  // 等宽 — Console 风格
  { label: "JetBrains Mono", value: "jetbrains", family: '"JetBrains Mono", "Fira Code", monospace', category: "mono" },
  { label: "Fira Code", value: "fira-code", family: '"Fira Code", "Source Code Pro", monospace', category: "mono" },
  { label: "Source Code Pro", value: "source-code", family: '"Source Code Pro", "Consolas", monospace', category: "mono" },
  { label: "Cascadia Code", value: "cascadia", family: '"Cascadia Code", "Cascadia Mono", Consolas, monospace', category: "mono" },
  { label: "Consolas", value: "consolas", family: 'Consolas, "Courier New", monospace', category: "mono" },
  { label: "Monaco", value: "monaco", family: 'Monaco, "Lucida Console", monospace', category: "mono" },
]

export type ContentWidth = "compact" | "standard" | "wide"

export interface ReaderSettings {
  fontSize: number        // 12–24
  fontValue: string       // FONT_OPTIONS[].value
  lineHeight: number      // 1.4–2.4
  contentWidth: ContentWidth
}

const DEFAULTS: ReaderSettings = {
  fontSize: 22,
  fontValue: "jetbrains",
  lineHeight: 1.5,
  contentWidth: "standard",
}

const STORAGE_KEY = "reader-settings"

interface ReaderSettingsState extends ReaderSettings {
  setFontSize: (v: number) => void
  setFontValue: (v: string) => void
  setLineHeight: (v: number) => void
  setContentWidth: (v: ContentWidth) => void
  reset: () => void
  /** 当前字体的 CSS font-family */
  fontFamily: string
}

const ReaderSettingsContext = createContext<ReaderSettingsState | null>(null)

function loadSettings(): ReaderSettings {
  if (typeof window === "undefined") return DEFAULTS
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULTS
    const parsed = JSON.parse(raw)
    return { ...DEFAULTS, ...parsed }
  } catch {
    return DEFAULTS
  }
}

function saveSettings(s: ReaderSettings) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)) } catch { /* ignore */ }
}

export function ReaderSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<ReaderSettings>(DEFAULTS)

  // hydrate from localStorage after mount
  useEffect(() => { setSettings(loadSettings()) }, [])

  // persist on change
  useEffect(() => { saveSettings(settings) }, [settings])

  const value = useMemo<ReaderSettingsState>(() => {
    const font = FONT_OPTIONS.find(f => f.value === settings.fontValue) || FONT_OPTIONS[0]
    return {
      ...settings,
      fontFamily: font.family,
      setFontSize: (v) => setSettings(prev => ({ ...prev, fontSize: v })),
      setFontValue: (v) => setSettings(prev => ({ ...prev, fontValue: v })),
      setLineHeight: (v) => setSettings(prev => ({ ...prev, lineHeight: v })),
      setContentWidth: (v) => setSettings(prev => ({ ...prev, contentWidth: v })),
      reset: () => setSettings(DEFAULTS),
    }
  }, [settings])

  return (
    <ReaderSettingsContext.Provider value={value}>
      {children}
    </ReaderSettingsContext.Provider>
  )
}

export function useReaderSettings(): ReaderSettingsState {
  const ctx = useContext(ReaderSettingsContext)
  if (!ctx) throw new Error("useReaderSettings must be used within ReaderSettingsProvider")
  return ctx
}
