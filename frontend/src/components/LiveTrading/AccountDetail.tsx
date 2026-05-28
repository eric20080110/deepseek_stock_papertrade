import { useEffect, useState, useRef } from 'react'

interface Props {
  instanceId: string
}

export function AccountDetail({ instanceId }: Props) {
  const [instance, setInstance] = useState<any>(null)
  const [positions, setPositions] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [tab, setTab] = useState<'monitor' | 'orders' | 'params'>('monitor')
  const chartRef = useRef<HTMLDivElement>(null)

  function refreshAll() {
    fetch(`/live-trading/${instanceId}`).then((r) => r.json()).then(setInstance)
    fetch(`/live-trading/${instanceId}/positions`).then((r) => r.json()).then(setPositions)
    fetch(`/live-trading/${instanceId}/orders`).then((r) => r.json()).then(setOrders)
  }

  useEffect(() => {
    refreshAll()
    const t = setInterval(refreshAll, 15000)
    return () => clearInterval(t)
  }, [instanceId])

  useEffect(() => {
    if (!chartRef.current || !instance) return
    const Plotly = (window as any).Plotly
    if (!Plotly) return
    const curve = [instance.initial_capital, instance.total_equity || instance.initial_capital]
    Plotly.newPlot(chartRef.current, [{
      x: ['開始', '目前'], y: curve, type: 'scatter', mode: 'lines',
      line: { color: '#e11d48' }, name: '總資產',
    }], {
      margin: { t: 10, r: 20, b: 40, l: 60 }, height: 200,
      xaxis: { title: '' }, yaxis: { title: 'USDT' },
      paper_bgcolor: 'white', plot_bgcolor: 'white',
    }, { responsive: true, displayModeBar: false })
  }, [instance])

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

  if (!instance) return <div className="text-center py-8 text-gray-400">載入中...</div>

  const orderStatusColor: Record<string, string> = {
    PENDING: 'bg-yellow-100 text-yellow-800',
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
          <button onClick={instance.status === 'STOPPED' ? handleDelete : handleStop}
            className="px-3 py-1.5 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50 cursor-pointer">
            {instance.status === 'STOPPED' ? '刪除' : '停止'}
          </button>
        </div>
      </div>
      <div className="text-sm text-gray-400 mb-4">
        狀態：{instance.status} · 排程：每日 {instance.schedule_time || '16:30'}
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
            {positions.map((p: any) => (
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
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium">
                    {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl?.toFixed(2)} USDT
                  </div>
                </div>
              </div>
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
              {orders.map((o: any) => (
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
    </div>
  )
}
