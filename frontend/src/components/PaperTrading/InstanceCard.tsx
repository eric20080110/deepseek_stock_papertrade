const statusColors: Record<string, string> = {
  INITIALIZING: 'bg-yellow-500',
  RUNNING: 'bg-green-500',
  PAUSED: 'bg-yellow-400',
  STOPPED: 'bg-gray-400',
  FAILED: 'bg-red-500',
}

export interface PaperInstance {
  instance_id: string
  name: string
  status: string
  source?: string
  symbols: string | string[]
  total_return: number
  trade_count: number
  timeframe: string
  started_at?: number
  stopped_at?: number
  params_json?: string
}

interface Props {
  instance: PaperInstance
  onView: (id: string) => void
}

export function InstanceCard({ instance, onView }: Props) {
  const handleStop = async () => {
    if (!confirm('確定停止此實例？將強制平倉所有持倉。')) return
    await fetch(`/paper-trading/${instance.instance_id}`, { method: 'DELETE' })
    window.location.reload()
  }

  const handleDelete = async () => {
    if (!confirm('確定永久刪除此實例？（所有紀錄將遺失）')) return
    await fetch(`/paper-trading/${instance.instance_id}?purge=true`, { method: 'DELETE' })
    window.location.reload()
  }

  const handleContinue = async () => {
    if (!confirm('重新開始此實例？（將刪除舊紀錄並建立新實例）')) return
    await fetch(`/paper-trading/${instance.instance_id}/continue`, { method: 'PUT' })
    window.location.reload()
  }

  const handlePauseResume = async (action: 'pause' | 'resume') => {
    await fetch(`/paper-trading/${instance.instance_id}/${action}`, { method: 'PUT' })
    window.location.reload()
  }

  const cfg = {
    color: statusColors[instance.status] || 'bg-gray-400',
    label: instance.status === 'INITIALIZING' ? '初始化中' :
           instance.status === 'RUNNING' ? '運行中' :
           instance.status === 'PAUSED' ? '已暫停' :
           instance.status === 'STOPPED' ? '已停止' : '失敗',
  }

  const symbols = typeof instance.symbols === 'string' ? JSON.parse(instance.symbols) : instance.symbols

  function formatUptime(started?: number, stopped?: number): string {
    if (!started) return '-'
    const end = stopped ?? Date.now() / 1000
    const sec = Math.max(0, Math.floor(end - started))
    if (sec < 60) return `${sec}s`
    const min = Math.floor(sec / 60)
    if (min < 60) return `${min}m`
    const hr = Math.floor(min / 60)
    const remMin = min % 60
    if (hr < 24) return `${hr}h ${remMin}m`
    const day = Math.floor(hr / 24)
    const remHr = hr % 24
    return `${day}d ${remHr}h`
  }

  return (
    <div className="border rounded-xl p-5 bg-white hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2 mb-3">
        <span className={`w-2.5 h-2.5 rounded-full ${cfg.color}`} />
        <span className="text-xs text-gray-500">{cfg.label}</span>
        {instance.source === 'evolution' && (
          <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">來自演化</span>
        )}
      </div>

      <h3 className="font-semibold">{instance.name}</h3>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {(symbols as string[]).map((sym: string) => (
          <span key={sym} className="text-xs bg-gray-100 px-2 py-0.5 rounded">{sym}</span>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2 mt-4">
        <div>
          <div className="text-xs text-gray-400">總報酬率</div>
          <div className={`text-base font-bold ${instance.total_return >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {instance.total_return >= 0 ? '+' : ''}{instance.total_return?.toFixed(2)}%
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-400">交易次數</div>
          <div className="text-base font-bold">{instance.trade_count}</div>
        </div>
        <div>
          <div className="text-xs text-gray-400">運行時間</div>
          <div className="text-base font-bold">{formatUptime(instance.started_at, instance.status === 'STOPPED' ? instance.stopped_at : undefined)}</div>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-4 pt-3 border-t flex-wrap">
        <button onClick={() => onView(instance.instance_id)}
          className="flex-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer">
          查看詳情
        </button>
        {instance.status === 'RUNNING' && (
          <button onClick={() => handlePauseResume('pause')}
            className="px-3 py-1.5 text-sm border rounded-lg hover:bg-gray-50 cursor-pointer">暫停</button>
        )}
        {instance.status === 'PAUSED' && (
          <button onClick={() => handlePauseResume('resume')}
            className="px-3 py-1.5 text-sm border rounded-lg hover:bg-gray-50 cursor-pointer">恢復</button>
        )}
        {instance.status === 'STOPPED' && (
          <button onClick={handleContinue}
            className="px-3 py-1.5 text-sm border border-green-200 text-green-600 rounded-lg hover:bg-green-50 cursor-pointer">繼續</button>
        )}
        <button onClick={instance.status === 'STOPPED' ? handleDelete : handleStop}
          className="px-3 py-1.5 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50 cursor-pointer">
          {instance.status === 'STOPPED' ? '刪除' : '停止'}
        </button>
      </div>
      <div className="mt-2 pt-2 border-t">
        <button onClick={async () => {
          if (!confirm(`將 "${instance.name}" 複製到實盤跑盤？`)) return
          try {
            const r = await fetch('/live-trading/from-paper/' + instance.instance_id, { method: 'POST' })
            if (!r.ok) { const e = await r.json(); alert('轉入失敗：' + (e.detail || r.statusText)); return }
            window.location.reload()
          } catch (e: unknown) { alert('轉入失敗：' + (e instanceof Error ? e.message : String(e))) }
        }}
          className="w-full px-3 py-1.5 text-xs border border-rose-200 text-rose-600 rounded-lg hover:bg-rose-50 cursor-pointer">
          + 轉入實盤
        </button>
      </div>
    </div>
  )
}
