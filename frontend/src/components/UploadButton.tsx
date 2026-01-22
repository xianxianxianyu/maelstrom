"use client"

import { useRef, useState } from "react"

interface Props {
  onUpload: (file: File) => void
  disabled: boolean
}

export function UploadButton({ onUpload, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState<string>("")

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setFileName(file.name)
      onUpload(file)
    }
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        onChange={handleChange}
        className="hidden"
        disabled={disabled}
      />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        className="px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white font-medium rounded transition-colors shadow-sm"
      >
        {disabled ? "Processing..." : "Import PDF Document"}
      </button>
      {fileName && (
        <p className="text-sm text-slate-600 font-light">
          Selected: {fileName}
        </p>
      )}
    </div>
  )
}
