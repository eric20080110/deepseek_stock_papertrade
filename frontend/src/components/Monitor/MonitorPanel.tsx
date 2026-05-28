import { useEffect, useRef, useState } from 'react'
import { useTaskStore } from '../../store/taskStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { StatCards } from './StatCards'
import { TrendChart } from './TrendChart'
import { LiveScatter } from './LiveScatter'
import { GenerationLog } from './GenerationLog'

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec} 秒`
  if (sec < 3600) return `${Math.round(sec / 60)} 分 ${sec % 60} 秒`
  const h = Math.floor(sec / 3600)
  const m = Math.round((sec % 3600) / 60)
  return `${h} 時 ${m} 分`
}

export function MonitorPanel() {
  const tasks = useTaskStore((s) => s.tasks)
  const activeTask = tasks.find((t) => t.status === 'RUNNING')
  const generationHistory = useTaskStore((s) => s.generationHistory)
  const clearGenerationHistory = useTaskStore((s) => s.clearGenerationHistory)
  const setActiveTaskId = useTaskStore((s) => s.setActiveTaskId)
  const latest = generationHistory.length > 0 ? generationHistory[generationHistory.length - 1] : null
  const individualProgress = useTaskStore((s) => s.individualProgress)
  const lastTaskIdRef = useRef<string | null>(null)
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000))
  useEffect(() => {
    if (!activeTask) return
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000)
    return () => clearInterval(id)
  }, [activeTask?.task_id])
  const elapsed = activeTask?.started_at ? now - activeTask.started_at : 0

  useEffect(() => {
    if (activeTask && activeTask.task_id !== lastTaskIdRef.current) {
      lastTaskIdRef.current = activeTask.task_id
      setActiveTaskId(activeTask.task_id)
      clearGenerationHistory()
    }
  }, [activeTask?.task_id])

  useWebSocket(activeTask?.task_id ?? null)

  if (!activeTask) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold mb-4">即時監控</h1>
        <div className="text-center py-16 text-gray-400">目前無執行中的任務</div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">即時監控</h1>
          <div className="text-sm text-gray-400 mt-1">
            {activeTask.config.symbols.join(', ')} ｜ {({'1d':'日 K','1h':'小時 K','30m':'30分 K','15m':'15分 K','5m':'5分 K','1m':'1分 K'})[activeTask.config.timeframe] || activeTask.config.timeframe}
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold">第 {activeTask.current_generation} / {activeTask.total_generations} 代</div>
          {individualProgress && individualProgress.generation === activeTask.current_generation && (
            <div className="text-xs text-gray-400 mt-0.5">
              個體 {individualProgress.current} / {individualProgress.total}
            </div>
          )}
          <div className="w-48 h-2 bg-gray-200 rounded-full mt-1 overflow-hidden">
            <div className="h-full bg-blue-600 rounded-full transition-all" style={{ width: `${activeTask.progress_pct}%` }} />
          </div>
          <div className="text-xs text-gray-400 mt-1">
            已運行 {formatDuration(elapsed)}
          </div>
        </div>
      </div>

      <StatCards latest={latest} />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
        <div className="border rounded-lg bg-white p-3">
          <div className="text-sm font-medium mb-2 text-gray-600">演化趨勢</div>
          <TrendChart history={generationHistory} />
        </div>
        <div className="border rounded-lg bg-white p-3">
          <div className="text-sm font-medium mb-2 text-gray-600">帕雷托散點</div>
          <LiveScatter latest={latest} />
        </div>
      </div>
      <GenerationLog history={generationHistory} />
    </div>
  )
}
