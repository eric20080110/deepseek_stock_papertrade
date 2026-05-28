import { useState, useEffect } from 'react'
import { useTaskStore } from '../../store/taskStore'

export function CreateAccountForm() {
  const [name, setName] = useState('')
  const [strategyId, setStrategyId] = useState('')
  const [strategies, setStrategies] = useState<any[]>([])
  const [symbolInput, setSymbolInput] = useState('')
  const [symbols, setSymbols] = useState<string[]>([])
  const [capital, setCapital] = useState(10000)
  const [timeframe, setTimeframe] = useState('1d')
  const [scheduleTime, setScheduleTime] = useState('16:30')
  const [saving, setSaving] = useState(false)
  const [params, setParams] = useState<Record<string, string>>({})
  const [isRotation, setIsRotation] = useState(false)
  const [rotationSymbols, setRotationSymbols] = useState<string[]>([])
  const [maxDailyLoss, setMaxDailyLoss] = useState<string>('')
  const [maxPositionSize, setMaxPositionSize] = useState<string>('')

  useEffect(() => {
    fetch('/strategies')
      .then((r) => r.json())
      .then((data: any[]) => setStrategies(data.filter((s) => !s.is_template)))
  }, [])

  useEffect(() => {
    if (strategyId) {
      fetch(`/strategies/${strategyId}`)
        .then((r) => r.json())
        .then((s: any) => {
          const defaults: Record<string, string> = {}
          for (const p of s.parameters) {
            defaults[p.name] = String(p.default ?? '')
          }
          setParams(defaults)
          setIsRotation(s.is_rotation ?? false)
          setRotationSymbols(s.rotation_symbols ?? [])
          if (s.is_rotation) setTimeframe('1d')
        })
    } else {
      setIsRotation(false)
      setRotationSymbols([])
    }
  }, [strategyId])

  const addSymbol = () => {
    const v = symbolInput.trim().toUpperCase()
    if (v && !symbols.includes(v)) setSymbols([...symbols, v])
    setSymbolInput('')
  }

  const handleSubmit = async () => {
    if (!name || !strategyId || (!isRotation && symbols.length === 0)) return
    setSaving(true)
    try {
      const parsedParams: Record<string, any> = {}
      for (const [k, v] of Object.entries(params)) {
        const num = Number(v)
        parsedParams[k] = isNaN(num) ? v : num
      }
      await fetch('/live-trading', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name, strategy_config_id: strategyId, params: parsedParams,
          symbols: isRotation ? [] : symbols, initial_capital: capital,
          timeframe, schedule_time: scheduleTime,
          max_daily_loss_pct: maxDailyLoss ? parseFloat(maxDailyLoss) : undefined,
          max_position_size_pct: maxPositionSize ? parseFloat(maxPositionSize) : undefined,
        }),
      })
      useTaskStore.getState().setCurrentView('paper-trading')
      window.location.reload()
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  const valid = name && strategyId && (isRotation || symbols.length > 0)

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <h2 className="text-lg font-semibold text-rose-700">新增實盤實例</h2>

      <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg">
        <div className="text-sm font-medium text-rose-800">⚠️ 實盤交易使用真實資金</div>
        <div className="text-xs text-rose-600 mt-1">請仔細確認策略參數、標的與風險控制設定後再啟動。</div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">實例名稱</label>
        <input value={name} onChange={(e) => setName(e.target.value)}
          className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-rose-500" />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">策略</label>
        <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}
          className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-rose-500">
          <option value="">選擇策略...</option>
          {strategies.map((s: any) => <option key={s.config_id} value={s.config_id}>{s.name}</option>)}
        </select>
      </div>

      {Object.keys(params).length > 0 && (
        <div>
          <label className="block text-sm font-medium mb-1">參數設定</label>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(params).map(([k, v]) => (
              <div key={k}>
                <span className="text-xs text-gray-500 font-mono">{k}</span>
                <input value={v} onChange={(e) => setParams({ ...params, [k]: e.target.value })}
                  className="w-full px-2 py-1 border rounded text-xs outline-none focus:ring-1 focus:ring-rose-500" />
              </div>
            ))}
          </div>
        </div>
      )}

      {isRotation ? (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="text-sm font-medium text-blue-800 mb-1">固定輪換標的（自動套用）</div>
          <div className="flex flex-wrap gap-1.5">
            {rotationSymbols.map((s) => (
              <span key={s} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-mono">{s}</span>
            ))}
          </div>
        </div>
      ) : (
        <div>
          <label className="block text-sm font-medium mb-1">監控標的</label>
          <div className="flex flex-wrap gap-1.5 mb-1.5">
            {symbols.map((s) => (
              <span key={s} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs">
                {s}
                <button onClick={() => setSymbols(symbols.filter((x) => x !== s))} className="ml-1 cursor-pointer">×</button>
              </span>
            ))}
          </div>
          <input value={symbolInput} onChange={(e) => setSymbolInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addSymbol())}
            placeholder="輸入代號按 Enter 加入" className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-rose-500" />
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">初始資金 (USDT)</label>
          <input type="number" min={1000} max={1000000} value={capital} onChange={(e) => setCapital(+e.target.value)}
            className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-rose-500" />
        </div>
        <div>
          {isRotation ? (
            <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-500">
              K 線週期：日 K（輪換策略固定使用日線）
            </div>
          ) : (
            <>
              <label className="block text-sm font-medium mb-1">K 線週期</label>
              <div className="flex gap-2 flex-wrap">
                {['1d', '1h', '30m', '15m', '5m', '1m'].map((v) => (
                  <button key={v} onClick={() => setTimeframe(v)}
                    className={`px-3 py-1.5 text-sm rounded-lg cursor-pointer ${timeframe === v ? 'bg-rose-600 text-white' : 'bg-gray-100'}`}>
                    {({'1d':'日 K','1h':'小時 K','30m':'30分','15m':'15分','5m':'5分','1m':'1分'} as Record<string,string>)[v] || v}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">每日執行時間</label>
        <input type="time" value={scheduleTime} onChange={(e) => setScheduleTime(e.target.value)}
          className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-rose-500" />
        <div className="text-xs text-gray-400 mt-1">每日收盤後執行策略、生成訂單（預設 16:30）</div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">最大單日虧損 (%)</label>
          <input type="number" min={0} max={100} step={0.1} value={maxDailyLoss}
            onChange={(e) => setMaxDailyLoss(e.target.value)}
            placeholder="選填" className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-rose-500" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">最大倉位比例 (%)</label>
          <input type="number" min={0} max={100} step={1} value={maxPositionSize}
            onChange={(e) => setMaxPositionSize(e.target.value)}
            placeholder="選填" className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-rose-500" />
        </div>
      </div>

      <button onClick={handleSubmit} disabled={!valid || saving}
        className="px-6 py-2.5 bg-rose-600 text-white rounded-lg hover:bg-rose-700 disabled:opacity-50 cursor-pointer">
        {saving ? '建立中...' : '啟動實盤'}
      </button>
    </div>
  )
}
