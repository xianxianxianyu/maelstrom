"use client"

import { ReactNode } from "react"
import { LLMConfigProvider } from "@/contexts/LLMConfigContext"

export function Providers({ children }: { children: ReactNode }) {
  return (
    <LLMConfigProvider>
      {children}
    </LLMConfigProvider>
  )
}
