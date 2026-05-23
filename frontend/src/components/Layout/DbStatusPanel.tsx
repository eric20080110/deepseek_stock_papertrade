import { useState, useEffect } from 'react'
import { Database, ChevronDown, ChevronUp, Trash2 } from 'lucide-react'
import { toast } from '../../lib/toast'
import { useTaskStore } from '../../store/taskStore'

interface DbStatus {
  local: {
    connected: boolean
    size: string
    rows: Record<string, number>
  }
  turso: {
    configured: boolean
    connected: boolean
    latency_ms: number | null
    rows: Record<string, number>
  }
}

const ROW_LABELS: Record<string, string> = {
  evolution_tasks: '演化任務',
  individuals: '個體',
  strategy_configs: '策略',
  paper_instances: '跑盤實例',
  virtual_trades: '模擬交易',
  paper_equity_history: '權益歷程',
  ohlcv_data: 'K線快取',
}

export function DbStatusPanel() {
  const [status, setStatus] = useState<DbStatus | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [vacuuming, setVacuuming] = useState(false)

  const handleVacuum = async () => {
    setVacuuming(true)
    try {
      const res = await fetch('/system/vacuum', { method: 'POST' })
      if (!res.ok) {
        const d = await res.json()
        toast.error(d.detail || 'VACUUM 失敗，請先關閉 DBeaver')
      } else {
        toast.success('VACUUM 完成，空間已回收')
        fetch('/system/db-status').then((r) => r.json()).then(setStatus).catch(() => {})
      }
    } catch {
      toast.error('VACUUM 請求失敗')
    }
    setVacuuming(false)
  }
  const dbStatusVersion = useTaskStore((s) => s.dbStatusVersion)

  useEffect(() => {
    const fetch_ = () =>
      fetch('/system/db-status')
        .then((r) => r.json())
        .then(setStatus)
        .catch(() => {})
    fetch_()
    const t = setInterval(fetch_, 30000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (dbStatusVersion === 0) return
    fetch('/system/db-status')
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {})
  }, [dbStatusVersion])

  if (!status) return null

  const localDot = status.local.connected
    ? 'bg-emerald-500'
    : 'bg-red-500'

  const tursoDot = !status.turso.configured
    ? 'bg-gray-400'
    : status.turso.connected
    ? 'bg-emerald-500'
    : 'bg-red-500'

  const tursoLabel = !status.turso.configured
    ? '未設定'
    : status.turso.connected
    ? `${status.turso.latency_ms}ms`
    : '未連線'

  return (
    <div className="border-t px-3 py-2 text-xs text-gray-500">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between hover:text-gray-700 cursor-pointer"
      >
        <span className="flex items-center gap-1.5">
          <Database className="w-3 h-3" />
          資料庫
        </span>
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      <div className="mt-1.5 space-y-1">
        {/* Always-visible summary */}
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${localDot}`} />
            本地
          </span>
          <span className="text-gray-400">{status.local.size}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${tursoDot}`} />
            Turso
          </span>
          <span className="text-gray-400">{tursoLabel}</span>
        </div>
      </div>

      {/* VACUUM button */}
      {expanded && (
        <button onClick={handleVacuum} disabled={vacuuming}
          className="mt-2 w-full flex items-center justify-center gap-1.5 px-2 py-1 text-xs border border-gray-200 rounded hover:bg-gray-50 disabled:opacity-50 cursor-pointer text-gray-500">
          <Trash2 className="w-3 h-3" />
          {vacuuming ? '回收中...' : '回收空間 (VACUUM)'}
        </button>
      )}

      {/* Expanded detail */}
      {expanded && (
        <div className="mt-2 space-y-2">
          <div>
            <div className="text-gray-400 mb-1 font-medium">本地 SQLite</div>
            {Object.entries(status.local.rows).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-gray-400">{ROW_LABELS[k] ?? k}</span>
                <span className="tabular-nums">{v.toLocaleString()}</span>
              </div>
            ))}
          </div>
          {status.turso.configured && status.turso.connected && (
            <div>
              <div className="text-gray-400 mb-1 font-medium">Turso 雲端</div>
              {Object.entries(status.turso.rows).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-gray-400">{ROW_LABELS[k] ?? k}</span>
                  <span className="tabular-nums">{v.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
