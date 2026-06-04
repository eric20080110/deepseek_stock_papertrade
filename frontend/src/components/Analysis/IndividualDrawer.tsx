import { useEffect, useState } from 'react'
import { X, GitFork } from 'lucide-react'
import { useTaskStore } from '../../store/taskStore'

export function IndividualDrawer() {
  const selectedId = useTaskStore((s) => s.selectedIndividualId)
  const setSelectedId = useTaskStore((s) => s.setSelectedIndividualId)
  const taskId = useTaskStore((s) => s.selectedAnalysisTaskId)
  const setSeedParams = useTaskStore((s) => s.setSeedParams)
  const setCurrentView = useTaskStore((s) => s.setCurrentView)
  interface IndividualDetail {
    cagr: number
    max_drawdown?: number
    sharpe_ratio?: number
    win_rate?: number
    profit_factor?: number
    r2?: number
    trade_count?: number
    oos_consistency_score?: number
    pareto_rank?: number
    params_json?: string
  }

  const [data, setData] = useState<IndividualDetail | null>(null)

  useEffect(() => {
    if (!selectedId || !taskId) return
    fetch(`/tasks/${taskId}/individuals/${selectedId}`)
      .then((r) => r.json())
      .then(setData)
  }, [selectedId, taskId])

  if (!selectedId || !data) return null

  const params = data.params_json ? JSON.parse(data.params_json) : {}

  const handleContinueEvolution = () => {
    setSeedParams(params)
    setSelectedId(null)
    setCurrentView('new-task')
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={() => setSelectedId(null)} />
      <div className="relative w-96 bg-white shadow-xl h-full overflow-y-auto">
        <div className="sticky top-0 bg-white border-b p-4 flex items-center justify-between">
          <h3 className="font-semibold">個體詳情</h3>
          <button onClick={() => setSelectedId(null)} className="cursor-pointer"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 bg-blue-50 rounded-lg text-center">
              <div className="text-xs text-gray-500">CAGR</div>
              <div className="text-lg font-bold text-blue-700">{(data.cagr * 100).toFixed(2)}%</div>
            </div>
            <div className="p-3 bg-red-50 rounded-lg text-center">
              <div className="text-xs text-gray-500">回撤</div>
              <div className="text-lg font-bold text-red-700">{data.max_drawdown?.toFixed(2)}%</div>
            </div>
            <div className="p-3 bg-green-50 rounded-lg text-center">
              <div className="text-xs text-gray-500">Sharpe</div>
              <div className="text-lg font-bold text-green-700">{data.sharpe_ratio?.toFixed(2)}</div>
            </div>
          </div>

          <div>
            <h4 className="text-sm font-medium mb-1">績效指標</h4>
            <table className="w-full text-xs">
              <tbody>
                {[
                  ['勝率', `${data.win_rate?.toFixed(1)}%`],
                  ['盈虧比', data.profit_factor?.toFixed(2)],
                  ['R²', data.r2?.toFixed(3)],
                  ['交易次數', data.trade_count],
                  ['OOS 一致性', data.oos_consistency_score?.toFixed(3)],
                  ['帕雷托排名', data.pareto_rank],
                ].map(([k, v]) => (
                  <tr key={k} className="border-b">
                    <td className="py-1 text-gray-500">{k}</td>
                    <td className="py-1 font-medium text-right">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h4 className="text-sm font-medium mb-1">參數字典</h4>
            <table className="w-full text-xs">
              <tbody>
                {Object.entries(params).map(([k, v]) => (
                  <tr key={k} className="border-b">
                    <td className="py-1 text-gray-500 font-mono">{k}</td>
                    <td className="py-1 font-medium text-right">{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex gap-2">
            <button onClick={handleContinueEvolution}
              className="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 cursor-pointer">
              <GitFork className="w-4 h-4" /> 繼續演化
            </button>
            <a href={`/tasks/${taskId}/export/python?sid=${selectedId}`}
              className="flex-1 px-3 py-2 text-sm text-center bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              匯出 Python
            </a>
            <a href={`/tasks/${taskId}/export?format=csv`}
              className="flex-1 px-3 py-2 text-sm text-center border rounded-lg hover:bg-gray-50">
              匯出 CSV
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
