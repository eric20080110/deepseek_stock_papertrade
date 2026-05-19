import { useEffect, useRef } from 'react'

interface TickPayload {
  type: 'INIT' | 'TICK' | 'ping'
  instance?: Record<string, any>
  total_equity?: number
  events?: any[]
}

interface Options {
  onInit: (instance: Record<string, any>) => void
  onTick: (payload: TickPayload) => void
}

export function usePaperTradingWS(instanceId: string | null, { onInit, onTick }: Options) {
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(0)
  const maxRetries = 5

  useEffect(() => {
    if (!instanceId) return

    const connect = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/paper-trading/${instanceId}/stream`)
      wsRef.current = ws

      ws.onmessage = (ev) => {
        try {
          const msg: TickPayload = JSON.parse(ev.data)
          if (msg.type === 'INIT' && msg.instance) {
            retryRef.current = 0
            onInit(msg.instance)
          } else if (msg.type === 'TICK') {
            onTick(msg)
          }
        } catch {}
      }

      ws.onclose = () => {
        if (retryRef.current < maxRetries) {
          const delay = Math.min(1000 * 2 ** retryRef.current, 16000)
          retryRef.current++
          setTimeout(connect, delay)
        }
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [instanceId])
}
