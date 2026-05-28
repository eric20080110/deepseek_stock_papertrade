const statusColors: Record<string, string> = {
  INITIALIZING: 'bg-yellow-500',
  RUNNING: 'bg-rose-500',
  PAUSED: 'bg-yellow-400',
  STOPPED: 'bg-gray-400',
  FAILED: 'bg-red-500',
}

interface Props {
  instance: any
  onView: (id: string) => void
}

export function AccountCard({ instance, onView }: Props) {
  const handleStop = async () => {
    if (!confirm('確定停止此實盤實例？將強制平倉所有持倉。')) return
    await fetch(`/live-trading/${instance.instance_id}`, { method: 'DELETE' })
    window.location.reload()
  }

  const handleDelete = async () => {
    if (!confirm('確定永久刪除此實例？（所有紀錄將遺失）')) return
    await fetch(`/live-trading/${instance.instance_id}?purge=true`, { method: 'DELETE' })
    window.location.reload()
  }

  const handlePauseResume = async (action: 'pause' | 'resume') => {
    await fetch(`/live-trading/${instance.instance_id}/${action}`, { method: 'PUT' })
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

  return (
    <div className="border rounded-xl p-5 bg-white hover:shadow-md transition-shadow border-l-4 border-l-rose-400">
      <div className="flex items-center gap-2 mb-3">
        <span className={`w-2.5 h-2.5 rounded-full ${cfg.color}`} />
        <span className="text-xs text-gray-500">{cfg.label}</span>
      </div>

      <h3 className="font-semibold">{instance.name}</h3>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {(symbols as string[]).map((sym: string) => (
          <span key={sym} className="text-xs bg-gray-100 px-2 py-0.5 rounded">{sym}</span>
        ))}
      </div>

      <div className="grid grid-cols-4 gap-2 mt-4">
        <div>
          <div className="text-xs text-gray-400">資金上限</div>
          <div className="text-base font-bold">${instance.initial_capital?.toLocaleString()}</div>
        </div>
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
          <div className="text-xs text-gray-400">精度</div>
          <div className="text-base font-bold">{instance.timeframe || '-'}</div>
        </div>
      </div>

      <div className="text-xs text-gray-400 mt-1">排程：每日 {instance.schedule_time || '16:30'}</div>

      <div className="flex items-center gap-2 mt-4 pt-3 border-t flex-wrap">
        <button onClick={() => onView(instance.instance_id)}
          className="flex-1 px-3 py-1.5 text-sm bg-rose-600 text-white rounded-lg hover:bg-rose-700 cursor-pointer">
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
        <button onClick={instance.status === 'STOPPED' ? handleDelete : handleStop}
          className="px-3 py-1.5 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50 cursor-pointer">
          {instance.status === 'STOPPED' ? '刪除' : '停止'}
        </button>
      </div>
    </div>
  )
}
