import { useState, useEffect, useRef } from 'react'
import { X, Search } from 'lucide-react'

interface Props {
  symbols: string[]
  onChange: (symbols: string[]) => void
}

let cache: { label: string; value: string }[] | null = null

export function SymbolInput({ symbols, onChange }: Props) {
  const [input, setInput] = useState('')
  const [suggestions, setSuggestions] = useState<{ label: string; value: string }[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(!cache)
  const [highlightIdx, setHighlightIdx] = useState(-1)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (cache) { setLoading(false); return }
    fetch('https://api.binance.com/api/v3/exchangeInfo')
      .then((r) => r.json())
      .then((data) => {
        cache = (data.symbols as any[])
          .filter((s: any) => s.status === 'TRADING' && s.quoteAsset === 'USDT')
          .map((s: any) => ({ label: `${s.baseAsset}/${s.quoteAsset}`, value: `${s.baseAsset}${s.quoteAsset}` }))
          .sort((a, b) => a.label.localeCompare(b.label))
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (input.length === 0) { setSuggestions([]); setOpen(false); return }
    const q = input.toUpperCase().replace('/', '')
    const matches = cache
      ?.filter((s) => s.value.includes(q))
      .slice(0, 20) ?? []
    setSuggestions(matches)
    setOpen(matches.length > 0)
    setHighlightIdx(-1)
  }, [input])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const add = (val?: string) => {
    const v = (val || input).trim().toUpperCase().replace('/', '')
    if (v && !symbols.includes(v)) onChange([...symbols, v])
    setInput('')
    setOpen(false)
  }

  const remove = (sym: string) => onChange(symbols.filter((s) => s !== sym))

  return (
    <div ref={ref} className="relative">
      <label className="block text-sm font-medium mb-1">回測標的</label>
      <div className="flex flex-wrap gap-1.5 mb-1.5">
        {symbols.map((sym) => (
          <span key={sym} className="flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs">
            {sym}
            <button onClick={() => remove(sym)} className="cursor-pointer"><X className="w-3 h-3" /></button>
          </span>
        ))}
      </div>
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); if (highlightIdx >= 0) add(suggestions[highlightIdx].value); else add() }
            if (e.key === 'ArrowDown') { e.preventDefault(); setHighlightIdx((i) => Math.min(i + 1, suggestions.length - 1)) }
            if (e.key === 'ArrowUp') { e.preventDefault(); setHighlightIdx((i) => Math.max(i - 1, 0)) }
            if (e.key === 'Escape') setOpen(false)
          }}
          onFocus={() => input.length > 0 && suggestions.length > 0 && setOpen(true)}
          placeholder="輸入代號（如 BTC）自動搜尋..."
          className="w-full pl-8 pr-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
        {loading && <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-gray-400">載入中…</div>}
      </div>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border rounded-lg shadow-lg max-h-60 overflow-y-auto">
          {suggestions.map((s, i) => {
            const alreadyAdded = symbols.includes(s.value)
            return (
              <button key={s.value}
                onMouseDown={(e) => { e.preventDefault(); add(s.value) }}
                className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between cursor-pointer ${i === highlightIdx ? 'bg-blue-100' : 'hover:bg-gray-50'} ${alreadyAdded ? 'opacity-40' : ''}`}>
                <span>{s.label}</span>
                {alreadyAdded && <span className="text-xs text-gray-400">已加入</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
