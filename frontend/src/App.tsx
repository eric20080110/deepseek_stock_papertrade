import { useEffect } from 'react'
import { Header } from './components/Layout/Header'
import { Sidebar } from './components/Layout/Sidebar'
import { MainContent } from './components/Layout/MainContent'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastContainer } from './components/ToastContainer'
import { useTaskStore } from './store/taskStore'
import type { EvolutionTask } from './types/evolution'

function App() {
  const setTasks = useTaskStore((s) => s.setTasks)
  const setApiStatus = useTaskStore((s) => s.setApiStatus)

  useEffect(() => {
    const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELLED'])
    const poll = () => {
      fetch('/tasks')
        .then((r) => { if (!r.ok) throw new Error(); return r.json() })
        .then((data) => {
          // Never let a stale RUNNING overwrite a terminal status the WS already set
          const current = useTaskStore.getState().tasks
          const terminalById = new Map(
            current.filter((t) => TERMINAL.has(t.status)).map((t) => [t.task_id, t])
          )
          const merged = (data as EvolutionTask[]).map((t) =>
            TERMINAL.has(t.status) || !terminalById.has(t.task_id) ? t : terminalById.get(t.task_id)!
          )
          setTasks(merged)
          setApiStatus('ok')
        })
        .catch(() => setApiStatus('error'))
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [])

  return (
    <ErrorBoundary>
      <div className="h-screen flex flex-col">
        <Header />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar />
          <MainContent />
        </div>
      </div>
      <ToastContainer />
    </ErrorBoundary>
  )
}

export default App
