export type ToastType = 'success' | 'error' | 'info'

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastItem {
  id: number
  type: ToastType
  message: string
  action?: ToastAction
  duration?: number
}

type Listener = (toast: ToastItem) => void

let _id = 0
const _listeners = new Set<Listener>()

export const toastBus = {
  subscribe(fn: Listener) {
    _listeners.add(fn)
    return () => { _listeners.delete(fn) }
  },
  emit(type: ToastType, message: string, opts?: { action?: ToastAction; duration?: number }) {
    const t: ToastItem = { id: ++_id, type, message, ...opts }
    _listeners.forEach((fn) => fn(t))
  },
}

export const toast = {
  success: (msg: string, opts?: { action?: ToastAction; duration?: number }) => toastBus.emit('success', msg, opts),
  error: (msg: string, opts?: { action?: ToastAction; duration?: number }) => toastBus.emit('error', msg, opts),
  info: (msg: string, opts?: { action?: ToastAction; duration?: number }) => toastBus.emit('info', msg, opts),
}
