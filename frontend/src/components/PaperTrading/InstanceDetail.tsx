import { useEffect, useState, useRef, useCallback } from 'react'
import { usePaperTradingWS } from '../../hooks/usePaperTradingWS'

interface Props {
  instanceId: string
}

export function InstanceDetail({ instanceId }: Props) {
  const [instance, setInstance] = useState<any>(null)
  const [positions, setPositions] = useState<any[]>([])
  const [trades, setTrades] = useState<any[]>([])
  const [chartData, setChartData] = useState<any>(null)
  const [tab, setTab] = useState<'monitor' | 'trades' | 'params'>('monitor')
  const chartRef = useRef<HTMLDivElement>(null)
  const priceRefs = useRef<Record<string, HTMLDivElement | null>>({})

  const [symbolsList, setSymbolsList] = useState<string[]>([])
  const priceChartDataRef = useRef<{ prices: Record<string, { dates: string[]; values: number[] }>; trades: any[] }>({ prices: {}, trades: [] })

  const refreshPositionsAndTrades = useCallback(() => {
    fetch(`/paper-trading/${instanceId}/positions`).then((r) => r.json()).then(setPositions)
    fetch(`/paper-trading/${instanceId}/trades`).then((r) => r.json()).then(setTrades)
  }, [instanceId])

  const refreshChart = useCallback(() => {
    fetch(`/paper-trading/${instanceId}/chart`).then((r) => r.json()).then((data) => {
      setChartData(data)
      const syms = Object.keys(data.prices || {})
      setSymbolsList(syms)
      priceChartDataRef.current = { prices: data.prices || {}, trades: data.trades || [] }
    })
  }, [instanceId])

  function refreshAll() {
    fetch(`/paper-trading/${instanceId}`).then((r) => r.json()).then(setInstance)
    refreshPositionsAndTrades()
    refreshChart()
  }

  // WebSocket for real-time updates from ticker
  usePaperTradingWS(instanceId, {
    onInit: (inst) => setInstance(inst),
    onTick: (payload) => {
      if (payload.instance) setInstance(payload.instance)
      if (payload.events && payload.events.length > 0) {
        // A trade happened — refresh positions, trades, and chart
        refreshPositionsAndTrades()
        refreshChart()
      }
    },
  })

  useEffect(() => {
    refreshAll()
  }, [instanceId])

  // equity curve chart
  useEffect(() => {
    if (!chartRef.current || !instance) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return
    const curve = (chartData?.equity_curve?.length ?? 0) > 0
      ? chartData.equity_curve
      : [instance.initial_capital, (instance.total_equity || instance.initial_capital)]
    const ts = (chartData?.equity_dates?.length ?? 0) > 0 ? chartData.equity_dates : []
    const fmtDate = (d: Date) =>
      `${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
    const xDates = ts.length > 0
      ? ts.map((t: number) => fmtDate(new Date(t * 1000)))
      : [fmtDate(new Date((instance.started_at || Date.now() / 1000) * 1000)), fmtDate(new Date())]
    Plotly.newPlot(chartRef.current, [{
      x: xDates, y: curve, type: 'scatter', mode: 'lines',
      line: { color: '#2563eb' }, name: '總資產',
    }], {
      margin: { t: 10, r: 20, b: 40, l: 60 }, height: 200,
      xaxis: { title: '時間' }, yaxis: { title: 'USDT' },
      paper_bgcolor: 'white', plot_bgcolor: 'white',
    }, { responsive: true, displayModeBar: false })
  }, [instance, chartData])

  // per-symbol price charts
  useEffect(() => {
    if (symbolsList.length === 0) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return
    const { prices, trades } = priceChartDataRef.current
    const allTrades = trades || []

    symbolsList.forEach((sym) => {
      const px = prices[sym]
      if (!px) return
      const el = priceRefs.current[sym]
      if (!el) return

      const symTrades = allTrades.filter((t: any) => t.symbol === sym)
      const traces: any[] = [{
        x: px.dates, y: px.values,
        type: 'scatter', mode: 'lines',
        name: sym, line: { color: '#2563eb', width: 1.5 },
      }]

      const buys = symTrades.filter((t: any) => t.side === 'buy')
      const sells = symTrades.filter((t: any) => t.side === 'sell')

      if (buys.length > 0) {
        const buyTimes = buys.map((t: any) => {
          const dt = new Date(t.time * 1000)
          return `${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')} ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`
        })
        traces.push({
          x: buyTimes, y: buys.map((t: any) => t.price),
          type: 'scatter', mode: 'markers', name: '買進',
          marker: { symbol: 'triangle-up', size: 10, color: '#16a34a', line: { color: '#14532d', width: 1 } },
        })
      }
      if (sells.length > 0) {
        const sellTimes = sells.map((t: any) => {
          const dt = new Date(t.time * 1000)
          return `${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')} ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`
        })
        traces.push({
          x: sellTimes, y: sells.map((t: any) => t.price),
          type: 'scatter', mode: 'markers', name: '賣出',
          marker: { symbol: 'triangle-down', size: 10, color: '#dc2626', line: { color: '#7f1d1d', width: 1 } },
        })
      }

      Plotly.newPlot(el, traces, {
        title: { text: `${sym} 價格走勢` },
        margin: { t: 35, r: 20, b: 40, l: 60 }, height: 220,
        xaxis: { title: '時間' }, yaxis: { title: '價格' },
        paper_bgcolor: 'white', plot_bgcolor: 'white',
        legend: { x: 1, xanchor: 'right', y: 1, font: { size: 9 } },
      }, { responsive: true, displayModeBar: false })
    })
  }, [symbolsList, chartData])

  const handleStop = async () => {
    if (!confirm('確定停止？將強制平倉所有持倉。')) return
    await fetch(`/paper-trading/${instanceId}`, { method: 'DELETE' })
    window.location.reload()
  }

  const handleDelete = async () => {
    if (!confirm('確定永久刪除？（所有紀錄將遺失）')) return
    await fetch(`/paper-trading/${instanceId}?purge=true`, { method: 'DELETE' })
    window.location.reload()
  }

  const handleContinue = async () => {
    if (!confirm('重新開始此實例？（將刪除舊紀錄並建立新實例）')) return
    await fetch(`/paper-trading/${instanceId}/continue`, { method: 'PUT' })
    window.location.reload()
  }

  if (!instance) return <div className="text-center py-8 text-gray-400">載入中...</div>

  const tabs = [
    { id: 'monitor' as const, label: '即時監控' },
    { id: 'trades' as const, label: '交易紀錄' },
    { id: 'params' as const, label: '策略參數' },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xl font-bold">{instance.name}</h2>
        <div className="flex gap-2">
          {instance.status === 'STOPPED' && (
            <button onClick={handleContinue}
              className="px-3 py-1.5 text-sm border border-green-200 text-green-600 rounded-lg hover:bg-green-50 cursor-pointer">繼續</button>
          )}
          <button onClick={async () => {
            if (!confirm(`將 "${instance.name}" 複製到實盤跑盤？`)) return
            await fetch('/live-trading/from-paper/' + instance.instance_id, { method: 'POST' })
            window.location.reload()
          }}
            className="px-3 py-1.5 text-sm border border-rose-200 text-rose-600 rounded-lg hover:bg-rose-50 cursor-pointer">轉入實盤</button>
          <button onClick={instance.status === 'STOPPED' ? handleDelete : handleStop}
            className="px-3 py-1.5 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50 cursor-pointer">
            {instance.status === 'STOPPED' ? '刪除' : '停止'}
          </button>
        </div>
      </div>
      <div className="text-sm text-gray-400 mb-4">狀態：{instance.status}</div>

      <div className="grid grid-cols-5 gap-3 mb-4">
        {[
          ['總資產', `${instance.total_equity?.toFixed(2)} USDT`],
          ['總報酬', `${instance.total_return >= 0 ? '+' : ''}${instance.total_return?.toFixed(2)}%`],
          ['已實現損益', `${instance.realized_pnl?.toFixed(2)} USDT`],
          ['交易次數', instance.trade_count],
          ['精度', instance.timeframe || '-'],
        ].map(([k, v]) => (
          <div key={k} className="p-3 border rounded-lg bg-white">
            <div className="text-xs text-gray-400">{k}</div>
            <div className="text-lg font-bold mt-0.5">{v}</div>
          </div>
        ))}
      </div>

      <div className="flex gap-1 mb-4 border-b">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm border-b-2 cursor-pointer ${
              tab === t.id ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500'
            }`}>{t.label}</button>
        ))}
      </div>

      {tab === 'monitor' && (
        <div>
          <div className="space-y-2 mb-4">
            {positions.map((p: any) => (
              <div key={p.symbol} className="flex items-center justify-between p-3 border rounded-lg bg-white">
                <div>
                  <span className="font-medium text-sm">{p.symbol}</span>
                  <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                    p.side === 'long' ? 'bg-green-100 text-green-700' :
                    p.side === 'short' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500'
                  }`}>{p.side === 'long' ? '多' : p.side === 'short' ? '空' : '無'}</span>
                  <span className="ml-2 text-xs text-gray-400">
                    {p.current_price ? `現價 $${typeof p.current_price === 'number' ? p.current_price.toFixed(2) : p.current_price}` : ''}
                  </span>
                  {p.entry_price ? (
                    <span className="ml-2 text-xs text-gray-400">
                      入場 ${typeof p.entry_price === 'number' ? p.entry_price.toFixed(2) : p.entry_price}
                    </span>
                  ) : ''}
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium">
                    {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl?.toFixed(2)} USDT
                  </div>
                  <div className={`text-xs ${(p.unrealized_pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {p.unrealized_pnl_pct?.toFixed(2)}%
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div ref={chartRef} className="w-full border rounded-lg bg-white p-3 mb-3" />
          <div className="space-y-3">
            {symbolsList.map((sym) => (
              <div key={sym} ref={(el) => { priceRefs.current[sym] = el }} className="w-full border rounded-lg bg-white p-3" />
            ))}
          </div>
        </div>
      )}

      {tab === 'trades' && (
        <div className="border rounded-lg bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left p-2 text-xs text-gray-500">時間</th>
                <th className="text-left p-2 text-xs text-gray-500">標的</th>
                <th className="text-left p-2 text-xs text-gray-500">方向</th>
                <th className="text-right p-2 text-xs text-gray-500">價格</th>
                <th className="text-right p-2 text-xs text-gray-500">數量</th>
                <th className="text-right p-2 text-xs text-gray-500">損益</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t: any) => (
                <tr key={t.trade_id} className="border-t">
                  <td className="p-2 text-xs">{new Date(t.executed_time * 1000).toLocaleString()}</td>
                  <td className="p-2 text-xs">{t.symbol}</td>
                  <td className="p-2 text-xs">
                    <span className={`${t.side === 'buy' ? 'text-green-600' : 'text-red-600'}`}>{t.side}</span>
                  </td>
                  <td className="p-2 text-xs text-right">
                    {t.price ? (typeof t.price === 'number' ? t.price.toFixed(2) : t.price) : ''}
                  </td>
                  <td className="p-2 text-xs text-right">{t.quantity?.toFixed(4)}</td>
                  <td className={`p-2 text-xs text-right ${(t.realized_pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {t.realized_pnl ? `${t.realized_pnl >= 0 ? '+' : ''}${t.realized_pnl.toFixed(2)}` : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'params' && (
        <div className="border rounded-lg bg-white p-4">
          <pre className="text-xs font-mono whitespace-pre-wrap">
            {JSON.stringify(
              typeof instance.params_json === 'string'
                ? JSON.parse(instance.params_json)
                : instance.params_json,
              null, 2
            )}
          </pre>
        </div>
      )}
    </div>
  )
}
