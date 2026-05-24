import { useState, useEffect } from 'react'
import { useTaskStore } from '../../store/taskStore'

export function CreateInstanceForm() {
  const [name, setName] = useState('')
  const [strategyId, setStrategyId] = useState('')
  const [strategies, setStrategies] = useState<any[]>([])
  const [symbolInput, setSymbolInput] = useState('')
  const [symbols, setSymbols] = useState<string[]>([])
  const [capital, setCapital] = useState(10000)
  const [timeframe, setTimeframe] = useState('1d')
  const [saving, setSaving] = useState(false)
  const [params, setParams] = useState<Record<string, string>>({})
  const [isRotation, setIsRotation] = useState(false)
  const [rotationSymbols, setRotationSymbols] = useState<string[]>([])

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
      await fetch('/paper-trading', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name, strategy_config_id: strategyId, params: parsedParams,
          symbols: isRotation ? [] : symbols, initial_capital: capital, timeframe,
        }),
      })
      useTaskStore.getState().setCurrentView('analysis')
      window.location.reload()
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  const valid = name && strategyId && (isRotation || symbols.length > 0)

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <h2 className="text-lg font-semibold">新增模擬實例</h2>

      <div>
        <label className="block text-sm font-medium mb-1">實例名稱</label>
        <input value={name} onChange={(e) => setName(e.target.value)}
          className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">策略</label>
        <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}
          className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500">
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
                  className="w-full px-2 py-1 border rounded text-xs outline-none focus:ring-1 focus:ring-blue-500" />
              </div>
            ))}
          </div>
        </div>
      )}

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
            placeholder="輸入代號按 Enter 加入" className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">每標的資金 (USDT)</label>
          <input type="number" min={1000} max={1000000} value={capital} onChange={(e) => setCapital(+e.target.value)}
            className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">K 線週期</label>
          <div className="flex gap-2 flex-wrap">
            {['1d', '1h', '30m', '15m', '5m', '1m'].map((v) => (
              <button key={v} onClick={() => setTimeframe(v)}
                className={`px-3 py-1.5 text-sm rounded-lg cursor-pointer ${timeframe === v ? 'bg-blue-600 text-white' : 'bg-gray-100'}`}>
                {{'1d':'日 K','1h':'小時 K','30m':'30分','15m':'15分','5m':'5分','1m':'1分'}[v] || v}
              </button>
            ))}
          </div>
        </div>
      </div>

      <button onClick={handleSubmit} disabled={!valid || saving}
        className="px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 cursor-pointer">
        {saving ? '建立中...' : '啟動模擬'}
      </button>
    </div>
  )
}
