import { useEffect, useState } from 'react'

interface CompareItem {
  strategy_id: string
  cagr: number
  max_drawdown: number
  sharpe_ratio: number
  profit_factor: number
  win_rate: number
  oos_score: number
  trade_count: number
  generation: number
  final_equity: number
}

interface Props {
  taskId: string
}

export function ComparePanel({ taskId }: Props) {
  const [individuals, setIndividuals] = useState<{ strategy_id: string; cagr: number }[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [results, setResults] = useState<CompareItem[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch(`/tasks/${taskId}/individuals?pareto_rank=1`)
      .then((r) => r.json())
      .then((data) => {
        setIndividuals(data)
        setResults([])
        setSelected(new Set())
      })
  }, [taskId])

  const toggle = (sid: string) => {
    const next = new Set(selected)
    if (next.has(sid)) next.delete(sid)
    else next.add(sid)
    setSelected(next)
  }

  const compare = async () => {
    if (selected.size < 2) return
    setLoading(true)
    try {
      const res = await fetch(`/tasks/${taskId}/individuals/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sids: Array.from(selected), task_id: taskId }),
      })
      setResults(await res.json())
    } catch { /* ignore */ }
    setLoading(false)
  }

  const metrics: { key: keyof CompareItem; label: string; suffix: string }[] = [
    { key: 'cagr', label: 'CAGR', suffix: '%' },
    { key: 'sharpe_ratio', label: 'Sharpe', suffix: '' },
    { key: 'max_drawdown', label: '最大回撤', suffix: '%' },
    { key: 'win_rate', label: '勝率', suffix: '%' },
    { key: 'profit_factor', label: '獲利因子', suffix: '' },
    { key: 'oos_score', label: 'OOS 分數', suffix: '' },
    { key: 'trade_count', label: '交易次數', suffix: '' },
    { key: 'final_equity', label: '最終權益', suffix: '' },
  ]

  return (
    <div>
      <div className="mb-3">
        <div className="text-sm font-medium mb-1">選擇要比較的個體（至少 2 個）：</div>
        <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto">
          {individuals.map((ind) => (
            <label key={ind.strategy_id} className="flex items-center gap-1.5 text-xs px-2 py-1 border rounded cursor-pointer hover:bg-gray-50">
              <input type="checkbox" checked={selected.has(ind.strategy_id)} onChange={() => toggle(ind.strategy_id)} />
              {ind.strategy_id.slice(0, 10)} ({ind.cagr ? (ind.cagr * 100).toFixed(1) : '?'}%)
            </label>
          ))}
        </div>
        <button
          onClick={compare}
          disabled={selected.size < 2 || loading}
          className="mt-2 px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
        >
          {loading ? '比較中...' : `比較 ${selected.size} 個個體`}
        </button>
      </div>

      {results.length > 0 && (
        <div className="border rounded-lg bg-white overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50">
                <th className="text-left p-2 text-xs text-gray-500">指標</th>
                {results.map((r) => (
                  <th key={r.strategy_id} className="p-2 text-xs text-gray-500 text-right">{r.strategy_id.slice(0, 8)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => {
                const vals = results.map((r) => r[m.key] as number)
                const best = m.key === 'max_drawdown' ? Math.min(...vals) : Math.max(...vals)
                return (
                  <tr key={m.key} className="border-t">
                    <td className="p-2 text-xs text-gray-600">{m.label}</td>
                    {results.map((r) => {
                      const v = r[m.key] as number
                      const isBest = v === best
                      return (
                        <td key={r.strategy_id} className={`p-2 text-xs text-right ${isBest ? 'text-green-600 font-bold' : ''}`}>
                          {typeof v === 'number' ? v.toFixed(2) : v}{m.suffix}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
