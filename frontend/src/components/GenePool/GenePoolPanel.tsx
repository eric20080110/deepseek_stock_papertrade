import { useEffect, useState, useCallback } from 'react'
import { ChevronDown, ChevronRight, Zap, Star, Pencil, Check, X, Trash2 } from 'lucide-react'
import { useTaskStore } from '../../store/taskStore'

interface Champion {
  sid: string
  strategy_id: string
  generation: number
  cagr: number
  max_drawdown: number
  sharpe_ratio: number
  profit_factor: number
  win_rate: number
  trade_count: number
  oos_consistency_score: number | null
  params_json: string
  is_favorite?: boolean
  custom_name?: string
}

interface GeneTask {
  task_id: string
  current_generation: number
  total_generations: number
  completed_at: number | null
  symbols: string[]
  timeframe: string
  champions: Champion[]
}

interface GeneStrategy {
  config_id: string
  name: string
  template_id: string | null
  is_template: boolean
  tasks: GeneTask[]
}

export function GenePoolPanel() {
  const [data, setData] = useState<GeneStrategy[]>([])
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [expandedStrategies, setExpandedStrategies] = useState<Set<string>>(new Set())
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set())
  const [editingName, setEditingName] = useState<Record<string, boolean>>({})
  const [draftNames, setDraftNames] = useState<Record<string, string>>({})

  const setCurrentView = useTaskStore((s) => s.setCurrentView)

  const load = useCallback(() => {
    fetch(`/gene-pool${favoritesOnly ? '?favorites_only=true' : ''}`).then((r) => r.json()).then(setData)
  }, [favoritesOnly])

  useEffect(() => { load() }, [load])

  const toggleFavorite = async (sid: string, current: boolean) => {
    await fetch(`/gene-pool/${sid}/favorite`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_favorite: !current }),
    })
    load()
  }

  const startRename = (sid: string, currentName: string) => {
    setEditingName((prev) => ({ ...prev, [sid]: true }))
    setDraftNames((prev) => ({ ...prev, [sid]: currentName }))
  }

  const confirmRename = async (sid: string) => {
    const name = draftNames[sid] || ''
    if (name.trim()) {
      await fetch(`/gene-pool/${sid}/rename`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ custom_name: name.trim() }),
      })
      load()
    }
    setEditingName((prev) => ({ ...prev, [sid]: false }))
  }

  const deleteChampion = async (sid: string) => {
    if (!confirm('確定移除此基因？')) return
    await fetch(`/gene-pool/${sid}`, { method: 'DELETE' })
    load()
  }

  const deployPT = async (c: Champion) => {
    try {
      const params = JSON.parse(c.params_json || '{}')
      const res = await fetch('/paper-trading', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy_id: c.strategy_id,
          symbol: c.sid?.split('-')[0] || 'BTCUSDT',
          capital: 10000,
          params_json: JSON.stringify(params),
        }),
      })
      if (res.ok) { alert('已部署至模擬跑盤！'); setCurrentView('paper-trading') }
    } catch (e) { console.error(e) }
  }

  const totalChampions = data.reduce((a, s) => a + s.tasks.reduce((b, t) => b + t.champions.length, 0), 0)

  const toggleStrategy = (id: string) => {
    setExpandedStrategies((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const toggleTask = (id: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">基因庫</h1>
        <span className="text-sm text-gray-400">共 {totalChampions} 個冠軍個體</span>
      </div>

      <div className="flex items-center gap-2 mb-4">
        <button onClick={() => setFavoritesOnly(false)}
          className={`px-3 py-1.5 text-sm rounded-lg cursor-pointer ${!favoritesOnly ? 'bg-blue-600 text-white' : 'bg-gray-100 hover:bg-gray-200'}`}>
          全部 ({totalChampions})
        </button>
        <button onClick={() => setFavoritesOnly(true)}
          className={`px-3 py-1.5 text-sm rounded-lg cursor-pointer ${favoritesOnly ? 'bg-blue-600 text-white' : 'bg-gray-100 hover:bg-gray-200'}`}>
          ★ 標記
        </button>
      </div>

      <div className="space-y-4">
        {data.map((strategy) => {
          const isExpanded = expandedStrategies.has(strategy.config_id)
          const taskChamps = strategy.tasks.reduce((a, t) => a + t.champions.length, 0)

          return (
            <div key={strategy.config_id} className="border rounded-lg bg-white overflow-hidden">
              <button onClick={() => toggleStrategy(strategy.config_id)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 cursor-pointer">
                <div className="flex items-center gap-2">
                  {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                  <span className="font-semibold">{strategy.name}</span>
                  <span className="text-xs text-gray-400">{taskChamps} 個</span>
                </div>
              </button>

              {isExpanded && strategy.tasks.map((task) => {
                const tExpanded = expandedTasks.has(task.task_id)
                return (
                  <div key={task.task_id}>
                    <button onClick={() => toggleTask(task.task_id)}
                      className="w-full flex items-center justify-between px-6 py-2 hover:bg-gray-50 cursor-pointer border-t">
                      <div className="flex items-center gap-2 text-sm">
                        {tExpanded ? <ChevronDown className="w-3 h-3 text-gray-400" /> : <ChevronRight className="w-3 h-3 text-gray-400" />}
                        <span className="text-gray-700">{task.symbols.join(', ')}</span>
                        <span className="text-xs text-gray-400">{task.timeframe}</span>
                        <span className="text-xs text-gray-400">G{task.current_generation}/{task.total_generations}</span>
                      </div>
                    </button>

                    {tExpanded && (
                      <div className="border-t">
                        <div className="grid grid-cols-8 gap-2 px-6 py-2 text-xs text-gray-400 bg-gray-50 font-medium">
                          <span className="col-span-2">個體</span>
                          <span>CAGR</span>
                          <span>Sharpe</span>
                          <span>|DD|</span>
                          <span>勝率</span>
                          <span>參數</span>
                          <span>操作</span>
                        </div>
                        {task.champions.map((c) => (
                          <div key={c.sid} className="grid grid-cols-8 gap-2 px-6 py-2 text-sm border-t hover:bg-gray-50 items-center">
                            <div className="col-span-2 flex items-center gap-1">
                              {editingName[c.sid] ? (
                                <div className="flex items-center gap-1">
                                  <input type="text" value={draftNames[c.sid] || ''}
                                    onChange={(e) => setDraftNames((prev) => ({ ...prev, [c.sid]: e.target.value }))}
                                    className="w-20 px-1 py-0.5 text-xs border rounded" />
                                  <button onClick={() => confirmRename(c.sid)} className="cursor-pointer"><Check className="w-3 h-3 text-green-600" /></button>
                                  <button onClick={() => setEditingName((prev) => ({ ...prev, [c.sid]: false }))} className="cursor-pointer"><X className="w-3 h-3 text-red-500" /></button>
                                </div>
                              ) : (
                                <>
                                  <span className="text-xs font-mono">{c.custom_name || c.sid.slice(0, 10)}</span>
                                  <button onClick={() => startRename(c.sid, c.custom_name || '')} className="cursor-pointer">
                                    <Pencil className="w-3 h-3 text-gray-400 hover:text-gray-600" />
                                  </button>
                                </>
                              )}
                              <button onClick={() => toggleFavorite(c.sid, !!c.is_favorite)} className="cursor-pointer">
                                <Star className={`w-3 h-3 ${c.is_favorite ? 'text-yellow-500 fill-yellow-500' : 'text-gray-300'}`} />
                              </button>
                            </div>
                            <span className="text-green-600 font-mono text-xs">+{(c.cagr * 100).toFixed(0)}%</span>
                            <span className="font-mono text-xs">{c.sharpe_ratio.toFixed(2)}</span>
                            <span className="text-orange-600 font-mono text-xs">{c.max_drawdown.toFixed(1)}%</span>
                            <span className="font-mono text-xs">{(c.win_rate * 100).toFixed(0)}%</span>
                            <span className="text-xs text-gray-500 truncate font-mono">
                              {(() => {
                                try {
                                  const p = JSON.parse(c.params_json || '{}')
                                  return Object.entries(p).slice(0, 2).map(([k, v]) => `${k}:${v}`).join(' ')
                                } catch { return '' }
                              })()}
                            </span>
                            <div className="flex gap-1">
                              <button onClick={() => deployPT(c)}
                                className="px-2 py-0.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 cursor-pointer">
                                <Zap className="w-3 h-3 inline-block" /> 跑盤
                              </button>
                              <button onClick={() => deleteChampion(c.sid)}
                                className="px-2 py-0.5 text-xs border border-red-200 text-red-600 rounded hover:bg-red-50 cursor-pointer">
                                <Trash2 className="w-3 h-3 inline-block" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )
        })}
        {data.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            尚無冠軍基因，請先完成演化任務
          </div>
        )}
      </div>
    </div>
  )
}
