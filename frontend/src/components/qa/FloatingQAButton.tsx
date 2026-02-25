"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { cn } from "@/lib/utils"

interface FloatingQAButtonProps {
  onClick: () => void
  hasUnread?: boolean
  unreadCount?: number
}

interface Position {
  x: number
  y: number
}

const BUTTON_SIZE = 56
const MARGIN = 24

export function FloatingQAButton({
  onClick,
  hasUnread = false,
  unreadCount = 0,
}: FloatingQAButtonProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [position, setPosition] = useState<Position>({ x: -1, y: -1 }) // -1 表示未初始化
  const [isHovering, setIsHovering] = useState(false)
  const dragStartPos = useRef<Position>({ x: 0, y: 0 })
  const buttonRef = useRef<HTMLButtonElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // 初始化位置到右下角
  useEffect(() => {
    if (position.x === -1) {
      const viewportWidth = window.innerWidth
      const viewportHeight = window.innerHeight
      setPosition({
        x: viewportWidth - BUTTON_SIZE - MARGIN,
        y: viewportHeight - BUTTON_SIZE - MARGIN,
      })
    }
  }, [position.x])

  // 处理拖拽
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    dragStartPos.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y,
    }
  }, [position])

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    const touch = e.touches[0]
    setIsDragging(true)
    dragStartPos.current = {
      x: touch.clientX - position.x,
      y: touch.clientY - position.y,
    }
  }, [position])

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent) => {
      const viewportWidth = window.innerWidth
      const viewportHeight = window.innerHeight
      
      let newX = e.clientX - dragStartPos.current.x
      let newY = e.clientY - dragStartPos.current.y

      // 限制在视口内
      newX = Math.max(MARGIN, Math.min(viewportWidth - BUTTON_SIZE - MARGIN, newX))
      newY = Math.max(MARGIN, Math.min(viewportHeight - BUTTON_SIZE - MARGIN, newY))

      setPosition({ x: newX, y: newY })
    }

    const handleTouchMove = (e: TouchEvent) => {
      const touch = e.touches[0]
      const viewportWidth = window.innerWidth
      const viewportHeight = window.innerHeight
      
      let newX = touch.clientX - dragStartPos.current.x
      let newY = touch.clientY - dragStartPos.current.y

      newX = Math.max(MARGIN, Math.min(viewportWidth - BUTTON_SIZE - MARGIN, newX))
      newY = Math.max(MARGIN, Math.min(viewportHeight - BUTTON_SIZE - MARGIN, newY))

      setPosition({ x: newX, y: newY })
    }

    const handleMouseUp = () => {
      setIsDragging(false)
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)
    document.addEventListener("touchmove", handleTouchMove, { passive: false })
    document.addEventListener("touchend", handleMouseUp)

    return () => {
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
      document.removeEventListener("touchmove", handleTouchMove)
      document.removeEventListener("touchend", handleMouseUp)
    }
  }, [isDragging])

  const handleClick = () => {
    if (!isDragging) {
      onClick()
    }
  }

  // 吸附到最近的角落
  const snapToCorner = useCallback(() => {
    const viewportWidth = window.innerWidth
    const viewportHeight = window.innerHeight
    
    const centerX = position.x + BUTTON_SIZE / 2
    const centerY = position.y + BUTTON_SIZE / 2
    
    // 计算到四个角的距离
    const distances = [
      { x: MARGIN, y: MARGIN }, // 左上
      { x: viewportWidth - BUTTON_SIZE - MARGIN, y: MARGIN }, // 右上
      { x: MARGIN, y: viewportHeight - BUTTON_SIZE - MARGIN }, // 左下
      { x: viewportWidth - BUTTON_SIZE - MARGIN, y: viewportHeight - BUTTON_SIZE - MARGIN }, // 右下
    ]
    
    const nearest = distances.reduce((prev, curr) => {
      const prevDist = Math.hypot(prev.x - centerX, prev.y - centerY)
      const currDist = Math.hypot(curr.x - centerX, curr.y - centerY)
      return currDist < prevDist ? curr : prev
    })
    
    setPosition(nearest)
  }, [position])

  // 拖拽结束后吸附
  useEffect(() => {
    if (!isDragging && position.x !== -1) {
      const timer = setTimeout(snapToCorner, 100)
      return () => clearTimeout(timer)
    }
  }, [isDragging, position, snapToCorner])

  if (position.x === -1) return null

  return (
    <div
      ref={containerRef}
      className="fixed z-50"
      style={{
        left: position.x,
        top: position.y,
        width: BUTTON_SIZE,
        height: BUTTON_SIZE,
      }}
    >
      <button
        ref={buttonRef}
        onClick={handleClick}
        onMouseDown={handleMouseDown}
        onTouchStart={handleTouchStart}
        onMouseEnter={() => setIsHovering(true)}
        onMouseLeave={() => setIsHovering(false)}
        className={cn(
          "w-full h-full rounded-full flex items-center justify-center transition-all duration-300",
          "bg-indigo-600 text-white shadow-lg",
          isDragging ? "cursor-grabbing scale-110" : "cursor-grab hover:scale-110",
          isHovering && !isDragging && "shadow-xl shadow-indigo-500/30"
        )}
        style={{
          touchAction: "none",
        }}
      >
        {/* 消息图标 */}
        <svg
          className="w-6 h-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>

        {/* 未读消息提示 */}
        {(hasUnread || unreadCount > 0) && (
          <span
            className={cn(
              "absolute -top-1 -right-1 flex items-center justify-center",
              "min-w-[20px] h-5 px-1.5 rounded-full text-xs font-bold",
              "bg-red-500 text-white animate-pulse"
            )}
          >
            {unreadCount > 99 ? "99+" : unreadCount || "•"}
          </span>
        )}
      </button>

      {/* 悬停提示 */}
      {isHovering && !isDragging && (
        <div
          className={cn(
            "absolute right-full mr-3 top-1/2 -translate-y-1/2",
            "px-3 py-2 bg-gray-900 text-white text-sm rounded-lg",
            "whitespace-nowrap opacity-0 animate-fade-in"
          )}
          style={{
            animation: "fadeIn 0.2s ease-out forwards",
          }}
        >
          点击打开问答助手
          <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 w-2 h-2 bg-gray-900 rotate-45" />
        </div>
      )}

      <style jsx>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-50%) translateX(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(-50%) translateX(0);
          }
        }
      `}</style>
    </div>
  )
}
