import { useEffect, useState, useCallback } from 'react'
import { ChevronDown, ChevronRight, Zap, Star, Pencil, Check, X, Trash2, Eye } from 'lucide-react'
import { useTaskStore } from '../../store/taskStore'
import { ChampionDetailDrawer } from './ChampionDetailDrawer'
import { PageLoading } from '../LoadingSpinner'

interface Champion {
  sid: string
  strategy_id: string
  generation: number
  idx: number
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
  task_name: string
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
  const [loading, setLoading] = useState(true)
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [expandedStrategies, setExpandedStrategies] = useState<Set<string>>(new Set())
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set())
  const [editingName, setEditingName] = useState<Record<string, boolean>>({})
  const [draftNames, setDraftNames] = useState<Record<string, string>>({})
  const [detailChampion, setDetailChampion] = useState<{ taskId: string; sid: string } | null>(null)
  const [editingTaskName, setEditingTaskName] = useState<Record<string, boolean>>({})
  const [draftTaskNames, setDraftTaskNames] = useState<Record<string, string>>({})

  const setCurrentView = useTaskStore((s) => s.setCurrentView)

  const load = useCallback(() => {
    setLoading(true)
    fetch(`/gene-pool${favoritesOnly ? '?favorites_only=true' : ''}`)
      .then((r) => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }, [favoritesOnly])

  useEffect(() => { load() }, [load])

  const toggleFavorite = (sid: string, current: boolean) => {
    setData((prev) => prev.map((s) => ({
      ...s,
      tasks: (s.tasks || []).map((t) => ({
        ...t,
        champions: t.champions.map((c) =>
          c.sid === sid ? { ...c, is_favorite: !current } : c
        ),
      })),
    })))
    fetch(`/gene-pool/${sid}/favorite`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_favorite: !current }),
    })
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

  const confirmTaskRename = async (taskId: string) => {
    const name = draftTaskNames[taskId]?.trim()
    if (name) {
      await fetch(`/gene-pool/tasks/${taskId}/rename`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      setData((prev) => prev.map((s) => ({
        ...s,
        tasks: s.tasks.map((t) =>
          t.task_id === taskId ? { ...t, task_name: name } : t
        ),
      })))
    }
    setEditingTaskName((prev) => ({ ...prev, [taskId]: false }))
  }

  const deleteChampion = async (sid: string) => {
    if (!confirm('確定移除此基因？')) return
    await fetch(`/gene-pool/${sid}`, { method: 'DELETE' })
    load()
  }

  const deployPT = async (c: Champion, task: GeneTask) => {
    try {
      const params = JSON.parse(c.params_json || '{}')
      const res = await fetch('/paper-trading', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: c.custom_name || `${task.task_name}-G${c.generation}-${c.idx}`,
          source: 'evolution',
          source_task_id: task.task_id,
          source_individual_id: c.sid,
          strategy_config_id: c.strategy_id,
          params,
          symbols: task.symbols,
          initial_capital: 10000,
          timeframe: task.timeframe,
        }),
      })
      if (res.ok) {
        alert('已部署至模擬跑盤！')
        setCurrentView('paper-trading')
      } else {
        const errBody = await res.text()
        alert(`部署失敗 (${res.status}): ${errBody}`)
      }
    } catch (e) {
      console.error(e)
      alert('部署失敗: ' + String(e))
    }
  }

  const totalChampions = data.reduce((a, s) => a + (s.tasks || []).reduce((b, t) => b + (t.champions || []).length, 0), 0)

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

  if (loading) return <PageLoading label="載入基因庫中..." />

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

              {isExpanded && (strategy.tasks || []).map((task) => {
                const tExpanded = expandedTasks.has(task.task_id)
                return (
                  <div key={task.task_id}>
                    <button onClick={() => toggleTask(task.task_id)}
                      className="w-full flex items-center justify-between px-6 py-2 hover:bg-gray-50 cursor-pointer border-t">
                      <div className="flex items-center gap-2 text-sm flex-1 min-w-0">
                        {tExpanded ? <ChevronDown className="w-3 h-3 text-gray-400 shrink-0" /> : <ChevronRight className="w-3 h-3 text-gray-400 shrink-0" />}
                        <div className="flex items-center gap-1 min-w-0" onClick={(e) => e.stopPropagation()}>
                          {editingTaskName[task.task_id] ? (
                            <div className="flex items-center gap-1">
                              <input type="text" value={draftTaskNames[task.task_id] || ''}
                                onChange={(e) => setDraftTaskNames((prev) => ({ ...prev, [task.task_id]: e.target.value }))}
                                onKeyDown={(e) => e.key === 'Enter' && confirmTaskRename(task.task_id)}
                                className="w-28 px-1 py-0.5 text-xs border rounded" />
                              <button onClick={() => confirmTaskRename(task.task_id)} className="cursor-pointer">
                                <Check className="w-3 h-3 text-green-600" />
                              </button>
                              <button onClick={() => setEditingTaskName((prev) => ({ ...prev, [task.task_id]: false }))} className="cursor-pointer">
                                <X className="w-3 h-3 text-red-500" />
                              </button>
                            </div>
                          ) : (
                            <>
                              <span className="text-gray-700 font-medium truncate">{task.task_name}</span>
                              <button onClick={() => {
                                setEditingTaskName((prev) => ({ ...prev, [task.task_id]: true }))
                                setDraftTaskNames((prev) => ({ ...prev, [task.task_id]: task.task_name }))
                              }} className="cursor-pointer">
                                <Pencil className="w-3 h-3 text-gray-400 hover:text-gray-600 shrink-0" />
                              </button>
                            </>
                          )}
                        </div>
                        <span className="text-xs text-gray-400 shrink-0">{task.symbols.join(', ')}</span>
                        <span className="text-xs text-gray-400 shrink-0">{task.timeframe}</span>
                        <span className="text-xs text-gray-400 shrink-0">G{task.current_generation}/{task.total_generations}</span>
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
                        {(task.champions || []).map((c) => (
                          <div key={c.sid} className="grid grid-cols-8 gap-2 px-6 py-2 text-sm border-t hover:bg-gray-50 items-center">
                            <div className="col-span-2 flex items-center gap-1">
                              {editingName[c.sid] ? (
                                <div className="flex items-center gap-1">
                                  <input type="text" value={draftNames[c.sid] || ''}
                                    onChange={(e) => setDraftNames((prev) => ({ ...prev, [c.sid]: e.target.value }))}
                                    onKeyDown={(e) => e.key === 'Enter' && confirmRename(c.sid)}
                                    className="w-20 px-1 py-0.5 text-xs border rounded" />
                                  <button onClick={() => confirmRename(c.sid)} className="cursor-pointer"><Check className="w-3 h-3 text-green-600" /></button>
                                  <button onClick={() => setEditingName((prev) => ({ ...prev, [c.sid]: false }))} className="cursor-pointer"><X className="w-3 h-3 text-red-500" /></button>
                                </div>
                              ) : (
                                <>
                                  <span className="text-xs font-mono">{c.custom_name || `${task.task_name}-G${c.generation}-${c.idx}`}</span>
                                  <button onClick={() => startRename(c.sid, c.custom_name || '')} className="cursor-pointer">
                                    <Pencil className="w-3 h-3 text-gray-400 hover:text-gray-600" />
                                  </button>
                                </>
                              )}
                              <button onClick={() => toggleFavorite(c.sid, !!c.is_favorite)} className="cursor-pointer">
                                <Star className={`w-3 h-3 ${c.is_favorite ? 'text-yellow-500 fill-yellow-500' : 'text-gray-300'}`} />
                              </button>
                            </div>
                            <span className="text-green-600 font-mono text-xs">+{((c.cagr ?? 0) * 100).toFixed(0)}%</span>
                            <span className="font-mono text-xs">{(c.sharpe_ratio ?? 0).toFixed(2)}</span>
                            <span className="text-orange-600 font-mono text-xs">{(c.max_drawdown ?? 0).toFixed(1)}%</span>
                            <span className="font-mono text-xs">{(c.win_rate ?? 0).toFixed(0)}%</span>
                            <span className="text-xs text-gray-500 truncate font-mono">
                              {(() => {
                                try {
                                  const p = JSON.parse(c.params_json || '{}')
                                  return Object.entries(p).slice(0, 2).map(([k, v]) => `${k}:${v}`).join(' ')
                                } catch { return '' }
                              })()}
                            </span>
                            <div className="flex gap-1">
                              <button onClick={() => setDetailChampion({ taskId: task.task_id, sid: c.sid })}
                                className="px-2 py-0.5 text-xs border border-gray-200 text-gray-600 rounded hover:bg-gray-50 cursor-pointer">
                                <Eye className="w-3 h-3 inline-block" />
                              </button>
                              <button onClick={() => deployPT(c, task)}
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

      {detailChampion && (
        <ChampionDetailDrawer
          taskId={detailChampion.taskId}
          sid={detailChampion.sid}
          onClose={() => setDetailChampion(null)}
        />
      )}
    </div>
  )
}
