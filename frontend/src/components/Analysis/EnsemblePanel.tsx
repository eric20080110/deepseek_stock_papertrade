import { useState, useEffect } from 'react'
import { toast } from '../../lib/toast'

interface ChampionInfo {
  strategy_id: string
  cagr: number
  sharpe_ratio: number
  max_drawdown: number
  profit_factor: number
  trade_count: number
  params_json?: string
}

interface EnsembleResult {
  weighted_metrics: Record<string, number>
  n_strategies: number
  threshold: number
  equity_curve: number[]
  equity_timestamps: number[]
  symbol_results: Record<string, {
    total_return: number
    annualized_return: number
    sharpe_ratio: number
    max_drawdown: number
    win_rate: number
    profit_factor: number
    trade_count: number
  }>
  duration_sec: number
}

interface Props {
  taskId: string
}

export function EnsemblePanel({ taskId }: Props) {
  const [champions, setChampions] = useState<ChampionInfo[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [threshold, setThreshold] = useState(0.2)
  const [result, setResult] = useState<EnsembleResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [chartRef, setChartRef] = useState<HTMLDivElement | null>(null)
  const [symbolsInput, setSymbolsInput] = useState('')
  const [logScale, setLogScale] = useState(false)

  useEffect(() => {
    if (!taskId) return
    fetch(`/tasks/${taskId}/individuals?pareto_rank=1&limit=50`)
      .then((r) => r.json())
      .then((data) => setChampions(data))
      .catch(() => {})
    fetch(`/tasks/${taskId}`)
      .then((r) => r.json())
      .then((task) => {
        const syms = task.config?.symbols
        if (syms && syms.length > 0) {
          setSymbolsInput(syms.join(', '))
        } else {
          const scid = task.config?.strategy_config_id
          if (scid) {
            fetch(`/strategies/${scid}`)
              .then((r2) => r2.json())
              .then((sc) => {
                if (sc.rotation_symbols?.length) {
                  setSymbolsInput(sc.rotation_symbols.join(', '))
                }
              })
              .catch(() => {})
          }
        }
      })
      .catch(() => {})
  }, [taskId])

  const toggle = (sid: string) => {
    const next = new Set(selected)
    if (next.has(sid)) next.delete(sid); else next.add(sid)
    setSelected(next)
  }

  const runEnsemble = async () => {
    if (selected.size < 2) {
      toast.error('請至少選擇 2 條策略')
      return
    }
    setLoading(true)
    setResult(null)
    try {
      const strategies = champions
        .filter((c) => selected.has(c.strategy_id))
        .map((c) => ({
          strategy_id: c.strategy_id,
          params: c.params_json ? JSON.parse(c.params_json) : {},
        }))
      const res = await fetch(`/tasks/${taskId}/ensemble`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategies,
          symbols: symbolsInput.split(',').map((s) => s.trim()).filter(Boolean),
          start_date: '',
          end_date: '',
          timeframe: '1d',
          ensemble_threshold: threshold,
        }),
      })
      if (!res.ok) {
        const errBody = await res.text()
        throw new Error(errBody ? `${res.status}: ${errBody.slice(0, 200)}` : `HTTP ${res.status}`)
      }
      const data: EnsembleResult = await res.json()
      setResult(data)
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!result || !chartRef || !result.equity_curve?.length) return
    const Plotly = (window as unknown as Record<string, unknown>).Plotly as unknown as {
      newPlot: (el: HTMLElement, traces: unknown[], layout: unknown, config: unknown) => void
    }
    if (!Plotly || !Plotly.newPlot) return
    const dates = result.equity_timestamps?.length === result.equity_curve.length
      ? result.equity_timestamps.map((ts) => new Date(ts * 1000).toISOString().slice(0, 10))
      : Array.from({ length: result.equity_curve.length }, (_, i) => i)
    const layout: Record<string, unknown> = {
      title: { text: `集成資金曲線 (${result.n_strategies} 條, threshold=${result.threshold})` },
      margin: { t: 40, r: 20, b: 50, l: 60 },
      height: 300,
      xaxis: { title: '日期', type: 'date' },
      yaxis: { title: '金額', type: logScale ? 'log' : 'linear' },
      paper_bgcolor: 'white', plot_bgcolor: 'white',
      legend: { x: 1, xanchor: 'right', y: 0, yanchor: 'bottom', font: { size: 9 } },
    }
    const trace = {
      x: dates,
      y: result.equity_curve,
      type: 'scatter', mode: 'lines',
      name: '集成',
      line: { color: '#2563eb', width: 2 },
    }
    Plotly.newPlot(chartRef, [trace], layout, { responsive: true, displayModeBar: false })
  }, [result, chartRef, logScale])

  return (
    <div className="space-y-4">
      <div className="text-sm font-semibold mb-2">Champion 集成 — 訊號加權平均</div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Threshold:</span>
        <input
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          className="w-20 border rounded px-2 py-1 text-xs"
        />
        <span className="text-xs text-gray-500 ml-2">標的:</span>
        <input
          type="text"
          value={symbolsInput}
          onChange={(e) => setSymbolsInput(e.target.value)}
          placeholder="BTC/USDT, ETH/USDT"
          className="flex-1 border rounded px-2 py-1 text-xs"
        />
        <button
          onClick={runEnsemble}
          disabled={loading}
          className="ml-2 px-4 py-1.5 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '計算中...' : `執行集成 (${selected.size} 條)`}
        </button>
      </div>

      <div className="border rounded max-h-40 overflow-y-auto">
        {champions.length === 0 ? (
          <div className="text-xs text-gray-400 p-3">暫無 champion</div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="p-2 w-8" />
                <th className="p-2 text-left">策略 ID</th>
                <th className="p-2 text-right">CAGR %</th>
                <th className="p-2 text-right">Sharpe</th>
                <th className="p-2 text-right">DD %</th>
              </tr>
            </thead>
            <tbody>
              {champions.map((c) => (
                <tr key={c.strategy_id} className="border-b last:border-b-0 hover:bg-gray-50">
                  <td className="p-2 text-center">
                    <input
                      type="checkbox"
                      checked={selected.has(c.strategy_id)}
                      onChange={() => toggle(c.strategy_id)}
                    />
                  </td>
                  <td className="p-2 font-mono">{c.strategy_id.slice(0, 12)}...</td>
                  <td className="p-2 text-right">{(c.cagr * 100).toFixed(1)}</td>
                  <td className="p-2 text-right">{c.sharpe_ratio.toFixed(2)}</td>
                  <td className="p-2 text-right text-red-500">{c.max_drawdown.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex items-center justify-end mb-1">
        <button onClick={() => setLogScale(p => !p)} className="text-xs px-2 py-0.5 border rounded hover:bg-gray-100 cursor-pointer">
          {logScale ? '線性' : '對數'}
        </button>
      </div>
      <div ref={setChartRef} className="w-full" />

      {result && (
        <>
          <div className="grid grid-cols-4 gap-3">
            <div className="border rounded p-3 bg-white">
              <div className="text-xs text-gray-500">年化報酬</div>
              <div className="text-lg font-bold">{(result.weighted_metrics.annualized_return * 100).toFixed(2)}%</div>
            </div>
            <div className="border rounded p-3 bg-white">
              <div className="text-xs text-gray-500">Sharpe</div>
              <div className="text-lg font-bold">{result.weighted_metrics.sharpe_ratio.toFixed(2)}</div>
            </div>
            <div className="border rounded p-3 bg-white">
              <div className="text-xs text-gray-500">MDD</div>
              <div className="text-lg font-bold text-red-500">{result.weighted_metrics.max_drawdown.toFixed(2)}%</div>
            </div>
            <div className="border rounded p-3 bg-white">
              <div className="text-xs text-gray-500">交易次數</div>
              <div className="text-lg font-bold">{result.weighted_metrics.trade_count}</div>
            </div>
          </div>
          <div className="border rounded p-3 bg-white">
            <div className="text-xs text-gray-500 mb-1">各標的績效</div>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b">
                  <th className="p-1 text-left">標的</th>
                  <th className="p-1 text-right">年化報酬</th>
                  <th className="p-1 text-right">Sharpe</th>
                  <th className="p-1 text-right">MDD</th>
                  <th className="p-1 text-right">勝率</th>
                  <th className="p-1 text-right">PF</th>
                  <th className="p-1 text-right">交易次數</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.symbol_results).map(([sym, sr]) => (
                  <tr key={sym} className="border-b last:border-b-0">
                    <td className="p-1 font-medium">{sym}</td>
                    <td className="p-1 text-right">{(sr.annualized_return * 100).toFixed(2)}%</td>
                    <td className="p-1 text-right">{sr.sharpe_ratio.toFixed(2)}</td>
                    <td className="p-1 text-right text-red-500">{sr.max_drawdown.toFixed(2)}%</td>
                    <td className="p-1 text-right">{sr.win_rate.toFixed(1)}%</td>
                    <td className="p-1 text-right">{sr.profit_factor.toFixed(2)}</td>
                    <td className="p-1 text-right">{sr.trade_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-xs text-gray-400">計算耗時: {result.duration_sec.toFixed(2)}s</div>
        </>
      )}
    </div>
  )
}
