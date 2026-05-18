import type { StrategyConfig } from '../types/strategy'

const BASE = ''

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export const api = {
  listStrategies: () => request<StrategyConfig[]>('/strategies'),
  listTemplates: () => request<StrategyConfig[]>('/strategies/templates'),
  getStrategy: (id: string) => request<StrategyConfig>(`/strategies/${id}`),
  createStrategy: (data: { template_id: string; name: string; description?: string; parameters?: any[]; constraints?: any[] }) =>
    request<StrategyConfig>('/strategies', { method: 'POST', body: JSON.stringify(data) }),
  updateStrategy: (id: string, data: { name: string; description?: string; parameters: any[]; constraints: any[] }) =>
    request<StrategyConfig>(`/strategies/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteStrategy: (id: string) => request<{ detail: string }>(`/strategies/${id}`, { method: 'DELETE' }),
  duplicateStrategy: (id: string) => request<StrategyConfig>(`/strategies/${id}/duplicate`, { method: 'POST' }),
}
