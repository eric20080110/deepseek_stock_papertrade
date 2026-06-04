import { useEffect, useRef, useState } from 'react'
import { RollingMetricsChart } from './RollingMetricsChart'
import { MonteCarloPanel } from './MonteCarloPanel'

interface Props {
  taskId: string
}

interface Trade {
  direction: number
  entry_bar: number
  exit_bar: number
}

interface EquityCurveData {
  equity_curve?: number[]
  symbol_curves?: Record<string, number[]>
  symbol_trades?: Record<string, Trade[]>
  symbol_prices?: Record<string, number[]>
  dca_combined?: number[]
  dates: string[]
  n_windows?: number
}

interface IndividualRecord {
  strategy_id: string
}

const COLORS = ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#be123c', '#4f46e5']

function parseDateToTs(dateStr: string): number {
  return Math.floor(new Date(String(dateStr).replace(' ', 'T') + 'Z').getTime() / 1000)
}

export function EquityCurve({ taskId }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const priceRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const priceDataRef = useRef<{
    prices: Record<string, number[]>
    trades: Record<string, Trade[]>
    dates: string[]
  }>({ prices: {}, trades: {}, dates: [] })
  const dcaRef = useRef<{ x: string[]; y: number[] } | null>(null)
  const layoutRef = useRef<Record<string, unknown> | null>(null)
  const [sid, setSid] = useState<string | null>(null)
  const [individuals, setIndividuals] = useState<IndividualRecord[]>([])
  const [symbolsList, setSymbolsList] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [metrics, setMetrics] = useState<{ totalReturn: number; valReturn: number | null } | null>(null)
  const [logScale, setLogScale] = useState(false)

  useEffect(() => {
    fetch(`/tasks/${taskId}/individuals?pareto_rank=1&limit=50`)
      .then((r) => r.json())
      .then((data) => {
        setIndividuals(data)
        if (data.length > 0) setSid(data[0].strategy_id)
      })
  }, [taskId])

  useEffect(() => {
    if (!chartRef.current || !sid) return
    const Plotly = (window as unknown as Record<string, unknown>).Plotly as
      { newPlot: (el: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config: Record<string, unknown>) => void
        react: (el: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>) => void
        purge: (el: HTMLElement) => void } | undefined
    if (!Plotly) return
    let cancelled = false
    const el = chartRef.current

    const renderFull = (data: EquityCurveData) => {
      if (cancelled || !el) return
      const combined: number[] = data.equity_curve || []
      const symbolCurves: Record<string, number[]> = data.symbol_curves || {}
      const symbolTrades: Record<string, Trade[]> = data.symbol_trades || {}
      const symbolPrices: Record<string, number[]> = data.symbol_prices || {}
      const dcaCombined: number[] = data.dca_combined || []
      const dates: string[] = data.dates || []
      const symbols = Object.keys(symbolCurves)

      setSymbolsList(symbols)
      priceDataRef.current = { prices: symbolPrices, trades: symbolTrades, dates }
      if (combined.length === 0) return

      let maxPeak = combined[0]
      const drawdownPct = combined.map(v => {
        maxPeak = Math.max(maxPeak, v)
        return ((v - maxPeak) / maxPeak) * 100
      })

      const isSingleWindow = (data.n_windows ?? 1) <= 1
      const cut = isSingleWindow ? Math.floor(combined.length * 0.7) : 0
      const xDates = dates.length > 0 ? dates : Array.from({ length: combined.length }, (_, i) => String(i))
      const pxDates = dates.length > 0 ? dates : Array.from({ length: Object.values(symbolPrices)[0]?.length || 500 }, (_, i) => String(i))

      const traces: Record<string, unknown>[] = []
      if (symbols.length <= 1) {
        if (isSingleWindow) {
          traces.push(
            { x: xDates.slice(0, cut), y: combined.slice(0, cut), type: 'scatter', mode: 'lines', name: '訓練集', line: { color: '#2563eb' } },
            { x: xDates.slice(cut), y: combined.slice(cut), type: 'scatter', mode: 'lines', name: '驗證集', line: { color: '#dc2626' } }
          )
        } else {
          traces.push({ x: xDates, y: combined, type: 'scatter', mode: 'lines', name: '資金曲線', line: { color: '#2563eb' } })
        }
      } else {
        symbols.forEach((sym, i) => {
          const curve = symbolCurves[sym]
          if (!curve || curve.length === 0) return
          traces.push({ x: xDates.slice(0, curve.length), y: curve, type: 'scatter', mode: 'lines', name: sym, line: { color: COLORS[i % COLORS.length], width: 1.5 } })
        })
        if (combined.length > 0) {
          traces.push({ x: xDates.slice(0, combined.length), y: combined, type: 'scatter', mode: 'lines', name: '加權平均', line: { color: '#000', width: 2.5, dash: 'dash' } })
        }
      }

      if (dcaCombined.length > 0) {
        const dcaX = pxDates.slice(0, dcaCombined.length)
        dcaRef.current = { x: dcaX, y: dcaCombined }
        traces.push({ x: dcaX, y: dcaCombined, type: 'scatter', mode: 'lines', name: '定投對照', line: { color: '#22c55e', width: 2, dash: 'dot' } })
      } else {
        dcaRef.current = null
      }

      traces.push({ x: xDates.slice(0, combined.length), y: drawdownPct, type: 'scatter', mode: 'lines', name: '回撤', line: { color: '#ef4444' }, yaxis: 'y2', fill: 'tozeroy' })

      const last = combined[combined.length - 1]
      const initialCapital = combined[0] || 1
      const totalReturn = ((last / initialCapital) - 1) * 100
      const valReturn = isSingleWindow && symbols.length <= 1 && cut > 0 && cut < combined.length
        ? ((last / combined[cut]) - 1) * 100 : null
      setMetrics({ totalReturn, valReturn })

      const layout: Record<string, unknown> = {
        title: { text: '資金曲線' },
        margin: { t: 40, r: 60, b: 40, l: 60 },
        yaxis: { title: '金額', type: logScale ? 'log' : 'linear' },
        yaxis2: { title: '回撤 %', overlaying: 'y', side: 'right', automargin: true },
        shapes: isSingleWindow && symbols.length <= 1 && cut > 0 && xDates[cut] ? [{
          type: 'line', x0: xDates[cut], y0: 0, x1: xDates[cut], y1: 1,
          yref: 'paper', line: { color: '#9ca3af', dash: 'dash' },
        }] : [],
        paper_bgcolor: 'white', plot_bgcolor: 'white',
        legend: { x: 1, xanchor: 'right', y: 0, yanchor: 'bottom', font: { size: 10 } },
      }
      layoutRef.current = layout
      Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false })
      ;(el as unknown as { on: (e: string, h: (d: Record<string, unknown>) => void) => void }).on('plotly_relayout', handleRelayout)
    }

    const handleRelayout = async (eventData: Record<string, unknown>) => {
      if (cancelled || !el) return
      const isReset = eventData['xaxis.autorange'] === true
      const x0 = eventData['xaxis.range[0]'] as string | undefined
      const x1 = eventData['xaxis.range[1]'] as string | undefined

      if (isReset) {
        const resp = await fetch(`/tasks/${taskId}/individuals/${sid}/equity-curve?max_points=500`)
        if (!resp.ok || cancelled) return
        renderFull(await resp.json() as EquityCurveData)
        return
      }
      if (!x0 || !x1) return

      const startTs = parseDateToTs(x0)
      const endTs = parseDateToTs(x1)
      if (!startTs || !endTs || startTs >= endTs) return

      const resp = await fetch(
        `/tasks/${taskId}/individuals/${sid}/equity-curve?max_points=1000&start_ts=${startTs}&end_ts=${endTs}`
      )
      if (!resp.ok || cancelled) return
      const zoomData = await resp.json() as EquityCurveData

      const combined: number[] = zoomData.equity_curve || []
      const dates: string[] = zoomData.dates || []
      if (combined.length === 0) return

      const xDates = dates.length > 0 ? dates : Array.from({ length: combined.length }, (_, i) => String(i))

      let maxPeak = combined[0]
      const drawdownPct = combined.map(v => {
        maxPeak = Math.max(maxPeak, v)
        return ((v - maxPeak) / maxPeak) * 100
      })

      const traces: Record<string, unknown>[] = [{
        x: xDates, y: combined, type: 'scatter', mode: 'lines', name: '資金曲線',
        line: { color: '#2563eb' },
      }]
      if (dcaRef.current) {
        traces.push({ x: dcaRef.current.x, y: dcaRef.current.y, type: 'scatter', mode: 'lines', name: '定投對照', line: { color: '#22c55e', width: 2, dash: 'dot' } })
      }
      traces.push({ x: xDates, y: drawdownPct, type: 'scatter', mode: 'lines', name: '回撤', line: { color: '#ef4444' }, yaxis: 'y2', fill: 'tozeroy' })

      Plotly.newPlot(el, traces, {
        title: { text: '資金曲線' },
        margin: { t: 40, r: 60, b: 40, l: 60 },
        yaxis: { title: '金額', type: logScale ? 'log' : 'linear' },
        yaxis2: { title: '回撤 %', overlaying: 'y', side: 'right', automargin: true },
        paper_bgcolor: 'white', plot_bgcolor: 'white',
        legend: { x: 1, xanchor: 'right', y: 0, yanchor: 'bottom', font: { size: 10 } },
      }, { responsive: true, displayModeBar: false })
    }

    setLoading(true)
    fetch(`/tasks/${taskId}/individuals/${sid}/equity-curve?max_points=500`)
      .then((r) => r.json())
      .then((data: EquityCurveData) => { if (!cancelled) { setLoading(false); renderFull(data) } })
      .catch(() => { if (!cancelled) setLoading(false) })

    return () => {
      cancelled = true
      Plotly.purge(el)
    }
    }, [taskId, sid, logScale])

  useEffect(() => {
    if (!sid || symbolsList.length === 0) return
    const Plotly = (window as unknown as Record<string, unknown>).Plotly as
      { newPlot: (el: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config: Record<string, unknown>) => void } | undefined
    if (!Plotly) return
    const { prices, trades, dates } = priceDataRef.current
    const pxDates = dates.length > 0 ? dates : []
    if (pxDates.length === 0) return

    symbolsList.forEach((sym) => {
      const px = prices[sym]
      if (!px || px.length === 0) return
      const el = priceRefs.current[sym]
      if (!el) return

      const symTrades = trades[sym] || []
      const traces: Record<string, unknown>[] = [{
        x: pxDates.slice(0, px.length), y: px,
        type: 'scatter', mode: 'lines', name: sym,
        line: { color: '#2563eb', width: 1.5 },
      }]
      const buy = { x: [] as string[], y: [] as number[] }
      const sell = { x: [] as string[], y: [] as number[] }
      symTrades.forEach((t: Trade) => {
        if (t.direction === 1) {
          buy.x.push(pxDates[t.entry_bar]); buy.y.push(px[t.entry_bar])
          sell.x.push(pxDates[t.exit_bar]); sell.y.push(px[t.exit_bar])
        } else {
          sell.x.push(pxDates[t.entry_bar]); sell.y.push(px[t.entry_bar])
          buy.x.push(pxDates[t.exit_bar]); buy.y.push(px[t.exit_bar])
        }
      })
      if (buy.x.length > 0) {
        traces.push({ x: buy.x, y: buy.y, type: 'scatter', mode: 'markers', name: '買進', marker: { symbol: 'triangle-up', size: 10, color: '#16a34a', line: { color: '#14532d', width: 1 } } })
      }
      if (sell.x.length > 0) {
        traces.push({ x: sell.x, y: sell.y, type: 'scatter', mode: 'markers', name: '賣出', marker: { symbol: 'triangle-down', size: 10, color: '#dc2626', line: { color: '#7f1d1d', width: 1 } } })
      }
      Plotly.newPlot(el, traces, {
        title: { text: `${sym} 價格走勢` },
        margin: { t: 35, r: 20, b: 40, l: 60 },
        height: 220,
        xaxis: { title: '日期' },
        yaxis: { title: '價格' },
        paper_bgcolor: 'white', plot_bgcolor: 'white',
        legend: { x: 1, xanchor: 'right', y: 0, yanchor: 'bottom', font: { size: 9 } },
      }, { responsive: true, displayModeBar: false })
    })
  }, [sid, symbolsList])

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm text-gray-500">選擇個體：</span>
        <select value={sid || ''} onChange={(e) => setSid(e.target.value)}
          className="px-2 py-1 border rounded text-sm">
          {individuals.map((ind) => (
            <option key={ind.strategy_id} value={ind.strategy_id}>{ind.strategy_id}</option>
          ))}
        </select>
      </div>
      {loading && (
        <div className="w-full h-[300px] rounded-lg bg-gray-100 animate-pulse flex items-center justify-center text-gray-400 text-sm">
          載入資金曲線中...
        </div>
      )}
      {metrics && (
        <div className="flex gap-6 mb-2 text-sm">
          <span>總報酬率：<strong className={metrics.totalReturn >= 0 ? 'text-green-600' : 'text-red-600'}>{metrics.totalReturn >= 0 ? '+' : ''}{metrics.totalReturn.toFixed(2)}%</strong></span>
          {metrics.valReturn !== null && (
            <span>驗證集報酬率：<strong className={metrics.valReturn >= 0 ? 'text-green-600' : 'text-red-600'}>{metrics.valReturn >= 0 ? '+' : ''}{metrics.valReturn.toFixed(2)}%</strong></span>
          )}
        </div>
      )}
      <div className="flex items-center justify-end mb-1">
        <button onClick={() => setLogScale(p => !p)} className="text-xs px-2 py-0.5 border rounded hover:bg-gray-100 cursor-pointer">
          {logScale ? '線性' : '對數'}
        </button>
      </div>
      <div ref={chartRef} className="w-full" />
      <div className="mt-2 space-y-3">
        {symbolsList.map((sym) => (
          <div key={sym} ref={(el) => { priceRefs.current[sym] = el }} className="w-full" />
        ))}
      </div>
      {sid && <RollingMetricsChart taskId={taskId} sid={sid} />}
      {sid && <MonteCarloPanel taskId={taskId} sid={sid} />}
    </div>
  )
}
