"use client"

import { ReactNode } from "react"
import { LLMConfigProvider } from "@/contexts/LLMConfigContext"
import { ReaderSettingsProvider } from "@/contexts/ReaderSettingsContext"

export function Providers({ children }: { children: ReactNode }) {
  return (
    <LLMConfigProvider>
      <ReaderSettingsProvider>
        {children}
      </ReaderSettingsProvider>
    </LLMConfigProvider>
  )
}
