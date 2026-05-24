import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import { useTaskStore } from '../../store/taskStore'
import type { StrategyConfig } from '../../types/strategy'
import { SymbolInput } from './SymbolInput'

const TF_LABELS: Record<string, string> = {
  '1d': '日 K', '1h': '小時 K', '30m': '30 分 K',
  '15m': '15 分 K', '5m': '5 分 K', '1m': '1 分 K',
}
const TF_DEFAULTS: Record<string, { pop: number; gens: number }> = {
  '1d': { pop: 200, gens: 50 }, '1h': { pop: 100, gens: 30 },
  '30m': { pop: 60, gens: 20 }, '15m': { pop: 50, gens: 15 },
  '5m': { pop: 30, gens: 10 }, '1m': { pop: 20, gens: 8 },
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec} 秒`
  if (sec < 3600) return `${Math.round(sec / 60)} 分鐘`
  if (sec < 86400) return `${(sec / 3600).toFixed(1)} 小時`
  return `${(sec / 86400).toFixed(1)} 天`
}

export function TaskForm() {
  const [strategies, setStrategies] = useState<StrategyConfig[]>([])
  const [strategyId, setStrategyId] = useState('')
  const [symbols, setSymbols] = useState<string[]>([])
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [timeframe, setTimeframe] = useState('1d')
  const [popSize, setPopSize] = useState(200)
  const [maxGens, setMaxGens] = useState(50)
  const [crossoverRate, setCrossoverRate] = useState(0.8)
  const [mutationRate, setMutationRate] = useState(0.15)
  const [earlyStop, setEarlyStop] = useState(10)
  const [advanced, setAdvanced] = useState(false)
  const [saving, setSaving] = useState(false)
  const [estimate, setEstimate] = useState<{ estimated_seconds: number; time_per_gen_sec: number } | null>(null)
  const [estimating, setEstimating] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [isRotation, setIsRotation] = useState(false)
  const [rotationSymbols, setRotationSymbols] = useState<string[]>([])

  const addTask = useTaskStore((s) => s.addTask)
  const setCurrentView = useTaskStore((s) => s.setCurrentView)
  const selectedStrategy = useTaskStore((s) => s.selectedStrategy)
  const setSelectedStrategy = useTaskStore((s) => s.setSelectedStrategy)
  const seedParams = useTaskStore((s) => s.seedParams)
  const setSeedParams = useTaskStore((s) => s.setSeedParams)
  const retryConfig = useTaskStore((s) => s.retryConfig)
  const setRetryConfig = useTaskStore((s) => s.setRetryConfig)

  useEffect(() => {
    api.listStrategies().then((s) => {
      const userStrategies = s.filter((x) => !x.is_template)
      setStrategies(userStrategies)
      if (retryConfig) {
        setStrategyId(retryConfig.strategy_config_id)
        setSymbols(retryConfig.symbols)
        setStartDate(retryConfig.start_date)
        setEndDate(retryConfig.end_date)
        setTimeframe(retryConfig.timeframe || '1d')
        if (retryConfig.population_size) setPopSize(retryConfig.population_size)
        if (retryConfig.max_generations) setMaxGens(retryConfig.max_generations)
        setRetryConfig(null)
      } else if (selectedStrategy) {
        setStrategyId(selectedStrategy)
        setSelectedStrategy(null)
      }
    })
  }, [])

  useEffect(() => {
    if (!strategyId) { setIsRotation(false); setRotationSymbols([]); return }
    const s = strategies.find((x) => x.config_id === strategyId)
    if (s) { setIsRotation(s.is_rotation); setRotationSymbols(s.rotation_symbols) }
  }, [strategyId, strategies])

  const handleOpenConfirm = async () => {
    if (!valid) return
    setEstimating(true)
    try {
      const res = await fetch('/tasks/estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbols, start_date: startDate, end_date: endDate,
          timeframe, population_size: popSize, max_generations: maxGens,
        }),
      })
      setEstimate(await res.json())
    } catch {
      setEstimate(null)
    }
    setEstimating(false)
    setShowConfirm(true)
  }

  const handleSubmit = async () => {
    if (!strategyId || (!isRotation && symbols.length === 0) || !startDate || !endDate) return
    setSaving(true)
    try {
      const body: Record<string, any> = {
        strategy_config_id: strategyId,
        symbols: isRotation ? [] : symbols,
        start_date: startDate,
        end_date: endDate,
        timeframe,
        population_size: popSize,
        max_generations: maxGens,
        crossover_rate: crossoverRate,
        mutation_rate: mutationRate,
        early_stop_generations: earlyStop,
      }
      if (seedParams) body.seed_params = seedParams
      const res = await fetch('/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const task = await res.json()
      addTask(task)
      setSeedParams(null)
      setCurrentView('queue')
    } catch (e) {
      console.error(e)
    }
    setSaving(false)
  }

  const handleTimeframeChange = (v: string) => {
    setTimeframe(v)
    const d = TF_DEFAULTS[v] || TF_DEFAULTS['1h']
    setPopSize(d.pop)
    setMaxGens(d.gens)
  }

  const valid = strategyId && (isRotation || symbols.length > 0) && startDate && endDate

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">
        {seedParams ? '繼續演化（種子繁衍）' : '新增演化任務'}
      </h1>
      {seedParams && (
        <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
          <div className="text-xs text-emerald-700 font-medium">冠軍種子參數（初始族群由此參數變異產生）</div>
          <div className="mt-1 text-xs text-emerald-600 font-mono break-all">
            {JSON.stringify(seedParams)}
          </div>
        </div>
      )}

      <div className="space-y-5">
        <div>
          <label className="block text-sm font-medium mb-1">策略定義 *</label>
          <select
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">選擇策略...</option>
            {strategies.map((s) => (
              <option key={s.config_id} value={s.config_id}>{s.name}</option>
            ))}
          </select>
        </div>

        {isRotation ? (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="text-sm font-medium text-blue-800 mb-1">固定輪換標的（自動套用，無需選擇）</div>
            <div className="flex flex-wrap gap-1.5">
              {rotationSymbols.map((s) => (
                <span key={s} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-mono">{s}</span>
              ))}
            </div>
          </div>
        ) : (
          <SymbolInput symbols={symbols} onChange={setSymbols} />
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">起始日期 *</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">結束日期 *</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {[
            { label: '近 7 天', start: new Date(new Date().setDate(new Date().getDate() - 7)).toISOString().slice(0, 10) },
            { label: '近 1 個月', start: new Date(new Date().setMonth(new Date().getMonth() - 1)).toISOString().slice(0, 10) },
            { label: '近 6 個月', start: new Date(new Date().setMonth(new Date().getMonth() - 6)).toISOString().slice(0, 10) },
            { label: '近 1 年', start: new Date(new Date().setFullYear(new Date().getFullYear() - 1)).toISOString().slice(0, 10) },
            { label: '近 2 年', start: new Date(new Date().setFullYear(new Date().getFullYear() - 2)).toISOString().slice(0, 10) },
            { label: '近 3 年', start: new Date(new Date().setFullYear(new Date().getFullYear() - 3)).toISOString().slice(0, 10) },
            { label: '近 5 年', start: new Date(new Date().setFullYear(new Date().getFullYear() - 5)).toISOString().slice(0, 10) },
            { label: '全部資料', start: '2020-01-01' },
          ].map(({ label, start }) => {
            const today = new Date().toISOString().slice(0, 10)
            const active = startDate === start && endDate === today
            return (
              <button key={label} onClick={() => { setStartDate(start); setEndDate(today) }}
                className={`px-3 py-1.5 text-xs rounded-lg cursor-pointer transition-colors ${active ? 'bg-blue-600 text-white' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'}`}>
                {label}
              </button>
            )
          })}
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">K 線週期</label>
          <div className="flex gap-2 flex-wrap">
            {['1d', '1h', '30m', '15m', '5m', '1m'].map((v) => (
              <button key={v} onClick={() => handleTimeframeChange(v)}
                className={`px-4 py-2 text-sm rounded-lg cursor-pointer ${timeframe === v ? 'bg-blue-600 text-white' : 'bg-gray-100 hover:bg-gray-200'}`}>
                {TF_LABELS[v] || v}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">族群大小</label>
            <input type="number" min={10} max={2000} value={popSize} onChange={(e) => setPopSize(+e.target.value)}
              className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">總世代數</label>
            <input type="number" min={5} max={500} value={maxGens} onChange={(e) => setMaxGens(+e.target.value)}
              className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium">交叉機率：{crossoverRate.toFixed(2)}</label>
            <input type="range" min={0.5} max={1.0} step={0.05} value={crossoverRate} onChange={(e) => setCrossoverRate(+e.target.value)}
              className="w-full" />
          </div>
          <div>
            <label className="text-sm font-medium">變異機率：{mutationRate.toFixed(2)}</label>
            <input type="range" min={0.05} max={0.5} step={0.01} value={mutationRate} onChange={(e) => setMutationRate(+e.target.value)}
              className="w-full" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">提前停止世代數</label>
            <input type="number" min={3} max={50} value={earlyStop} onChange={(e) => setEarlyStop(+e.target.value)}
              className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>

        <button onClick={() => setAdvanced(!advanced)} className="text-sm text-blue-600 hover:text-blue-800 cursor-pointer">
          {advanced ? '收起' : '展開'}進階設定
        </button>
      </div>

      {valid && !showConfirm && (
        <div className="mt-6">
          <button onClick={handleOpenConfirm} disabled={estimating}
            className="w-full px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 cursor-pointer">
            {estimating ? '計算預估時間中...' : '建立任務'}
          </button>
        </div>
      )}

      {showConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 className="text-lg font-bold mb-2">確認執行</h3>
            <div className="text-sm text-gray-600 mb-4 space-y-1">
              <p>策略：{strategies.find(s => s.config_id === strategyId)?.name}</p>
              <p>標的：{isRotation ? `輪換 (${rotationSymbols.join(', ')})` : symbols.join(', ')}</p>
              <p>週期：{TF_LABELS[timeframe] || timeframe}</p>
              <p>族群：{popSize} ｜ 世代：{maxGens}</p>
              <div className="mt-3 pt-3 border-t space-y-1">
                {estimate ? (
                  <>
                    <div className="flex justify-between text-xs text-gray-500">
                      <span>每代預估</span>
                      <span>{formatDuration(Math.round(estimate.time_per_gen_sec))}</span>
                    </div>
                    <div className="flex justify-between font-semibold">
                      <span>總預估時間</span>
                      <span className={estimate.estimated_seconds > 7200 ? 'text-amber-600' : 'text-emerald-600'}>
                        {formatDuration(estimate.estimated_seconds)}
                      </span>
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-gray-400">預估時間不可用</p>
                )}
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setShowConfirm(false)}
                className="flex-1 px-4 py-2 border rounded-lg text-sm hover:bg-gray-50 cursor-pointer">
                取消
              </button>
              <button onClick={handleSubmit} disabled={saving}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 cursor-pointer">
                {saving ? '建立中...' : '確認執行'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
