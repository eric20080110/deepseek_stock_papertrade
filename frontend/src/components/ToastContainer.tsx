import { useEffect, useState } from 'react'
import { toastBus, type ToastItem } from '../lib/toast'

const ICONS = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
}

const COLORS = {
  success: 'bg-green-600',
  error: 'bg-red-600',
  info: 'bg-gray-800',
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    return toastBus.subscribe((t) => {
      setToasts((prev) => [...prev, t])
      setTimeout(() => {
        setToasts((prev) => prev.filter((x) => x.id !== t.id))
      }, 3500)
    })
  }, [])

  if (toasts.length === 0) return null

  return (
    <>
      <style>{`
        @keyframes toast-in {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .toast-item { animation: toast-in 0.18s ease-out; }
      `}</style>
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div key={t.id}
            className={`toast-item flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg text-sm text-white max-w-xs ${COLORS[t.type]}`}>
            <span className="font-bold mt-px">{ICONS[t.type]}</span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </>
  )
}
