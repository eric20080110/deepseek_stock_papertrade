import { useState, useEffect } from 'react'
import { InstanceList } from './InstanceList'
import { CreateInstanceForm } from './CreateInstanceForm'
import { InstanceDetail } from './InstanceDetail'

interface RenderStatus {
  connected: boolean
  url?: string
  instances?: number
  reason?: string
}

function RenderStatusBadge() {
  const [status, setStatus] = useState<RenderStatus | null>(null)

  useEffect(() => {
    const check = () =>
      fetch('/paper-trading/render-status')
        .then((r) => r.json())
        .then(setStatus)
        .catch(() => setStatus({ connected: false, reason: 'fetch_error' }))
    check()
    const t = setInterval(check, 30000)
    return () => clearInterval(t)
  }, [])

  if (!status) return <span className="text-xs text-gray-400">檢查 Render...</span>

  if (status.reason === 'not_configured') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-gray-400">
        <span className="w-2 h-2 rounded-full bg-gray-300" />
        Render 未設定
      </span>
    )
  }

  if (status.connected) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-emerald-600">
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
        Render 運行中（{status.instances} 個實例）
      </span>
    )
  }

  if (status.reason === 'not_deployed') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-amber-500">
        <span className="w-2 h-2 rounded-full bg-amber-400" />
        Render 尚未部署
      </span>
    )
  }

  return (
    <span className="flex items-center gap-1.5 text-xs text-red-500">
      <span className="w-2 h-2 rounded-full bg-red-400" />
      Render 未連線
    </span>
  )
}

export function PaperTradingPanel() {
  const [view, setView] = useState<'list' | 'create' | 'detail'>('list')
  const [detailId, setDetailId] = useState<string | null>(null)

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {view === 'list' && (
        <>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold">模擬跑盤</h1>
              <div className="mt-1">
                <RenderStatusBadge />
              </div>
            </div>
            <button onClick={() => setView('create')}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer">
              + 新增模擬實例
            </button>
          </div>
          <InstanceList onViewDetail={(id) => { setDetailId(id); setView('detail') }} />
        </>
      )}
      {view === 'create' && (
        <div>
          <button onClick={() => setView('list')}
            className="mb-4 text-sm text-blue-600 hover:text-blue-800 cursor-pointer">← 返回列表</button>
          <CreateInstanceForm />
        </div>
      )}
      {view === 'detail' && detailId && (
        <div>
          <button onClick={() => setView('list')}
            className="mb-4 text-sm text-blue-600 hover:text-blue-800 cursor-pointer">← 返回列表</button>
          <InstanceDetail instanceId={detailId} />
        </div>
      )}
    </div>
  )
}
