"use client"

import { useState, useEffect, useCallback } from "react"
import { FloatingQAButton } from "./FloatingQAButton"
import { QADialog } from "./QADialog"
import { useQASession } from "@/hooks/useQASession"

interface QAContainerProps {
  docId?: string
}

export function QAContainer({ docId }: QAContainerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [hasUnread, setHasUnread] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)

  const {
    sessions,
    currentSession,
    messages,
    isLoading,
    selectedProfile,
    profileNames,
    setSelectedProfile,
    createSession,
    switchSession,
    deleteSession,
    sendMessage,
  } = useQASession({ docId })

  // 当有新消息且对话框关闭时，更新未读计数
  useEffect(() => {
    if (!isOpen && messages.length > 0) {
      const lastMessage = messages[messages.length - 1]
      if (lastMessage.role === "assistant") {
        setHasUnread(true)
        setUnreadCount((prev) => prev + 1)
      }
    }
  }, [messages, isOpen])

  // 打开对话框时重置未读状态
  const handleOpen = useCallback(() => {
    setIsOpen(true)
    setIsMinimized(false)
    setHasUnread(false)
    setUnreadCount(0)
  }, [])

  const handleClose = useCallback(() => {
    setIsOpen(false)
    setIsMinimized(false)
  }, [])

  const handleMinimize = useCallback(() => {
    setIsMinimized(true)
    setIsOpen(false)
  }, [])

  return (
    <>
      {/* 悬浮按钮 */}
      <FloatingQAButton
        onClick={handleOpen}
        hasUnread={hasUnread}
        unreadCount={unreadCount}
      />

      {/* QA 对话框 */}
      <QADialog
        isOpen={isOpen}
        isMinimized={isMinimized}
        onClose={handleClose}
        onMinimize={handleMinimize}
        sessions={sessions}
        currentSession={currentSession}
        messages={messages}
        isLoading={isLoading}
        selectedProfile={selectedProfile}
        profileNames={profileNames}
        onProfileChange={setSelectedProfile}
        onCreateSession={createSession}
        onSwitchSession={switchSession}
        onDeleteSession={deleteSession}
        onSendMessage={sendMessage}
        docId={docId}
      />
    </>
  )
}
