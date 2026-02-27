'use client'

import React, { useState, useEffect, useCallback } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:3301"

// 简化的日志条目类型
interface LogEntry {
  id: string
  timestamp: string
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL'
  event_type: string
  trace_id?: string
  session_id?: string
  message: string
  context?: Record<string, any>
  agent_name?: string
  tool_name?: string
  duration_ms?: number
}

// 简化的日志查看器属性
interface LogViewerProps {
  sessionId?: string
  docId?: string
  autoRefresh?: boolean
  refreshInterval?: number
  maxHeight?: string
}

export function LogViewer({
  sessionId,
  docId,
  autoRefresh: initialAutoRefresh = false,
  refreshInterval = 5000,
  maxHeight = '600px',
}: LogViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filterLevel, setFilterLevel] = useState<string>('ALL')
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(initialAutoRefresh)

  // 获取日志
  const fetchLogs = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const params = new URLSearchParams()
      if (sessionId) params.append('session_id', sessionId)
      if (filterLevel !== 'ALL') params.append('level', filterLevel)
      if (searchTerm) params.append('event_type', searchTerm)

      const response = await fetch(`${API_BASE}/api/agent/qa/logs?${params.toString()}`)
      
      if (!response.ok) {
        throw new Error(`Failed to fetch logs: ${response.statusText}`)
      }

      const data = await response.json()
      setLogs(data.logs || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setIsLoading(false)
    }
  }, [sessionId, filterLevel, searchTerm])

  const selectedTraceCount = logs.filter((log) => log.trace_id === selectedTrace).length

  // 自动刷新
  useEffect(() => {
    fetchLogs()
    
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, refreshInterval)
      return () => clearInterval(interval)
    }
  }, [fetchLogs, autoRefresh, refreshInterval])

  // 获取级别颜色
  const getLevelColor = (level: string) => {
    switch (level) {
      case 'DEBUG': return 'bg-gray-500'
      case 'INFO': return 'bg-blue-500'
      case 'WARN': return 'bg-yellow-500'
      case 'ERROR': return 'bg-red-500'
      case 'CRITICAL': return 'bg-purple-600'
      default: return 'bg-gray-400'
    }
  }

  // 获取级别文本颜色
  const getLevelTextColor = (level: string) => {
    switch (level) {
      case 'DEBUG': return 'text-gray-600'
      case 'INFO': return 'text-blue-600'
      case 'WARN': return 'text-yellow-600'
      case 'ERROR': return 'text-red-600'
      case 'CRITICAL': return 'text-purple-700'
      default: return 'text-gray-500'
    }
  }

  // 格式化时间戳
  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3,
    })
  }

  return (
    <div className="w-full">
      {/* 工具栏 */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {/* 级别过滤 */}
        <select
          value={filterLevel}
          onChange={(e) => setFilterLevel(e.target.value)}
          className="px-3 py-1.5 text-sm border rounded-md bg-white"
        >
          <option value="ALL">全部级别</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>

        {/* 搜索框 */}
        <input
          type="text"
          placeholder="搜索日志内容..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="px-3 py-1.5 text-sm border rounded-md flex-1 min-w-[200px]"
        />

        {/* 刷新按钮 */}
        <button
          onClick={fetchLogs}
          disabled={isLoading}
          className="px-4 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50"
        >
          {isLoading ? '加载中...' : '刷新'}
        </button>

        {/* 自动刷新开关 */}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="rounded"
          />
          自动刷新
        </label>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-700 text-sm">
          错误: {error}
        </div>
      )}

      {/* 日志列表 */}
      <div 
        className="border rounded-md overflow-hidden"
        style={{ maxHeight }}
      >
        <div className="overflow-auto" style={{ maxHeight }}>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-24">时间</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-20">级别</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-32">事件类型</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">消息</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-3 py-8 text-center text-gray-500">
                    {isLoading ? '加载中...' : '暂无日志记录'}
                  </td>
                </tr>
              ) : (
                logs.map((log, index) => (
                  <tr 
                    key={log.id || index}
                    className={`hover:bg-gray-50 cursor-pointer ${
                      selectedTrace === log.trace_id ? 'bg-blue-50' : ''
                    }`}
                    onClick={() => {
                      const nextTrace = log.trace_id ?? null
                      setSelectedTrace(selectedTrace === nextTrace ? null : nextTrace)
                    }}
                  >
                    <td className="px-3 py-2 whitespace-nowrap text-gray-600">
                      {formatTimestamp(log.timestamp)}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium text-white ${getLevelColor(log.level)}`}>
                        {log.level}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-600">
                      {log.event_type}
                    </td>
                    <td className="px-3 py-2">
                      <div className="truncate max-w-md" title={log.message}>
                        {log.message}
                      </div>
                      {log.trace_id && (
                        <div className="text-xs text-gray-400 mt-0.5">
                          Trace: {log.trace_id.slice(0, 16)}...
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 选中 Trace 的详细信息 */}
      {selectedTrace && (
        <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-md">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium text-blue-900">
              Trace 详情: {selectedTrace.slice(0, 24)}...
            </h3>
            <button
              onClick={() => setSelectedTrace(null)}
              className="text-blue-600 hover:text-blue-800"
            >
              关闭
            </button>
          </div>
          <div className="text-sm text-blue-800">
            <p>该 Trace 包含 {selectedTraceCount} 条日志记录</p>
            <p className="mt-1">点击刷新按钮查看完整链路分析</p>
          </div>
        </div>
      )}

      {/* 统计信息 */}
      <div className="mt-4 flex items-center gap-4 text-sm text-gray-600">
        <span>总计: {logs.length} 条日志</span>
        {selectedTrace && <span className="text-blue-600">已选择 Trace</span>}
      </div>
    </div>
  )
}
