import { useEffect, useState, useCallback } from 'react'
import { toast } from '../../lib/toast'
import { Trash2, Play, Pause } from 'lucide-react'

interface Schedule {
  rule_id: string
  name: string
  strategy_config_id: string
  symbols: string
  timeframe: string
  cron_expr: string
  enabled: number
  last_run_at: number | null
  next_run_at: number | null
  population_size: number
  max_generations: number
}

export function SchedulePanel() {
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/schedules')
      .then((r) => r.json())
      .then(setSchedules)
      .catch(() => toast.error('載入排程失敗'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = async (id: string) => {
    await fetch(`/schedules/${id}/toggle`, { method: 'PUT' })
    load()
  }

  const remove = async (id: string) => {
    if (!confirm('確定刪除此排程？')) return
    await fetch(`/schedules/${id}`, { method: 'DELETE' })
    toast.success('排程已刪除')
    load()
  }

  const fmtTime = (ts: number | null) => {
    if (!ts) return '-'
    return new Date(ts * 1000).toLocaleString()
  }

  if (loading) return <div className="text-center py-8 text-gray-400">載入中...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">自動排程任務</h2>
        <a href="/#/new-task" className="text-sm text-blue-600 hover:underline">建立新排程（先建立策略任務）</a>
      </div>
      {schedules.length === 0 ? (
        <div className="text-center py-12 text-gray-400 border rounded-lg bg-white">尚無排程規則</div>
      ) : (
        <div className="space-y-2">
          {schedules.map((s) => (
            <div key={s.rule_id} className="flex items-center justify-between p-3 border rounded-lg bg-white">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{s.name || s.rule_id.slice(0, 12)}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${s.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                    {s.enabled ? '啟用' : '停用'}
                  </span>
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  Cron: {s.cron_expr} | {s.timeframe} | 上次: {fmtTime(s.last_run_at)} | 下次: {fmtTime(s.next_run_at)}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => toggle(s.rule_id)} className="p-1.5 hover:bg-gray-100 rounded cursor-pointer" title={s.enabled ? '暫停' : '啟用'}>
                  {s.enabled ? <Pause className="w-4 h-4 text-gray-500" /> : <Play className="w-4 h-4 text-green-500" />}
                </button>
                <button onClick={() => remove(s.rule_id)} className="p-1.5 hover:bg-red-50 rounded cursor-pointer" title="刪除">
                  <Trash2 className="w-4 h-4 text-red-400" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
