"use client"

import { useState } from "react"
import { UploadButton } from "@/components/UploadButton"
import { MarkdownViewer } from "@/components/MarkdownViewer"
import { LoadingState } from "@/components/LoadingState"
import { ModelSettings } from "@/components/ModelSettings"
import { uploadPDF } from "@/lib/api"
import { ModelConfig } from "@/types"

export default function Home() {
  const [markdown, setMarkdown] = useState<string>("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>("")
  const [modelConfig, setModelConfig] = useState<ModelConfig>({
    provider: "zhipuai",
    model: "glm-4"
  })

  const handleUpload = async (file: File) => {
    setLoading(true)
    setError("")
    try {
      const result = await uploadPDF(file, modelConfig)
      setMarkdown(result.markdown)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <ModelSettings
        onConfigChange={setModelConfig}
        currentProvider={modelConfig.provider}
        currentModel={modelConfig.model}
      />

      <div className="max-w-4xl mx-auto px-8 py-12">
        <header className="mb-12 text-center">
          <h1 className="text-4xl font-light tracking-tight text-slate-900 mb-3">
            PDF to Markdown Translator
          </h1>
          <p className="text-slate-600 font-light">
            Academic document translation with preserved structure
          </p>
          <p className="text-sm text-slate-500 mt-2">
            Using: {modelConfig.provider} / {modelConfig.model}
          </p>
        </header>

        <UploadButton onUpload={handleUpload} disabled={loading} />

        {loading && <LoadingState />}

        {error && (
          <div className="mt-8 p-4 bg-red-50 border border-red-200 text-red-700 rounded">
            {error}
          </div>
        )}

        {markdown && !loading && (
          <MarkdownViewer content={markdown} />
        )}
      </div>
    </main>
  )
}
