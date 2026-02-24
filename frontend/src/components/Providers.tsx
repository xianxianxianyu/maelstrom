"use client"

import { ReactNode } from "react"
import { LLMConfigProvider } from "@/contexts/LLMConfigContext"
import { ReaderSettingsProvider } from "@/contexts/ReaderSettingsContext"
import { TranslationSettingsProvider } from "@/contexts/TranslationSettingsContext"

export function Providers({ children }: { children: ReactNode }) {
  return (
    <LLMConfigProvider>
      <TranslationSettingsProvider>
        <ReaderSettingsProvider>
          {children}
        </ReaderSettingsProvider>
      </TranslationSettingsProvider>
    </LLMConfigProvider>
  )
}
