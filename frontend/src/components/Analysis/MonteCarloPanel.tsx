import { useEffect, useState } from 'react'

interface MonteCarloResult {
  n_simulations: number
  confidence: number
  median_final_equity: number
  median_return_pct: number
  mean_return_pct: number
  std_return_pct: number
  ci_lower_return: number
  ci_upper_return: number
  prob_positive: number
  prob_double: number
  prob_half_loss: number
  error?: string
}

interface Props {
  taskId: string
  sid: string
}

export function MonteCarloPanel({ taskId, sid }: Props) {
  const [result, setResult] = useState<MonteCarloResult | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetch(`/tasks/${taskId}/individuals/${sid}/monte-carlo?n_simulations=1000`)
      .then((r) => r.json())
      .then((d) => setResult(d))
      .catch(() => setResult(null))
      .finally(() => setLoading(false))
  }, [taskId, sid])

  if (loading) return <div className="text-sm text-gray-400 py-2">計算蒙地卡羅中...</div>
  if (!result) return null
  if (result.error) return <div className="text-sm text-red-500 py-2">{result.error}</div>

  return (
    <div className="border rounded-lg bg-white p-3 mt-2">
      <h4 className="text-sm font-semibold mb-2">蒙地卡羅模擬 ({result.n_simulations} 次)</h4>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-gray-400">中位數報酬</div>
          <div className="font-bold">{result.median_return_pct >= 0 ? '+' : ''}{result.median_return_pct}%</div>
        </div>
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-gray-400">平均報酬</div>
          <div className="font-bold">{result.mean_return_pct >= 0 ? '+' : ''}{result.mean_return_pct}%</div>
        </div>
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-gray-400">標準差</div>
          <div className="font-bold">±{result.std_return_pct}%</div>
        </div>
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-gray-400">95% CI</div>
          <div className="font-bold">{result.ci_lower_return}% ~ {result.ci_upper_return}%</div>
        </div>
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-gray-400">正報酬機率</div>
          <div className="font-bold text-green-600">{result.prob_positive}%</div>
        </div>
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-gray-400">翻倍機率</div>
          <div className="font-bold text-blue-600">{result.prob_double}%</div>
        </div>
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-gray-400">腰斬機率</div>
          <div className="font-bold text-red-600">{result.prob_half_loss}%</div>
        </div>
        <div className="p-2 bg-gray-50 rounded">
          <div className="text-gray-400">中位數最終權益</div>
          <div className="font-bold">${result.median_final_equity.toLocaleString()}</div>
        </div>
      </div>
    </div>
  )
}
