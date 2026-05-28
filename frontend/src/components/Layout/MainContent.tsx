import { useTaskStore } from '../../store/taskStore'
import { StrategyPanel } from '../Strategy/StrategyPanel'
import { TaskForm } from '../NewTask/TaskForm'
import { TaskList } from '../TaskQueue/TaskList'
import { MonitorPanel } from '../Monitor/MonitorPanel'
import { AnalysisPanel } from '../Analysis/AnalysisPanel'
import { PaperTradingPanel } from '../PaperTrading/PaperTradingPanel'
import { LiveTradingPanel } from '../LiveTrading/LiveTradingPanel'
import { GenePoolPanel } from '../GenePool/GenePoolPanel'

export function MainContent() {
  const currentView = useTaskStore((s) => s.currentView)

  const views: Record<string, React.ReactNode> = {
    strategy: <StrategyPanel />,
    'new-task': <TaskForm />,
    queue: <TaskList />,
    monitor: <MonitorPanel />,
    analysis: <AnalysisPanel />,
    'paper-trading': <PaperTradingPanel />,
    'live-trading': <LiveTradingPanel />,
    'gene-pool': <GenePoolPanel />,
  }

  return (
    <main className="flex-1 overflow-y-auto bg-gray-50">
      {views[currentView] || views.queue}
    </main>
  )
}
