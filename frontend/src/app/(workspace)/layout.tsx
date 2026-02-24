import type { ReactNode } from "react"
import WorkspaceSidebar from "@/components/WorkspaceSidebar"

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <div className="h-screen flex overflow-hidden bg-gray-100">
      <WorkspaceSidebar />
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  )
}
