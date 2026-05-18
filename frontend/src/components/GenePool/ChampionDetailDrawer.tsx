import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

interface Props {
  taskId: string
  sid: string
  onClose: () => void
}

export function ChampionDetailDrawer({ taskId, sid, onClose }: Props) {
  const equityRef = useRef<HTMLDivElement>(null)
  const priceRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [data, setData] = useState<any>(null)
  const [symbols, setSymbols] = useState<string[]>([])

  useEffect(() => {
    fetch(`/tasks/${taskId}/individuals/${sid}/equity-curve`)
      .then((r) => r.json())
      .then((d) => {
        setData(d)
        setSymbols(Object.keys(d.symbol_curves || {}))
      })
  }, [taskId, sid])

  useEffect(() => {
    if (!equityRef.current || !data) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return
    const combined = data.equity_curve || []
    const dates = data.dates || []
    const xDates = dates.length > 0 ? dates : Array.from({ length: combined.length }, (_, i) => String(i))
    const cut = Math.floor(combined.length * 0.7)

    const traces: any[] = [{
      x: xDates.slice(0, cut), y: combined.slice(0, cut),
      type: 'scatter', mode: 'lines', name: '訓練',
      line: { color: '#2563eb' },
    }, {
      x: xDates.slice(cut), y: combined.slice(cut),
      type: 'scatter', mode: 'lines', name: '驗證',
      line: { color: '#dc2626' },
    }]
    if (data.dca_combined?.length) {
      traces.push({
        x: xDates.slice(0, data.dca_combined.length), y: data.dca_combined,
        type: 'scatter', mode: 'lines', name: '定投對照',
        line: { color: '#22c55e', width: 2, dash: 'dot' },
      })
    }
    Plotly.newPlot(equityRef.current, traces, {
      title: { text: '資金曲線' },
      margin: { t: 40, r: 20, b: 40, l: 60 },
      height: 280,
      shapes: [{ type: 'line', x0: xDates[cut], y0: 0, x1: xDates[cut], y1: 1, yref: 'paper', line: { color: '#9ca3af', dash: 'dash' } }],
      paper_bgcolor: 'white', plot_bgcolor: 'white',
      legend: { x: 1, xanchor: 'right', y: 1, font: { size: 10 } },
    }, { responsive: true, displayModeBar: false })
  }, [data])

  useEffect(() => {
    if (!data || symbols.length === 0) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return
    const dates = data.dates || []
    const prices = data.symbol_prices || {}
    const trades = data.symbol_trades || {}

    symbols.forEach((sym) => {
      const px = prices[sym]
      if (!px?.length) return
      const el = priceRefs.current[sym]
      if (!el) return
      const symTrades = trades[sym] || []
      const pxDates = dates.length > 0 ? dates : Array.from({ length: px.length }, (_, i) => String(i))

      const traces: any[] = [{
        x: pxDates.slice(0, px.length), y: px,
        type: 'scatter', mode: 'lines', name: sym,
        line: { color: '#2563eb', width: 1.5 },
      }]
      const buy: { x: string[]; y: number[] } = { x: [], y: [] }
      const sell: { x: string[]; y: number[] } = { x: [], y: [] }
      symTrades.forEach((t: any) => {
        if (px[t.entry_bar] == null || px[t.exit_bar] == null) return
        if (t.direction === 1) {
          buy.x.push(pxDates[t.entry_bar]); buy.y.push(px[t.entry_bar])
          sell.x.push(pxDates[t.exit_bar]); sell.y.push(px[t.exit_bar])
        } else {
          sell.x.push(pxDates[t.entry_bar]); sell.y.push(px[t.entry_bar])
          buy.x.push(pxDates[t.exit_bar]); buy.y.push(px[t.exit_bar])
        }
      })
      if (buy.x.length) {
        traces.push({
          x: buy.x, y: buy.y, type: 'scatter', mode: 'markers', name: '買進',
          marker: { symbol: 'triangle-up', size: 10, color: '#16a34a', line: { color: '#14532d', width: 1 } },
        })
      }
      if (sell.x.length) {
        traces.push({
          x: sell.x, y: sell.y, type: 'scatter', mode: 'markers', name: '賣出',
          marker: { symbol: 'triangle-down', size: 10, color: '#dc2626', line: { color: '#7f1d1d', width: 1 } },
        })
      }
      Plotly.newPlot(el, traces, {
        title: { text: `${sym} 價格走勢` },
        margin: { t: 35, r: 20, b: 40, l: 60 },
        height: 200,
        paper_bgcolor: 'white', plot_bgcolor: 'white',
        legend: { x: 1, xanchor: 'right', y: 1, font: { size: 9 } },
      }, { responsive: true, displayModeBar: false })
    })
  }, [data, symbols])

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div className="relative w-[640px] bg-white shadow-xl h-full overflow-y-auto">
        <div className="sticky top-0 bg-white border-b p-4 flex items-center justify-between z-10">
          <h3 className="font-semibold">基因詳情</h3>
          <button onClick={onClose} className="cursor-pointer p-1 hover:bg-gray-100 rounded"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-4 space-y-4">
          {!data ? (
            <div className="text-center py-12 text-gray-400">載入中...</div>
          ) : (
            <>
              <div ref={equityRef} className="w-full" />
              <div className="space-y-3">
                {symbols.map((sym) => (
                  <div key={sym} ref={(el) => { priceRefs.current[sym] = el }} className="w-full" />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
