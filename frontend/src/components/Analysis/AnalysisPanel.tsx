import { useEffect, useState } from 'react'
import { toast } from '../../lib/toast'
import { useTaskStore } from '../../store/taskStore'
import type { EvolutionTask } from '../../types/evolution'
import { ParetoScatter3D } from './ParetoScatter3D'
import { EvolutionTrend } from './EvolutionTrend'
import { EquityCurve } from './EquityCurve'
import { ParamHeatmap } from './ParamHeatmap'
import { ComparePanel } from './ComparePanel'
import { EnsemblePanel } from './EnsemblePanel'
import { IndividualDrawer } from './IndividualDrawer'

type Tab = 'scatter' | 'trend' | 'equity' | 'heatmap' | 'compare' | 'ensemble'

interface IndividualSummary {
  cagr: number
  params_json: string
  strategy_id: string
}

export function AnalysisPanel() {
  const taskId = useTaskStore((s) => s.selectedAnalysisTaskId)
  const setTaskId = useTaskStore((s) => s.setSelectedAnalysisTaskId)
  const addTask = useTaskStore((s) => s.addTask)
  const setCurrentView = useTaskStore((s) => s.setCurrentView)
  const [tasks, setTasks] = useState<EvolutionTask[]>([])
  const [tab, setTab] = useState<Tab>('scatter')
  const [evolving, setEvolving] = useState(false)

  const storeTasks = useTaskStore((s) => s.tasks)
  useEffect(() => {
    const completed = storeTasks.filter((t) => t.status === 'COMPLETED')
    setTasks(completed)
    if (!taskId && completed.length > 0) setTaskId(completed[0].task_id)
  }, [storeTasks])

  const handleQuickEvolve = async () => {
    if (!taskId || evolving) return
    setEvolving(true)
    try {
      const individuals = await fetch(`/tasks/${taskId}/individuals?pareto_rank=1&limit=100`).then((r) => r.json())
      if (!individuals.length) {
        toast.error('此任務沒有帕雷托前緣個體，無法繼續演化')
        return
      }
      individuals.sort((a: IndividualSummary, b: IndividualSummary) => (b.cagr || 0) - (a.cagr || 0))
      const top10 = individuals.slice(0, Math.max(1, Math.ceil(individuals.length * 0.1)))
      const champion = top10[0]
      const params = JSON.parse(champion.params_json || '{}')
      const original = tasks.find((t) => t.task_id === taskId)
      if (!original) return

      const res = await fetch('/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy_config_id: original.config.strategy_config_id,
          symbols: original.config.symbols,
          start_date: original.config.start_date,
          end_date: original.config.end_date,
          timeframe: original.config.timeframe,
          population_size: original.config.population_size || 200,
          max_generations: original.config.max_generations || 50,
          seed_params: params,
        }),
      })
      const task = await res.json()
      addTask(task)
      setCurrentView('monitor')
    } catch (e) {
      console.error(e)
    }
    setEvolving(false)
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">結果分析</h1>
        <div className="flex items-center gap-2">
          <select
            className="px-3 py-1.5 border rounded-lg text-sm outline-none max-w-xs"
            value={taskId || ''}
            onChange={(e) => setTaskId(e.target.value || null)}
          >
            {tasks.map((t) => (
              <option key={t.task_id} value={t.task_id}>
                {t.name || t.task_id.slice(0, 8)} — {t.config.symbols.slice(0, 3).join('/')} {t.config.timeframe}
              </option>
            ))}
          </select>
          {taskId && (
            <>
              <a href={`/tasks/${taskId}/export`} target="_blank" rel="noopener noreferrer"
                className="px-2.5 py-1.5 border border-gray-300 text-gray-600 rounded-lg text-xs hover:bg-gray-50">
                匯出 CSV
              </a>
              <a href={`/tasks/${taskId}/export/json`} target="_blank" rel="noopener noreferrer"
                className="px-2.5 py-1.5 border border-gray-300 text-gray-600 rounded-lg text-xs hover:bg-gray-50">
                匯出 JSON
              </a>
            </>
          )}
          <button onClick={handleQuickEvolve} disabled={evolving}
            className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700 disabled:opacity-50 cursor-pointer">
            {evolving ? '演化中...' : '前 10% 快速演化'}
          </button>
        </div>
      </div>

      {taskId && (
        <div className="flex gap-1 mb-4 border-b">
          {(['scatter', 'trend', 'equity', 'heatmap', 'compare', 'ensemble'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm border-b-2 cursor-pointer ${
                tab === t ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500'
              }`}>
              {t === 'scatter' ? '帕雷托散點' : t === 'trend' ? '演化歷程' : t === 'equity' ? '資金曲線' : t === 'heatmap' ? '參數熱圖' : t === 'compare' ? '策略對比' : '策略集成'}
            </button>
          ))}
        </div>
      )}

      {!taskId && <div className="text-center py-16 text-gray-400">請選擇一個已完成的任務</div>}

      {tab === 'scatter' && taskId && <ParetoScatter3D taskId={taskId} />}
      {tab === 'trend' && taskId && <EvolutionTrend taskId={taskId} />}
      {tab === 'equity' && taskId && <EquityCurve taskId={taskId} />}
      {tab === 'heatmap' && taskId && <ParamHeatmap taskId={taskId} />}
      {tab === 'compare' && taskId && <ComparePanel taskId={taskId} />}
      {tab === 'ensemble' && taskId && <EnsemblePanel taskId={taskId} />}

      <IndividualDrawer />
    </div>
  )
}
