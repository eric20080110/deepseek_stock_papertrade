import type { EvolutionTask } from '../../types/evolution'
import { useTaskStore } from '../../store/taskStore'
import { useState, useEffect } from 'react'
import { Trash2, Pencil, Check, X, Clock } from 'lucide-react'
import { toast } from '../../lib/toast'
import { ConfirmModal } from '../ConfirmModal'

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec} 秒`
  if (sec < 3600) return `${Math.round(sec / 60)} 分 ${sec % 60} 秒`
  const h = Math.floor(sec / 3600)
  const m = Math.round((sec % 3600) / 60)
  return `${h} 時 ${m} 分`
}

function useElapsed(task: EvolutionTask): number {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000))
  useEffect(() => {
    if (task.status !== 'RUNNING') return
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000)
    return () => clearInterval(id)
  }, [task.status, task.task_id])
  if (task.status === 'RUNNING' && task.started_at) return now - task.started_at
  if (task.status === 'COMPLETED' && task.started_at && task.completed_at) return task.completed_at - task.started_at
  if ((task.status === 'FAILED' || task.status === 'CANCELLED') && task.started_at && task.completed_at) return task.completed_at - task.started_at
  return 0
}

const statusConfig: Record<string, { color: string; label: string }> = {
  QUEUED: { color: 'bg-gray-400', label: '排隊中' },
  RUNNING: { color: 'bg-blue-500', label: '執行中' },
  COMPLETED: { color: 'bg-green-500', label: '已完成' },
  FAILED: { color: 'bg-red-500', label: '失敗' },
  CANCELLED: { color: 'bg-gray-300', label: '已取消' },
}

interface Props {
  task: EvolutionTask
  onRefresh: () => void
}

export function TaskCard({ task, onRefresh }: Props) {
  const cfg = statusConfig[task.status]
  const elapsed = useElapsed(task)
  const setCurrentView = useTaskStore((s) => s.setCurrentView)
  const setSelectedAnalysisTaskId = useTaskStore((s) => s.setSelectedAnalysisTaskId)
  const triggerDbStatusRefresh = useTaskStore((s) => s.triggerDbStatusRefresh)
  const setRetryConfig = useTaskStore((s) => s.setRetryConfig)
  const [deleting, setDeleting] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [draftName, setDraftName] = useState(task.name || '')

  const confirmRename = async () => {
    const name = draftName.trim()
    if (name) {
      await fetch(`/gene-pool/tasks/${task.task_id}/rename`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      useTaskStore.getState().updateTask(task.task_id, { name })
    }
    setEditingName(false)
  }

  const handleCancel = async () => {
    await fetch(`/tasks/${task.task_id}`, { method: 'DELETE' })
    useTaskStore.getState().updateTask(task.task_id, { status: 'CANCELLED' })
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      const res = await fetch(`/tasks/${task.task_id}?purge=true`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`${res.status}`)
      toast.success('任務已刪除')
      onRefresh()
      triggerDbStatusRefresh()
    } catch (e) {
      toast.error('刪除失敗，請重試')
      setDeleting(false)
    }
  }

  const handleViewResults = () => {
    setSelectedAnalysisTaskId(task.task_id)
    setCurrentView('analysis')
  }

  const handleRetry = () => {
    setRetryConfig(task.config)
    setCurrentView('new-task')
  }

  return (
    <>
    <div className="flex items-center gap-4 p-4 border rounded-lg bg-white hover:shadow-sm transition-shadow">
      <span className={`w-3 h-3 rounded-full shrink-0 ${cfg.color}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          {editingName ? (
            <div className="flex items-center gap-1 flex-1 min-w-0">
              <input type="text" value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && confirmRename()}
                className="flex-1 min-w-0 px-1 py-0.5 text-sm border rounded" />
              <button onClick={confirmRename} className="cursor-pointer shrink-0"><Check className="w-3.5 h-3.5 text-green-600" /></button>
              <button onClick={() => setEditingName(false)} className="cursor-pointer shrink-0"><X className="w-3.5 h-3.5 text-red-500" /></button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 flex-1 min-w-0">
              <span className="font-medium text-sm truncate">{task.name || task.task_id.slice(0, 12)}</span>
              <button onClick={() => { setEditingName(true); setDraftName(task.name || '') }} className="cursor-pointer shrink-0">
                <Pencil className="w-3 h-3 text-gray-400 hover:text-gray-600" />
              </button>
            </div>
          )}
          <span className="text-xs text-gray-400 shrink-0">
            {new Date(task.created_at * 1000).toLocaleString()}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-400 mt-0.5">
          <span>{task.config.timeframe}</span>
          <span>{task.config.symbols.length} 標的</span>
          <span>{task.config.population_size || '?'}×{task.config.max_generations || '?'}</span>
          {elapsed > 0 && (
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDuration(elapsed)}
            </span>
          )}
        </div>
        {task.status === 'FAILED' && task.error_message && (
          <div className="text-xs text-red-500 mt-1 truncate">{task.error_message}</div>
        )}
      </div>
      <div className="w-24 text-center">
        {task.status === 'RUNNING' && (
          <div>
            <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full bg-blue-600 rounded-full transition-all" style={{ width: `${task.progress_pct}%` }} />
            </div>
            <span className="text-xs text-gray-400 mt-0.5 block">{task.current_generation}/{task.total_generations}</span>
          </div>
        )}
        {task.status === 'QUEUED' && <span className="text-xs text-gray-400">第 N 位</span>}
      </div>
      <div className="flex gap-1">
        {task.status === 'RUNNING' && (
          <button onClick={handleCancel} className="px-2 py-1 text-xs border border-red-200 text-red-600 rounded hover:bg-red-50 cursor-pointer">取消</button>
        )}
        {task.status === 'QUEUED' && (
          <button onClick={handleCancel} className="px-2 py-1 text-xs border rounded hover:bg-gray-50 cursor-pointer">取消</button>
        )}
        {task.status === 'COMPLETED' && (
          <button onClick={handleViewResults} className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 cursor-pointer">查看</button>
        )}
        {task.status === 'FAILED' && (
          <span className="text-xs text-red-500" title={task.error_message || ''}>查看錯誤</span>
        )}
        {(task.status === 'FAILED' || task.status === 'CANCELLED') && (
          <button onClick={handleRetry}
            className="px-2 py-1 text-xs border border-blue-200 text-blue-600 rounded hover:bg-blue-50 cursor-pointer">
            重跑
          </button>
        )}
        {(task.status === 'COMPLETED' || task.status === 'FAILED' || task.status === 'CANCELLED') && (
          <button onClick={() => setShowDeleteModal(true)} disabled={deleting}
            className="px-2 py-1 text-xs border border-red-200 text-red-500 rounded hover:bg-red-50 cursor-pointer flex items-center gap-1">
            <Trash2 className="w-3 h-3" /> {deleting ? '...' : '刪除'}
          </button>
        )}
      </div>
    </div>
    {showDeleteModal && (
      <ConfirmModal
        title="永久刪除此任務？"
        description="將刪除所有相關個體與演化紀錄，此操作無法復原。"
        confirmLabel="刪除"
        danger
        onConfirm={() => { setShowDeleteModal(false); handleDelete() }}
        onCancel={() => setShowDeleteModal(false)}
      />
    )}
    </>
  )
}
