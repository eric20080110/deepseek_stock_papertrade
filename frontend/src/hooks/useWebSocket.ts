import { useEffect, useRef } from 'react'
import { useTaskStore } from '../store/taskStore'

export function useWebSocket(taskId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const retryCount = useRef(0)
  const maxRetries = 5
  const { addGeneration, setWsStatus, updateTask, setActiveTaskId, setIndividualProgress } = useTaskStore()

  useEffect(() => {
    if (!taskId) return

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
            ws.close()
          } else if (msg.type === 'TASK_FAILED') {
            updateTask(taskId, { status: 'FAILED', error_message: msg.error })
            setActiveTaskId(null)
            ws.close()
          } else if (msg.type === 'TASK_CANCELLED') {
            updateTask(taskId, { status: 'CANCELLED' })
            setActiveTaskId(null)
            ws.close()
          }
        } catch {}
      }

      ws.onclose = () => {
        if (retryCount.current < maxRetries) {
          setWsStatus('reconnecting')
          const delay = Math.min(1000 * Math.pow(2, retryCount.current), 16000)
          retryCount.current++
          setTimeout(connect, delay)
        } else {
          setWsStatus('disconnected')
        }
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [taskId])
}
