import { useEffect, useState, useRef, useCallback } from 'react'

interface LiveAccount {
  instance_id: string
  name: string
  status: string
  symbols: string | string[]
  initial_capital: number
  total_equity: number
  unrealized_pnl: number
  total_return: number
  schedule_time?: string
  params_json?: string
  trade_count?: number
  win_rate?: number
}

interface Position {
  symbol: string
  side: string
  qty?: number
  market_value?: number
  unrealized_pnl: number
  change_pct?: number
}

interface Order {
  order_id: string
  created_at: number
  symbol: string
  side: string
  qty: number
  filled_qty?: number
  filled_avg_price?: number
  status: string
}

interface FlattenResult {
  symbol: string
  result: string
}

interface Props {
  instanceId: string
}

export function AccountDetail({ instanceId }: Props) {
  const [instance, setInstance] = useState<LiveAccount | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [equityHistory, setEquityHistory] = useState<{ timestamp: number; equity: number }[]>([])
  const [tab, setTab] = useState<'monitor' | 'orders' | 'params'>('monitor')
  const chartRef = useRef<HTMLDivElement>(null)
  const [showOrderForm, setShowOrderForm] = useState(false)
  const [orderSymbol, setOrderSymbol] = useState('')
  const [orderSide, setOrderSide] = useState<'buy' | 'sell'>('buy')
  const [orderQty, setOrderQty] = useState(0)
  const [orderSaving, setOrderSaving] = useState(false)
  const [flattening, setFlattening] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [chartRange, setChartRange] = useState<'1W' | '1M' | '3M' | 'ALL'>('ALL')

  const refreshAll = useCallback(() => {
    setRefreshing(true)
    Promise.allSettled([
      fetch(`/live-trading/${instanceId}`).then((r) => r.json()).then(setInstance).catch(() => {}),
      fetch(`/live-trading/${instanceId}/positions`).then((r) => r.json()).then(setPositions).catch(() => {}),
      fetch(`/live-trading/${instanceId}/orders`).then((r) => r.json()).then(setOrders).catch(() => {}),
    ]).finally(() => setRefreshing(false))
  }, [instanceId])

  const loadEquityHistory = useCallback(() => {
    fetch(`/live-trading/${instanceId}/equity-history`)
      .then((r) => r.json())
      .then(setEquityHistory)
      .catch(() => {})
  }, [instanceId])

  useEffect(() => {
    refreshAll()
    loadEquityHistory()
  }, [refreshAll, loadEquityHistory])

  useEffect(() => {
    if (tab !== 'monitor') return
    const t = setInterval(refreshAll, 15000)
    return () => clearInterval(t)
  }, [tab, refreshAll])

  useEffect(() => {
    if (!chartRef.current) return
    const data = filteredHistory.length > 0 ? filteredHistory : equityHistory
    if (data.length < 2) {
      if (data.length === 1) {
        const Plotly = (window as unknown as Record<string, unknown>).Plotly as
          { newPlot: (el: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config: Record<string, unknown>) => void } | undefined
        if (Plotly) {
          Plotly.newPlot(chartRef.current, [{
            x: [new Date(data[0].timestamp * 1000)], y: [data[0].equity],
            type: 'scatter', mode: 'lines+markers',
            line: { color: '#e11d48' }, name: '總資產',
          }], {
            margin: { t: 10, r: 20, b: 40, l: 60 }, height: 200,
            xaxis: { title: '' }, yaxis: { title: 'USDT' },
            paper_bgcolor: 'white', plot_bgcolor: 'white',
          }, { responsive: true, displayModeBar: false })
        }
      }
      return
    }
    const Plotly = (window as unknown as Record<string, unknown>).Plotly as
      { newPlot: (el: HTMLElement, data: Record<string, unknown>[], layout: Record<string, unknown>, config: Record<string, unknown>) => void } | undefined
    if (!Plotly) return
    Plotly.newPlot(chartRef.current, [{
      x: data.map((e) => new Date(e.timestamp * 1000)),
      y: data.map((e) => e.equity),
      type: 'scatter', mode: 'lines',
      line: { color: '#e11d48' }, name: '總資產',
    }], {
      margin: { t: 10, r: 20, b: 40, l: 60 }, height: 200,
      xaxis: { title: '' }, yaxis: { title: 'USDT' },
      paper_bgcolor: 'white', plot_bgcolor: 'white',
    }, { responsive: true, displayModeBar: false })
  }, [equityHistory, chartRange])

  const filteredHistory = (() => {
    if (chartRange === 'ALL' || equityHistory.length === 0) return equityHistory
    const now = Date.now() / 1000
    const cutoffs: Record<string, number> = { '1W': 604800, '1M': 2592000, '3M': 7776000 }
    const since = now - (cutoffs[chartRange] || 0)
    return equityHistory.filter((e) => e.timestamp >= since)
  })()

  const handleStop = async () => {
    if (!confirm('確定停止？將強制平倉所有持倉。')) return
    await fetch(`/live-trading/${instanceId}`, { method: 'DELETE' })
    window.location.reload()
  }

  const handleDelete = async () => {
    if (!confirm('確定永久刪除？（所有紀錄將遺失）')) return
    await fetch(`/live-trading/${instanceId}?purge=true`, { method: 'DELETE' })
    window.location.reload()
  }

  const handleFlatten = async () => {
    if (!confirm('確定平掉此實例所有 Alpaca 持倉？')) return
    setFlattening(true)
    try {
      const res = await fetch(`/live-trading/${instanceId}/flatten`, { method: 'POST' })
      const data = await res.json()
      if (data.results) {
        alert(data.results.map((r: FlattenResult) => `${r.symbol}: ${r.result}`).join('\n'))
      }
    } catch {
      alert('平倉請求失敗')
    }
    setFlattening(false)
    refreshAll()
  }

  const handleSubmitOrder = async () => {
    if (!orderSymbol || orderQty <= 0) return
    setOrderSaving(true)
    try {
      const res = await fetch(`/live-trading/${instanceId}/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: orderSymbol, side: orderSide, qty: orderQty }),
      })
      if (res.ok) {
        setShowOrderForm(false)
        setOrderSymbol('')
        setOrderQty(0)
        refreshAll()
      } else {
        const err = await res.text()
        alert(`下單失敗: ${err}`)
      }
    } catch {
      alert('下單請求失敗')
    }
    setOrderSaving(false)
  }

  const instanceSymbols: string[] = instance?.symbols
    ? (typeof instance.symbols === 'string' ? JSON.parse(instance.symbols) : instance.symbols)
    : []

  if (!instance) return <div className="text-center py-8 text-gray-400">載入中...</div>

  const orderStatusColor: Record<string, string> = {
    PENDING: 'bg-yellow-100 text-yellow-800',
    SUBMITTED: 'bg-blue-100 text-blue-800',
    FILLED: 'bg-green-100 text-green-800',
    PARTIALLY_FILLED: 'bg-blue-100 text-blue-800',
    CANCELLED: 'bg-gray-100 text-gray-600',
    REJECTED: 'bg-red-100 text-red-800',
    FAILED: 'bg-red-100 text-red-800',
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xl font-bold">{instance.name}</h2>
        <div className="flex gap-2">
          <button onClick={() => setShowOrderForm(true)}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer">
            手動下單
          </button>
          <button onClick={handleFlatten} disabled={flattening}
            className="px-3 py-1.5 text-sm border border-orange-200 text-orange-600 rounded-lg hover:bg-orange-50 disabled:opacity-50 cursor-pointer">
            {flattening ? '平倉中...' : '一鍵平倉'}
          </button>
          <button onClick={instance.status === 'STOPPED' ? handleDelete : handleStop}
            className="px-3 py-1.5 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50 cursor-pointer">
            {instance.status === 'STOPPED' ? '刪除' : '停止'}
          </button>
        </div>
      </div>
      <div className="text-sm text-gray-400 mb-4">
        狀態：{instance.status} · 排程：每日 {instance.schedule_time || '16:30'} {refreshing && <span className="text-blue-500 ml-2">更新中...</span>}
      </div>

      <div className="grid grid-cols-5 gap-3 mb-4">
        {[
          ['總資產', `${instance.total_equity?.toFixed(2)} USDT`],
          ['總報酬', `${instance.total_return >= 0 ? '+' : ''}${instance.total_return?.toFixed(2)}%`],
          ['未實現損益', `${instance.unrealized_pnl >= 0 ? '+' : ''}${instance.unrealized_pnl?.toFixed(2)} USDT`],
          ['交易次數', instance.trade_count],
          ['勝率', instance.win_rate ? `${(instance.win_rate * 100).toFixed(1)}%` : '-'],
        ].map(([k, v]) => (
          <div key={k} className="p-3 border rounded-lg bg-white">
            <div className="text-xs text-gray-400">{k}</div>
            <div className="text-lg font-bold mt-0.5">{v}</div>
          </div>
        ))}
      </div>

      <div className="flex gap-1 mb-4 border-b">
        {['monitor', 'orders', 'params'].map((t) => (
          <button key={t} onClick={() => setTab(t as typeof tab)}
            className={`px-4 py-2 text-sm border-b-2 cursor-pointer ${
              tab === t ? 'border-rose-600 text-rose-700' : 'border-transparent text-gray-500'
            }`}>
            {t === 'monitor' ? '即時監控' : t === 'orders' ? '訂單紀錄' : '策略參數'}
          </button>
        ))}
      </div>

      {tab === 'monitor' && (
        <div>
          <div className="space-y-2 mb-4">
            {positions.length === 0 && (
              <div className="text-center py-6 text-gray-400">目前無持倉</div>
            )}
            {positions.map((p: Position) => (
              <div key={p.symbol} className="flex items-center justify-between p-3 border rounded-lg bg-white">
                <div>
                  <span className="font-medium text-sm">{p.symbol}</span>
                  <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                    p.side === 'long' ? 'bg-green-100 text-green-700' :
                    p.side === 'short' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500'
                  }`}>{p.side === 'long' ? '多' : p.side === 'short' ? '空' : '無'}</span>
                  <span className="ml-2 text-xs text-gray-400">
                    {p.qty ? `數量 ${p.qty}` : ''}
                  </span>
                  {p.market_value ? (
                    <span className="ml-2 text-xs text-gray-400">
                      持有 ${typeof p.market_value === 'number' ? p.market_value.toFixed(2) : p.market_value}
                    </span>
                  ) : ''}
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium">
                    {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl?.toFixed(2)} USDT
                  </div>
                  {p.change_pct !== undefined && (
                    <div className={`text-xs ${p.change_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {p.change_pct >= 0 ? '+' : ''}{p.change_pct?.toFixed(2)}%
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-1 mb-2">
            {(['1W', '1M', '3M', 'ALL'] as const).map((r) => (
              <button key={r} onClick={() => setChartRange(r)}
                className={`px-3 py-1 text-xs rounded cursor-pointer ${
                  chartRange === r ? 'bg-rose-600 text-white' : 'bg-gray-100 hover:bg-gray-200'
                }`}>
                {r === '1W' ? '1 週' : r === '1M' ? '1 月' : r === '3M' ? '3 月' : '全部'}
              </button>
            ))}
          </div>
          <div ref={chartRef} className="w-full border rounded-lg bg-white p-3" />
        </div>
      )}

      {tab === 'orders' && (
        <div className="border rounded-lg bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left p-2 text-xs text-gray-500">時間</th>
                <th className="text-left p-2 text-xs text-gray-500">標的</th>
                <th className="text-left p-2 text-xs text-gray-500">方向</th>
                <th className="text-right p-2 text-xs text-gray-500">數量</th>
                <th className="text-right p-2 text-xs text-gray-500">成交均價</th>
                <th className="text-center p-2 text-xs text-gray-500">狀態</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 && (
                <tr><td colSpan={6} className="text-center py-6 text-gray-400">尚無訂單紀錄</td></tr>
              )}
              {orders.map((o: Order) => (
                <tr key={o.order_id} className="border-t">
                  <td className="p-2 text-xs">{new Date(o.created_at * 1000).toLocaleString()}</td>
                  <td className="p-2 text-xs">{o.symbol}</td>
                  <td className="p-2 text-xs">
                    <span className={o.side === 'buy' ? 'text-green-600' : 'text-red-600'}>{o.side}</span>
                  </td>
                  <td className="p-2 text-xs text-right">{o.qty}{o.filled_qty ? ` (已成交 ${o.filled_qty})` : ''}</td>
                  <td className="p-2 text-xs text-right">{o.filled_avg_price?.toFixed(2) || '-'}</td>
                  <td className="p-2 text-xs text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${orderStatusColor[o.status] || 'bg-gray-100'}`}>
                      {o.status}
                    </span>
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

      {showOrderForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold">手動下單</h3>
            <div>
              <label className="block text-sm font-medium mb-1">標的</label>
              <select value={orderSymbol} onChange={(e) => setOrderSymbol(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none">
                <option value="">選擇標的</option>
                {instanceSymbols.map((sym: string) => (
                  <option key={sym} value={sym}>{sym}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setOrderSide('buy')}
                className={`flex-1 py-2 rounded-lg text-sm cursor-pointer ${
                  orderSide === 'buy' ? 'bg-green-600 text-white' : 'bg-gray-100'
                }`}>買入</button>
              <button onClick={() => setOrderSide('sell')}
                className={`flex-1 py-2 rounded-lg text-sm cursor-pointer ${
                  orderSide === 'sell' ? 'bg-red-600 text-white' : 'bg-gray-100'
                }`}>賣出</button>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">數量</label>
              <input type="number" min={0} step={1} value={orderQty || ''}
                onChange={(e) => setOrderQty(Number(e.target.value))}
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none" />
            </div>
            <div className="flex gap-2 pt-2">
              <button onClick={() => setShowOrderForm(false)}
                className="flex-1 py-2 text-sm border rounded-lg hover:bg-gray-50 cursor-pointer">取消</button>
              <button onClick={handleSubmitOrder} disabled={orderSaving || !orderSymbol || orderQty <= 0}
                className="flex-1 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 cursor-pointer">
                {orderSaving ? '送出中...' : '送出'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
