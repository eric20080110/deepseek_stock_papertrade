import { useEffect, useRef, useState } from 'react'

interface Props {
  taskId: string
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
    trades: Record<string, any[]>
    dates: string[]
  }>({ prices: {}, trades: {}, dates: [] })
  const dcaRef = useRef<{ x: string[]; y: number[] } | null>(null)
  const layoutRef = useRef<any>(null)
  const [sid, setSid] = useState<string | null>(null)
  const [individuals, setIndividuals] = useState<any[]>([])
  const [symbolsList, setSymbolsList] = useState<string[]>([])

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
    const Plotly = (window as any).Plotly
    if (!Plotly) return
    let cancelled = false
    const el = chartRef.current

    const renderFull = (data: any) => {
      if (cancelled || !el) return
      const combined: number[] = data.equity_curve || []
      const symbolCurves: Record<string, number[]> = data.symbol_curves || {}
      const symbolTrades: Record<string, any[]> = data.symbol_trades || {}
      const symbolPrices: Record<string, number[]> = data.symbol_prices || {}
      const dcaCombined: number[] = data.dca_combined || []
      const dates: string[] = data.dates || []
      const symbols = Object.keys(symbolCurves)

      setSymbolsList(symbols)
      priceDataRef.current = { prices: symbolPrices, trades: symbolTrades, dates }
      if (combined.length === 0) return

      const cut = Math.floor(combined.length * 0.7)
      const xDates = dates.length > 0 ? dates : Array.from({ length: combined.length }, (_, i) => String(i))
      const pxDates = dates.length > 0 ? dates : Array.from({ length: Object.values(symbolPrices)[0]?.length || 500 }, (_, i) => String(i))

      const traces: any[] = []
      if (symbols.length <= 1) {
        traces.push(
          { x: xDates.slice(0, cut), y: combined.slice(0, cut), type: 'scatter', mode: 'lines', name: '訓練集', line: { color: '#2563eb' } },
          { x: xDates.slice(cut), y: combined.slice(cut), type: 'scatter', mode: 'lines', name: '驗證集', line: { color: '#dc2626' } }
        )
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

      const layout = {
        title: { text: '資金曲線' },
        margin: { t: 40, r: 20, b: 40, l: 60 },
        height: 300,
        xaxis: { title: '日期' },
        yaxis: { title: '資金' },
        shapes: symbols.length <= 1 && cut > 0 && xDates[cut] ? [{
          type: 'line', x0: xDates[cut], y0: 0, x1: xDates[cut], y1: 1,
          yref: 'paper', line: { color: '#9ca3af', dash: 'dash' },
        }] : [],
        paper_bgcolor: 'white', plot_bgcolor: 'white',
        legend: { x: 1, xanchor: 'right', y: 1, font: { size: 10 } },
      }
      layoutRef.current = layout
      Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false })
      el.on('plotly_relayout', handleRelayout)
    }

    const handleRelayout = async (eventData: any) => {
      if (cancelled || !el) return
      const isReset = eventData['xaxis.autorange'] === true
      const x0 = eventData['xaxis.range[0]']
      const x1 = eventData['xaxis.range[1]']

      if (isReset) {
        const resp = await fetch(`/tasks/${taskId}/individuals/${sid}/equity-curve?max_points=500`)
        if (!resp.ok || cancelled) return
        renderFull(await resp.json())
        return
      }
      if (!x0 || !x1) return

      const startTs = parseDateToTs(String(x0))
      const endTs = parseDateToTs(String(x1))
      if (!startTs || !endTs || startTs >= endTs) return

      const resp = await fetch(
        `/tasks/${taskId}/individuals/${sid}/equity-curve?max_points=1000&start_ts=${startTs}&end_ts=${endTs}`
      )
      if (!resp.ok || cancelled) return
      const zoomData = await resp.json()

      const combined: number[] = zoomData.equity_curve || []
      const dates: string[] = zoomData.dates || []
      if (combined.length === 0) return

      const xDates = dates.length > 0 ? dates : Array.from({ length: combined.length }, (_, i) => String(i))
      const traces: any[] = [{
        x: xDates, y: combined,
        type: 'scatter', mode: 'lines', name: '資金曲線 (放大)',
        line: { color: '#2563eb' },
      }]
      if (dcaRef.current) {
        traces.push({ x: dcaRef.current.x, y: dcaRef.current.y, type: 'scatter', mode: 'lines', name: '定投對照', line: { color: '#22c55e', width: 2, dash: 'dot' } })
      }
      Plotly.react(el, traces, layoutRef.current || {})
    }

    fetch(`/tasks/${taskId}/individuals/${sid}/equity-curve?max_points=500`)
      .then((r) => r.json())
      .then((data) => { if (!cancelled) renderFull(data) })

    return () => {
      cancelled = true
      Plotly.purge(el)
    }
  }, [taskId, sid])

  // Render per-symbol price charts
  useEffect(() => {
    if (!sid || symbolsList.length === 0) return
    const Plotly = (window as any).Plotly
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
      const traces: any[] = [{
        x: pxDates.slice(0, px.length), y: px,
        type: 'scatter', mode: 'lines', name: sym,
        line: { color: '#2563eb', width: 1.5 },
      }]
      const buy = { x: [] as string[], y: [] as number[] }
      const sell = { x: [] as string[], y: [] as number[] }
      symTrades.forEach((t: any) => {
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
        legend: { x: 1, xanchor: 'right', y: 1, font: { size: 9 } },
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
      <div ref={chartRef} className="w-full" />
      <div className="mt-2 space-y-3">
        {symbolsList.map((sym) => (
          <div key={sym} ref={(el) => { priceRefs.current[sym] = el }} className="w-full" />
        ))}
      </div>
    </div>
  )
}
