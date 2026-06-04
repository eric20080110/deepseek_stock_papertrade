import { useEffect, useState } from 'react'
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'

interface RankingItem {
  strategy_id: string
  task_id: string
  task_name: string
  generation: number
  cagr: number
  max_drawdown: number
  sharpe_ratio: number
  profit_factor: number
  win_rate: number
  oos_consistency_score: number | null
  trade_count: number
  symbols: string[]
  timeframe: string
}

type SortKey = 'cagr' | 'sharpe_ratio' | 'max_drawdown'
type SortDir = 'asc' | 'desc'

export function ChampionRanking() {
  const [data, setData] = useState<RankingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>('cagr')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  useEffect(() => {
    fetch('/gene-pool/ranking')
      .then((r) => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }, [])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = [...data].sort((a, b) => {
    const av = a[sortKey] ?? 0
    const bv = b[sortKey] ?? 0
    return sortDir === 'desc' ? bv - av : av - bv
  })

  const SortIcon = ({ k }: { k: SortKey }) => {
    if (sortKey !== k) return <ArrowUpDown className="w-3 h-3 inline-block ml-1 text-gray-300" />
    return sortDir === 'desc'
      ? <ArrowDown className="w-3 h-3 inline-block ml-1 text-blue-600" />
      : <ArrowUp className="w-3 h-3 inline-block ml-1 text-blue-600" />
  }

  const rankColor = (i: number) => {
    if (i === 0) return 'bg-yellow-50 border-yellow-300'
    if (i === 1) return 'bg-gray-50 border-gray-300'
    if (i === 2) return 'bg-orange-50 border-orange-300'
    return ''
  }

  const rankMedal = (i: number) => {
    if (i === 0) return <span className="font-bold text-yellow-600">🥇</span>
    if (i === 1) return <span className="font-bold text-gray-500">🥈</span>
    if (i === 2) return <span className="font-bold text-orange-600">🥉</span>
    return <span className="text-gray-400">{i + 1}</span>
  }

  if (loading) {
    return <div className="text-center py-12 text-gray-400">載入中...</div>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wider">
            <th className="px-3 py-2 text-left w-10">#</th>
            <th className="px-3 py-2 text-left">策略 ID</th>
            <th className="px-3 py-2 text-left">任務名稱</th>
            <th className="px-3 py-2 text-left">標的</th>
            <th className="px-3 py-2 text-left">框架</th>
            <th className="px-3 py-2 text-right cursor-pointer select-none" onClick={() => toggleSort('cagr')}>
              CAGR % <SortIcon k="cagr" />
            </th>
            <th className="px-3 py-2 text-right cursor-pointer select-none" onClick={() => toggleSort('sharpe_ratio')}>
              Sharpe <SortIcon k="sharpe_ratio" />
            </th>
            <th className="px-3 py-2 text-right cursor-pointer select-none" onClick={() => toggleSort('max_drawdown')}>
              最大回撤 % <SortIcon k="max_drawdown" />
            </th>
            <th className="px-3 py-2 text-right">勝率 %</th>
            <th className="px-3 py-2 text-right">交易次數</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((item, i) => (
            <tr key={item.strategy_id} className={`border-t border-l border-r ${rankColor(i)} hover:bg-blue-50/50`}>
              <td className="px-3 py-2 text-center">{rankMedal(i)}</td>
              <td className="px-3 py-2 font-mono text-xs text-gray-500">{item.strategy_id.slice(0, 8)}...</td>
              <td className="px-3 py-2 font-medium">{item.task_name}</td>
              <td className="px-3 py-2 text-xs text-gray-600">{item.symbols.join(', ')}</td>
              <td className="px-3 py-2 text-xs text-gray-600">{item.timeframe}</td>
              <td className={`px-3 py-2 text-right font-mono font-semibold ${(item.cagr ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {((item.cagr ?? 0) * 100).toFixed(1)}%
              </td>
              <td className="px-3 py-2 text-right font-mono">{(item.sharpe_ratio ?? 0).toFixed(2)}</td>
              <td className="px-3 py-2 text-right font-mono text-orange-600">{(item.max_drawdown ?? 0).toFixed(1)}%</td>
              <td className="px-3 py-2 text-right font-mono">{(item.win_rate ?? 0).toFixed(0)}%</td>
              <td className="px-3 py-2 text-right font-mono text-gray-500">{item.trade_count ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length === 0 && (
        <div className="text-center py-12 text-gray-400">尚無跨任務排名數據</div>
      )}
    </div>
  )
}
