import { useState } from 'react'
import type { StrategyConfig } from '../../types/strategy'
import { StrategyCard } from './StrategyCard'

interface Props {
  strategies: StrategyConfig[]
  loading: boolean
  onEdit: (s: StrategyConfig) => void
  onRefresh: () => void
  onUseStrategy?: (s: StrategyConfig) => void
  onCreateFromTemplate?: (s: StrategyConfig) => void
}

type Filter = 'all' | 'templates' | 'user'

export function StrategyList({ strategies, loading, onEdit, onRefresh, onUseStrategy, onCreateFromTemplate }: Props) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')

  const filtered = strategies.filter((s) => {
    if (filter === 'templates' && !s.is_template) return false
    if (filter === 'user' && s.is_template) return false
    if (search && !s.name.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  if (loading) {
    return <div className="text-center py-12 text-gray-400">載入中...</div>
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <input
          type="text"
          placeholder="搜尋策略名稱..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div className="flex gap-1">
          {(['all', 'templates', 'user'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-sm rounded-lg cursor-pointer ${
                filter === f ? 'bg-blue-600 text-white' : 'bg-gray-100 hover:bg-gray-200'
              }`}
            >
              {f === 'all' ? '全部' : f === 'templates' ? '系統模板' : '我的策略'}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((s) => (
          <StrategyCard key={s.config_id} strategy={s} onEdit={onEdit} onRefresh={onRefresh} onUseStrategy={onUseStrategy} onCreateFromTemplate={onCreateFromTemplate} />
        ))}
      </div>
      {filtered.length === 0 && (
        <div className="text-center py-12 text-gray-400">無符合條件的策略</div>
      )}
    </div>
  )
}
