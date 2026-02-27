"use client"

import { useMemo, useState } from "react"
import type { ReactNode } from "react"
import type { QAExecutionRun, QAExecutionSnapshot, QAExecutionWorkerDescriptor } from "./types"

interface ExecutionFlowPanelProps {
  execution: QAExecutionSnapshot
  onRetryExecution?: (traceId: string) => void
}

type GroupState = Record<string, boolean>

const ROLE_ORDER = ["MCP", "RESEARCHER", "CODER", "VERIFIER", "AGGREGATOR", "FALLBACK"]

export function ExecutionFlowPanel({ execution, onRetryExecution }: ExecutionFlowPanelProps) {
  const [selectedWorker, setSelectedWorker] = useState<QAExecutionWorkerDescriptor | null>(null)
  const [selectedRun, setSelectedRun] = useState<QAExecutionRun | null>(null)
  const [groupState, setGroupState] = useState<GroupState>({})

  const workerRuns = useMemo(() => execution.workers || [], [execution.workers])
  const groupedRuns = useMemo(() => groupRunsByRole(workerRuns), [workerRuns])
  const hasFailure = workerRuns.some((run) => (run.status || "").toUpperCase().includes("FAIL") || run.success === false)
  const timeline = buildTimeline(execution)

  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold text-slate-700">Agent 集群执行流程</div>
        {onRetryExecution ? (
          <button
            onClick={() => onRetryExecution(execution.traceId)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-100"
          >
            重试执行
          </button>
        ) : null}
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="text-xs font-medium text-slate-600 mb-2">执行时间轴</div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {timeline.map((step) => (
            <div key={step.key} className="rounded-md border border-slate-200 p-2">
              <div className="flex items-center gap-2">
                <span
                  className={
                    "inline-block h-2 w-2 rounded-full " +
                    (step.state === "done"
                      ? "bg-emerald-500"
                      : step.state === "running"
                        ? "bg-indigo-500 animate-pulse"
                        : step.state === "failed"
                          ? "bg-rose-500"
                          : "bg-slate-300")
                  }
                />
                <span className="text-[11px] font-medium text-slate-700">{step.label}</span>
              </div>
              <div className="mt-1 h-1 rounded-full bg-slate-200 overflow-hidden">
                <div className="h-full bg-indigo-500 transition-all" style={{ width: `${step.progress}%` }} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="text-xs font-medium text-slate-600 mb-2">Manager Agent · 问题识别</div>
        <div className="space-y-2">
          {(execution.manager?.problems || []).length === 0 ? (
            <div className="text-xs text-slate-400">未拆分子问题，进入默认路径</div>
          ) : (
            execution.manager.problems?.map((problem, index) => (
              <div key={problem.sub_problem_id || `${index}`} className="rounded-md border border-slate-200 p-2">
                <div className="text-xs text-slate-800">{problem.question || "未命名问题"}</div>
                <div className="mt-1 text-[11px] text-slate-500">
                  intent: {problem.intent || "-"} · route: {problem.route_type || "-"}
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="text-xs font-medium text-slate-600 mb-2">Plan Agent · Worker 集群</div>
        <div className="flex flex-wrap gap-2">
          {(execution.plan?.workers || []).map((worker) => (
            <button
              key={worker.workerId}
              onClick={() => setSelectedWorker(worker)}
              className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-100"
            >
              {worker.role}
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="text-xs font-medium text-slate-600 mb-2">Worker 执行看板</div>
        <div className="space-y-2">
          {Object.keys(groupedRuns).length === 0 ? (
            <div className="text-xs text-slate-400">暂无 worker 执行记录</div>
          ) : (
            orderedRoles(groupedRuns).map((role) => {
              const runs = groupedRuns[role]
              const collapsed = groupState[role] ?? false
              const groupProgress = calcGroupProgress(runs)
              return (
                <div key={role} className="rounded-md border border-slate-200">
                  <button
                    onClick={() =>
                      setGroupState((prev) => ({
                        ...prev,
                        [role]: !collapsed,
                      }))
                    }
                    className="w-full px-3 py-2 flex items-center justify-between text-left"
                  >
                    <div className="text-xs font-medium text-slate-700">{role} · {runs.length} 节点</div>
                    <div className="text-[11px] text-slate-500">{collapsed ? "展开" : "收起"}</div>
                  </button>
                  <div className="px-3 pb-2">
                    <div className="h-1.5 rounded-full bg-slate-200 overflow-hidden">
                      <div className="h-full bg-indigo-500 transition-all" style={{ width: `${groupProgress}%` }} />
                    </div>
                  </div>
                  {collapsed ? null : (
                    <div className="px-3 pb-3 space-y-2">
                      {runs.map((run, index) => {
                        const status = run.status || (run.success ? "COMPLETED" : "FAILED")
                        const progress = Number(run.progress ?? (run.success ? 100 : 0))
                        return (
                          <button
                            key={`${run.sub_problem_id || run.node_id || role + index}`}
                            onClick={() => setSelectedRun(run)}
                            className="w-full rounded-md border border-slate-200 p-2 text-left hover:bg-slate-50"
                          >
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-medium text-slate-800">{run.capability || run.agent || "-"}</span>
                              <span className="text-slate-500">{status}</span>
                            </div>
                            <div className="mt-1 h-1.5 rounded-full bg-slate-200 overflow-hidden">
                              <div className="h-full bg-indigo-500 transition-all" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-3">
        <div className="text-xs font-medium text-slate-600">执行摘要</div>
        <div className="mt-1 text-[11px] text-slate-500">
          trace: {execution.traceId} · fallback: {execution.summary?.fallbackUsed ? "yes" : "no"} · status: {execution.summary?.finalStatus || "-"}
        </div>
        {hasFailure && onRetryExecution ? (
          <button
            onClick={() => onRetryExecution(execution.traceId)}
            className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700 hover:bg-rose-100"
          >
            发现失败节点，重试本次执行
          </button>
        ) : null}
      </section>

      {selectedWorker ? (
        <WorkerIdentityModal worker={selectedWorker} onClose={() => setSelectedWorker(null)} />
      ) : null}
      {selectedRun ? (
        <WorkerTaskModal
          run={selectedRun}
          traceId={execution.traceId}
          onRetryExecution={onRetryExecution}
          onClose={() => setSelectedRun(null)}
        />
      ) : null}
    </div>
  )
}

function WorkerIdentityModal({
  worker,
  onClose,
}: {
  worker: QAExecutionWorkerDescriptor
  onClose: () => void
}) {
  return (
    <ModalShell title={`${worker.role} · 身份 Prompt`} onClose={onClose}>
      <pre className="whitespace-pre-wrap text-xs text-slate-700 bg-slate-50 rounded-md p-2">{worker.identityPrompt || "(empty)"}</pre>
      <div className="mt-2 text-[11px] text-slate-500">capabilities: {(worker.capabilities || []).join(", ") || "-"}</div>
    </ModalShell>
  )
}

function WorkerTaskModal({
  run,
  traceId,
  onRetryExecution,
  onClose,
}: {
  run: QAExecutionRun
  traceId: string
  onRetryExecution?: (traceId: string) => void
  onClose: () => void
}) {
  const outputText = JSON.stringify(run.output || {}, null, 2)
  return (
    <ModalShell title={`${run.role || "Worker"} · 任务详情`} onClose={onClose}>
      <div className="space-y-2 text-xs">
        <div>
          <div className="text-slate-500">Task Prompt</div>
          <pre className="whitespace-pre-wrap text-slate-700 bg-slate-50 rounded-md p-2">{run.task_prompt || "(empty)"}</pre>
        </div>
        <div>
          <div className="text-slate-500">产物</div>
          <pre className="whitespace-pre-wrap text-slate-700 bg-slate-50 rounded-md p-2">{outputText}</pre>
        </div>
        {run.artifact_preview ? <div className="text-slate-700 bg-slate-50 rounded-md p-2">{run.artifact_preview}</div> : null}
        {onRetryExecution ? (
          <button
            onClick={() => {
              onRetryExecution(traceId)
              onClose()
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-1 text-[11px] text-slate-700 hover:bg-slate-100"
          >
            重试本次执行
          </button>
        ) : null}
      </div>
    </ModalShell>
  )
}

function ModalShell({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/35">
      <div className="w-[min(680px,92vw)] max-h-[80vh] overflow-auto rounded-xl bg-white shadow-xl border border-slate-200">
        <div className="sticky top-0 bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-800">{title}</div>
          <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-700">关闭</button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  )
}

function groupRunsByRole(runs: QAExecutionRun[]): Record<string, QAExecutionRun[]> {
  return runs.reduce<Record<string, QAExecutionRun[]>>((acc, run) => {
    const role = run.role || "WORKER"
    if (!acc[role]) {
      acc[role] = []
    }
    acc[role].push(run)
    return acc
  }, {})
}

function orderedRoles(grouped: Record<string, QAExecutionRun[]>): string[] {
  const existing = Object.keys(grouped)
  const sorted = [...existing].sort((a, b) => {
    const ia = ROLE_ORDER.indexOf(a)
    const ib = ROLE_ORDER.indexOf(b)
    if (ia === -1 && ib === -1) return a.localeCompare(b)
    if (ia === -1) return 1
    if (ib === -1) return -1
    return ia - ib
  })
  return sorted
}

function calcGroupProgress(runs: QAExecutionRun[]): number {
  if (runs.length === 0) return 0
  const total = runs.reduce((acc, run) => acc + Number(run.progress ?? (run.success ? 100 : 0)), 0)
  return Math.max(0, Math.min(100, Math.round(total / runs.length)))
}

function buildTimeline(execution: QAExecutionSnapshot): Array<{ key: string; label: string; state: string; progress: number }> {
  const managerDone = Boolean(execution.manager?.stage1 || (execution.manager?.problems || []).length > 0)
  const planDone = Boolean(execution.plan?.planId || (execution.plan?.workers || []).length > 0)
  const workerProgress = calcGroupProgress(execution.workers || [])
  const hasFailure = (execution.workers || []).some((run) => run.success === false || (run.status || "").toUpperCase().includes("FAIL"))
  const finalDone = (execution.summary?.finalStatus || "").toLowerCase() === "complete"

  return [
    {
      key: "manager",
      label: "Manager",
      state: managerDone ? "done" : "running",
      progress: managerDone ? 100 : 40,
    },
    {
      key: "plan",
      label: "Plan",
      state: planDone ? "done" : managerDone ? "running" : "pending",
      progress: planDone ? 100 : managerDone ? 50 : 0,
    },
    {
      key: "workers",
      label: "Workers",
      state: hasFailure ? "failed" : workerProgress >= 100 ? "done" : workerProgress > 0 ? "running" : "pending",
      progress: workerProgress,
    },
    {
      key: "final",
      label: "Final",
      state: finalDone ? "done" : hasFailure ? "failed" : "pending",
      progress: finalDone ? 100 : hasFailure ? 30 : 0,
    },
  ]
}
