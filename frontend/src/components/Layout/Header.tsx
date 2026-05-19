import { useTaskStore } from '../../store/taskStore'

const wsColors: Record<string, string> = {
  CONNECTED: 'bg-green-500',
  CONNECTING: 'bg-yellow-500',
  RECONNECTING: 'bg-yellow-500',
  DISCONNECTED: 'bg-red-400',
}

const wsLabels: Record<string, string> = {
  CONNECTED: 'WS 已連線',
  CONNECTING: 'WS 連線中',
  RECONNECTING: 'WS 重連中',
  DISCONNECTED: 'WS 中斷',
}

export function Header() {
  const tasks = useTaskStore((s) => s.tasks)
  const activeTask = tasks.find((t) => t.status === 'RUNNING')
  const wsStatus = useTaskStore((s) => s.wsStatus)
  const apiStatus = useTaskStore((s) => s.apiStatus)

  const apiDot =
    apiStatus === 'ok' ? 'bg-green-500' :
    apiStatus === 'error' ? 'bg-red-500' :
    'bg-gray-400 animate-pulse'

  const apiLabel =
    apiStatus === 'ok' ? '後端已連線' :
    apiStatus === 'error' ? '後端無法連線' :
    '連線中...'

  return (
    <header className="h-14 bg-white border-b flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-lg font-bold text-blue-900">QuantGene</span>
        <span className="text-xs text-gray-400">量化策略遺傳演算法</span>
      </div>
      <div className="flex items-center gap-4">
        {activeTask && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-500">執行中：</span>
            <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-600 rounded-full transition-all"
                style={{ width: `${activeTask.progress_pct}%` }}
              />
            </div>
            <span className="text-xs text-gray-400">
              {activeTask.current_generation}/{activeTask.total_generations}
            </span>
          </div>
        )}
        {wsStatus !== 'idle' && (
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${wsColors[wsStatus.toUpperCase()] || 'bg-gray-400'}`} />
            <span className="text-xs text-gray-400">{wsLabels[wsStatus.toUpperCase()] || wsStatus}</span>
          </div>
        )}
        <div className="flex items-center gap-1.5" title={apiLabel}>
          <span className={`w-2 h-2 rounded-full ${apiDot}`} />
          <span className={`text-xs ${apiStatus === 'error' ? 'text-red-500' : 'text-gray-400'}`}>
            {apiLabel}
          </span>
        </div>
      </div>
    </header>
  )
}
