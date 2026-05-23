import { useEffect, useState } from 'react'
import { useTaskStore } from '../../store/taskStore'
import type { EvolutionTask } from '../../types/evolution'
import { TaskCard } from './TaskCard'
import { PageLoading } from '../LoadingSpinner'

type Filter = 'all' | 'RUNNING' | 'QUEUED' | 'COMPLETED' | 'FAILED'

export function TaskList() {
  const tasks = useTaskStore((s) => s.tasks)
  const setTasks = useTaskStore((s) => s.setTasks)
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    fetch('/tasks')
      .then((r) => r.json())
      .then((data: EvolutionTask[]) => {
        const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELLED'])
        const current = useTaskStore.getState().tasks
        const terminalById = new Map(
          current.filter((t) => TERMINAL.has(t.status)).map((t) => [t.task_id, t])
        )
        const merged = data.map((t) =>
          TERMINAL.has(t.status) || !terminalById.has(t.task_id) ? t : terminalById.get(t.task_id)!
        )
        setTasks(merged)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const filtered = tasks
    .filter((t) => filter === 'all' || t.status === filter)
    .filter((t) => {
      if (!search.trim()) return true
      const q = search.toLowerCase()
      return (
        (t.name || '').toLowerCase().includes(q) ||
        t.task_id.toLowerCase().includes(q) ||
        t.config.symbols.some((s) => s.toLowerCase().includes(q))
      )
    })

  const counts = {
    all: tasks.length,
    RUNNING: tasks.filter((t) => t.status === 'RUNNING').length,
    QUEUED: tasks.filter((t) => t.status === 'QUEUED').length,
    COMPLETED: tasks.filter((t) => t.status === 'COMPLETED').length,
    FAILED: tasks.filter((t) => t.status === 'FAILED').length,
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {loading && <PageLoading />}
      <h1 className="text-2xl font-bold mb-4">任務隊列</h1>
      <input
        type="search" placeholder="搜尋名稱、標的..."
        value={search} onChange={(e) => setSearch(e.target.value)}
        className="w-full mb-3 px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
      />
      <div className="flex gap-2 mb-4">
        {(Object.entries(counts) as [Filter, number][]).map(([key, count]) => (
          <button key={key} onClick={() => setFilter(key)}
            className={`px-3 py-1.5 text-sm rounded-lg cursor-pointer ${filter === key ? 'bg-blue-600 text-white' : 'bg-gray-100 hover:bg-gray-200'}`}>
            {key === 'all' ? '全部' : key === 'RUNNING' ? '執行中' : key === 'QUEUED' ? '排隊中' : key === 'COMPLETED' ? '已完成' : '失敗'} ({count})
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {filtered.map((t) => <TaskCard key={t.task_id} task={t} onRefresh={load} />)}
      </div>
      {filtered.length === 0 && <div className="text-center py-12 text-gray-400">無符合條件的任務</div>}
    </div>
  )
}
