import { useEffect } from 'react'
import { useTaskStore } from '../../store/taskStore'
import type { ViewType } from '../../types/evolution'
import { Layers, PlusCircle, List, Activity, BarChart3, Gauge, Dna } from 'lucide-react'

const navItems: { id: ViewType; label: string; icon: React.ReactNode }[] = [
  { id: 'strategy', label: '策略管理', icon: <Layers className="w-4 h-4" /> },
  { id: 'new-task', label: '新增任務', icon: <PlusCircle className="w-4 h-4" /> },
  { id: 'queue', label: '任務隊列', icon: <List className="w-4 h-4" /> },
  { id: 'monitor', label: '即時監控', icon: <Activity className="w-4 h-4" /> },
  { id: 'analysis', label: '結果分析', icon: <BarChart3 className="w-4 h-4" /> },
  { id: 'gene-pool', label: '基因庫', icon: <Dna className="w-4 h-4" /> },
  { id: 'paper-trading', label: '模擬跑盤', icon: <Gauge className="w-4 h-4" /> },
]

export function Sidebar() {
  const currentView = useTaskStore((s) => s.currentView)
  const setCurrentView = useTaskStore((s) => s.setCurrentView)
  const tasks = useTaskStore((s) => s.tasks)
  const activeTask = tasks.find((t) => t.status === 'RUNNING')
  const queuedCount = tasks.filter((t) => t.status === 'QUEUED').length

  return (
    <aside className="w-52 bg-white border-r flex flex-col shrink-0">
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setCurrentView(item.id)}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer ${
              currentView === item.id
                ? 'bg-blue-50 text-blue-700 font-medium'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>
      <div className="p-3 border-t text-xs text-gray-400 space-y-1">
        {activeTask && (
          <div>
            <span className="text-blue-600 font-medium">執行中</span>
            <div className="w-full h-1 bg-gray-200 rounded-full mt-1 overflow-hidden">
              <div className="h-full bg-blue-600 rounded-full" style={{ width: `${activeTask.progress_pct}%` }} />
            </div>
          </div>
        )}
        {queuedCount > 0 && <div>排隊中：{queuedCount} 個任務</div>}
        <div>v1.0.0</div>
      </div>
    </aside>
  )
}
