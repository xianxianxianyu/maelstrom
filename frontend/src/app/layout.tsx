import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "PDF to Markdown Translator",
  description: "Academic document translation with preserved structure",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
