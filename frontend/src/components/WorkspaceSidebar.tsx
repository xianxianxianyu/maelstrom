"use client"

import type { ReactNode } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"

type NavItem = {
  href: string
  label: string
  icon: (active: boolean) => ReactNode
}

function navIconClass(active: boolean) {
  return active ? "text-indigo-600" : "text-gray-400 group-hover:text-gray-600"
}

const NAV_ITEMS: NavItem[] = [
  {
    href: "/translate",
    label: "翻译",
    icon: (active) => (
      <svg className={`w-5 h-5 ${navIconClass(active)}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    href: "/history",
    label: "历史",
    icon: (active) => (
      <svg className={`w-5 h-5 ${navIconClass(active)}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    href: "/config",
    label: "配置",
    icon: (active) => (
      <svg className={`w-5 h-5 ${navIconClass(active)}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
]

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`)
}

export default function WorkspaceSidebar() {
  const pathname = usePathname()

  return (
    <aside className="w-16 bg-white border-r border-gray-200 flex flex-col items-center py-4 gap-3">
      <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center mb-2">
        <span className="text-indigo-600 text-sm font-bold">M</span>
      </div>

      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href)
        return (
          <Link
            key={item.href}
            href={item.href}
            title={item.label}
            className={`group w-10 h-10 rounded-xl flex items-center justify-center transition ${
              active ? "bg-indigo-50 border border-indigo-100" : "hover:bg-gray-100"
            }`}
            aria-label={item.label}
          >
            {item.icon(active)}
          </Link>
        )
      })}
    </aside>
  )
}
