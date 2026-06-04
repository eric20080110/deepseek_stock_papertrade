import { useEffect, useRef } from 'react'
import { useTaskStore } from '../store/taskStore'
import { toast } from '../lib/toast'

export function useWebSocket(taskId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const retryCount = useRef(0)
  const doneRef = useRef(false)
  const maxRetries = 5
  const { addGeneration, setWsStatus, updateTask, setActiveTaskId, setIndividualProgress,
    setSelectedAnalysisTaskId, setCurrentView } = useTaskStore()

  useEffect(() => {
    if (!taskId) return
    doneRef.current = false
    retryCount.current = 0

    const connect = () => {
      setWsStatus('connecting')
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      const ws = new WebSocket(`${protocol}//${host}/tasks/${taskId}/stream`)
      wsRef.current = ws

      ws.onopen = () => {
        setWsStatus('connected')
        retryCount.current = 0
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'GENERATION_COMPLETED' && msg.data) {
            addGeneration(msg.data)
          } else if (msg.type === 'INDIVIDUAL_PROGRESS') {
            setIndividualProgress({ generation: msg.generation, current: msg.current, total: msg.total })
          } else if (msg.type === 'TASK_COMPLETED') {
            updateTask(taskId, { status: 'COMPLETED', progress_pct: 100 })
            setActiveTaskId(null)
            doneRef.current = true
            ws.close()
            toast.success('演化任務完成！', {
              duration: 8000,
              action: {
                label: '查看結果 →',
                onClick: () => {
                  setSelectedAnalysisTaskId(taskId)
                  setCurrentView('analysis')
                },
              },
            })
          } else if (msg.type === 'TASK_FAILED') {
            updateTask(taskId, { status: 'FAILED', error_message: msg.error })
            setActiveTaskId(null)
            doneRef.current = true
            ws.close()
            toast.error('任務執行失敗', { duration: 6000 })
          } else if (msg.type === 'TASK_CANCELLED') {
            updateTask(taskId, { status: 'CANCELLED' })
            setActiveTaskId(null)
            doneRef.current = true
            ws.close()
          }
        } catch { /* ignore parse errors */ }
      }

      ws.onclose = () => {
        if (!doneRef.current && retryCount.current < maxRetries) {
          setWsStatus('reconnecting')
          const delay = Math.min(1000 * Math.pow(2, retryCount.current), 16000)
          retryCount.current++
          setTimeout(connect, delay)
        } else {
          // idle = task finished normally; disconnected = gave up retrying after error
          setWsStatus(doneRef.current ? 'idle' : 'disconnected')
        }
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      doneRef.current = true
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [taskId])
}
