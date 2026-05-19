export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  type: ToastType
  message: string
}

type Listener = (toast: ToastItem) => void

let _id = 0
const _listeners = new Set<Listener>()

export const toastBus = {
  subscribe(fn: Listener) {
    _listeners.add(fn)
    return () => { _listeners.delete(fn) }
  },
  emit(type: ToastType, message: string) {
    const t: ToastItem = { id: ++_id, type, message }
    _listeners.forEach((fn) => fn(t))
  },
}

export const toast = {
  success: (msg: string) => toastBus.emit('success', msg),
  error: (msg: string) => toastBus.emit('error', msg),
  info: (msg: string) => toastBus.emit('info', msg),
}
