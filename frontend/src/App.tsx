import { useEffect } from 'react'
import { Header } from './components/Layout/Header'
import { Sidebar } from './components/Layout/Sidebar'
import { MainContent } from './components/Layout/MainContent'
import { useTaskStore } from './store/taskStore'

function App() {
  const setTasks = useTaskStore((s) => s.setTasks)

  useEffect(() => {
    const poll = () => {
      fetch('/tasks').then((r) => r.json()).then(setTasks).catch(() => {})
    }
    poll()
    const id = setInterval(poll, 3000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="h-screen flex flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <MainContent />
      </div>
    </div>
  )
}

export default App
