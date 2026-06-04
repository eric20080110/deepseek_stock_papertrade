import { useEffect, useRef, useState } from 'react'
import { X, Save } from 'lucide-react'
import { toast } from '../../lib/toast'

interface Props {
  taskId: string
  sid: string
  onClose: () => void
}

export function ChampionDetailDrawer({ taskId, sid, onClose }: Props) {
  const equityRef = useRef<HTMLDivElement>(null)
  const priceRefs = useRef<Record<string, HTMLDivElement | null>>({})
  interface EquityData {
    equity_curve?: number[]
    dates?: string[]
    dca_combined?: number[]
    symbol_curves?: Record<string, number[]>
    symbol_prices?: Record<string, number[]>
    symbol_trades?: Record<string, Trade[]>
    n_windows?: number
  }

  interface Trade {
    direction: number
    entry_bar: number
    exit_bar: number
  }

  const [data, setData] = useState<EquityData | null>(null)
  const [symbols, setSymbols] = useState<string[]>([])
  const [metrics, setMetrics] = useState<{ totalReturn: number; valReturn: number | null } | null>(null)
  const [logScale, setLogScale] = useState(false)

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
    const Plotly = (window as unknown as Record<string, unknown>).Plotly as
      { newPlot: (el: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config: Record<string, unknown>) => void } | undefined
    if (!Plotly) return
    const combined = data.equity_curve || []
    const dates = data.dates || []
    const xDates = dates.length > 0 ? dates : Array.from({ length: combined.length }, (_, i) => String(i))
    const isSingleWindow = (data.n_windows ?? 1) <= 1
    const cut = isSingleWindow ? Math.floor(combined.length * 0.7) : 0

    let maxPeak = combined[0]
    const drawdownPct = combined.map(v => {
      maxPeak = Math.max(maxPeak, v)
      return ((v - maxPeak) / maxPeak) * 100
    })

    const traces: Record<string, unknown>[] = []
    if (isSingleWindow) {
      traces.push({ x: xDates.slice(0, cut), y: combined.slice(0, cut),
        type: 'scatter', mode: 'lines', name: '訓練',
        line: { color: '#2563eb' },
      }, { x: xDates.slice(cut), y: combined.slice(cut),
        type: 'scatter', mode: 'lines', name: '驗證',
        line: { color: '#dc2626' },
      })
    } else {
      traces.push({ x: xDates, y: combined,
        type: 'scatter', mode: 'lines', name: '資金曲線',
        line: { color: '#2563eb' },
      })
    }
    if (data.dca_combined?.length) {
      traces.push({
        x: xDates.slice(0, data.dca_combined.length), y: data.dca_combined,
        type: 'scatter', mode: 'lines', name: '定投對照',
        line: { color: '#22c55e', width: 2, dash: 'dot' },
      })
    }
    traces.push({ x: xDates.slice(0, combined.length), y: drawdownPct, type: 'scatter', mode: 'lines', name: '回撤', line: { color: '#ef4444' }, yaxis: 'y2', fill: 'tozeroy' })
    const last = combined[combined.length - 1]
    const initialCapital = combined[0] || 1
    const totalReturn = ((last / initialCapital) - 1) * 100
    const valReturn = isSingleWindow && cut > 0 && cut < combined.length ? ((last / combined[cut]) - 1) * 100 : null
    setMetrics({ totalReturn, valReturn })

    Plotly.newPlot(equityRef.current, traces, {
      title: { text: '資金曲線' },
      margin: { t: 40, r: 60, b: 40, l: 60 },
      yaxis: { title: '金額', type: logScale ? 'log' : 'linear' },
      yaxis2: { title: '回撤 %', overlaying: 'y', side: 'right', automargin: true },
      height: 280,
      shapes: isSingleWindow && xDates[cut] ? [{ type: 'line', x0: xDates[cut], y0: 0, x1: xDates[cut], y1: 1, yref: 'paper', line: { color: '#9ca3af', dash: 'dash' } }] : [],
      paper_bgcolor: 'white', plot_bgcolor: 'white',
      legend: { x: 1, xanchor: 'right', y: 0, yanchor: 'bottom', font: { size: 10 } },
    }, { responsive: true, displayModeBar: false })
  }, [data, logScale])

  useEffect(() => {
    if (!data || symbols.length === 0) return
    const Plotly = (window as unknown as Record<string, unknown>).Plotly as
      { newPlot: (el: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config: Record<string, unknown>) => void } | undefined
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

      const traces: Record<string, unknown>[] = [{
        x: pxDates.slice(0, px.length), y: px,
        type: 'scatter', mode: 'lines', name: sym,
        line: { color: '#2563eb', width: 1.5 },
      }]
      const buy: { x: string[]; y: number[] } = { x: [], y: [] }
      const sell: { x: string[]; y: number[] } = { x: [], y: [] }
      symTrades.forEach((t: Trade) => {
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
        legend: { x: 1, xanchor: 'right', y: 0, yanchor: 'bottom', font: { size: 9 } },
      }, { responsive: true, displayModeBar: false })
    })
  }, [data, symbols])

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div className="relative w-[640px] bg-white shadow-xl h-full overflow-y-auto">
        <div className="sticky top-0 bg-white border-b p-4 flex items-center justify-between z-10">
          <h3 className="font-semibold">基因詳情</h3>
          <div className="flex items-center gap-2">
            <button onClick={async () => {
              const name = window.prompt('請輸入策略名稱：')
              if (!name) return
              try {
                const res = await fetch(`/gene-pool/${sid}/create-strategy`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ name, description: '' }),
                })
                if (res.ok) {
                  toast.success('策略已創建！')
                  onClose()
                } else {
                  const err = await res.text()
                  toast.error('創建失敗: ' + err)
                }
              } catch (e) {
                toast.error('創建失敗: ' + String(e))
              }
            }} className="flex items-center gap-1 px-2 py-1 text-xs border border-blue-200 text-blue-700 rounded hover:bg-blue-50 cursor-pointer">
              <Save className="w-3 h-3" />另存為策略
            </button>
            <button onClick={onClose} className="cursor-pointer p-1 hover:bg-gray-100 rounded"><X className="w-4 h-4" /></button>
          </div>
        </div>
        <div className="p-4 space-y-4">
          {!data ? (
            <div className="text-center py-12 text-gray-400">載入中...</div>
          ) : (
            <>
              {metrics && (
                <div className="flex gap-4 mb-2 text-sm">
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
