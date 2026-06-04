import { useState, useEffect } from 'react'
import { toast } from '../../lib/toast'

interface DashboardStats {
  tasks: { total: number; running: number; completed: number; failed: number }
  paper: { instances: number; running: number; total_equity: number; total_return_pct: number }
  live: { instances: number; running: number; total_equity: number }
  best_champion: { strategy_id: string; cagr: number; sharpe: number; max_drawdown: number } | null
  recent_tasks: {
    task_id: string
    status: string
    created_at: number
    progress: string
    progress_pct: number
    symbols: string[]
    timeframe: string
  }[]
}

const statusColors: Record<string, string> = {
  QUEUED: 'text-gray-500 bg-gray-100',
  RUNNING: 'text-blue-600 bg-blue-50',
  COMPLETED: 'text-emerald-600 bg-emerald-50',
  FAILED: 'text-red-600 bg-red-50',
  CANCELLED: 'text-gray-500 bg-gray-100',
}

function StatCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border rounded-lg bg-white p-5">
      <div className="text-xs text-gray-500 mb-2">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

export function DashboardPanel() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchStats = () => {
      fetch('/dashboard/stats')
        .then((r) => {
          if (!r.ok) throw new Error('Failed to fetch dashboard stats')
          return r.json()
        })
        .then((data) => {
          setStats(data)
          setLoading(false)
        })
        .catch((err) => {
          toast.error(err.message)
          setLoading(false)
        })
    }
    fetchStats()
    const id = setInterval(fetchStats, 15000)
    return () => clearInterval(id)
  }, [])

  if (loading) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <h1 className="text-2xl font-bold mb-6">儀表板</h1>
        <div className="text-sm text-gray-400">載入中...</div>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <h1 className="text-2xl font-bold mb-6">儀表板</h1>
        <div className="text-sm text-red-500">無法載入儀表板數據</div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">儀表板</h1>

      <div className="grid grid-cols-4 gap-4 mb-4">
        <StatCard title="演化任務">
          <div className="text-2xl font-bold">{stats.tasks.total}</div>
          <div className="flex gap-3 text-xs mt-1">
            <span className="text-blue-600">執行中 {stats.tasks.running}</span>
            <span className="text-emerald-600">完成 {stats.tasks.completed}</span>
            <span className="text-red-500">失敗 {stats.tasks.failed}</span>
          </div>
        </StatCard>
        <StatCard title="模擬交易">
          <div className="text-2xl font-bold">{stats.paper.instances}</div>
          <div className="flex gap-3 text-xs mt-1">
            <span className="text-blue-600">運行中 {stats.paper.running}</span>
          </div>
        </StatCard>
        <StatCard title="實盤交易">
          <div className="text-2xl font-bold">{stats.live.instances}</div>
          <div className="flex gap-3 text-xs mt-1">
            <span className="text-blue-600">運行中 {stats.live.running}</span>
          </div>
        </StatCard>
        <StatCard title="最佳 Champion">
          {stats.best_champion ? (
            <>
              <div className="text-lg font-bold text-blue-700">{stats.best_champion.cagr}%</div>
              <div className="flex gap-3 text-xs mt-1">
                <span>Sharpe {stats.best_champion.sharpe}</span>
                <span className="text-red-500">DD {stats.best_champion.max_drawdown}%</span>
              </div>
            </>
          ) : (
            <div className="text-sm text-gray-400">暫無數據</div>
          )}
        </StatCard>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="border rounded-lg bg-white p-5">
          <div className="text-xs text-gray-500 mb-2">模擬總權益</div>
          <div className="text-2xl font-bold">${(stats.paper.total_equity ?? 0).toLocaleString()}</div>
          <div className={`text-sm mt-1 ${stats.paper.total_return_pct >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
            {stats.paper.total_return_pct >= 0 ? '+' : ''}{stats.paper.total_return_pct}% 總報酬率
          </div>
        </div>
        <div className="border rounded-lg bg-white p-5">
          <div className="text-xs text-gray-500 mb-2">實盤總權益</div>
          <div className="text-2xl font-bold">${(stats.live.total_equity ?? 0).toLocaleString()}</div>
        </div>
      </div>

      <div className="border rounded-lg bg-white">
        <div className="px-5 py-3 border-b">
          <h2 className="text-sm font-semibold">近期任務</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs text-gray-500">
                <th className="text-left px-5 py-3 font-medium">任務 ID</th>
                <th className="text-left px-5 py-3 font-medium">狀態</th>
                <th className="text-left px-5 py-3 font-medium">標的</th>
                <th className="text-left px-5 py-3 font-medium">框架</th>
                <th className="text-left px-5 py-3 font-medium">進度</th>
                <th className="text-left px-5 py-3 font-medium">建立時間</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_tasks.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-gray-400">暫無任務</td>
                </tr>
              ) : (
                stats.recent_tasks.map((t) => (
                  <tr key={t.task_id} className="border-b last:border-b-0 hover:bg-gray-50">
                    <td className="px-5 py-3 font-mono text-xs">{t.task_id.slice(0, 12)}...</td>
                    <td className="px-5 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${statusColors[t.status] || 'text-gray-500 bg-gray-100'}`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="px-5 py-3">{t.symbols?.join(', ') || '-'}</td>
                    <td className="px-5 py-3">{t.timeframe || '-'}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-blue-600 rounded-full"
                            style={{ width: `${t.progress_pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">{t.progress}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-xs text-gray-500">
                      {new Date(t.created_at * 1000).toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
