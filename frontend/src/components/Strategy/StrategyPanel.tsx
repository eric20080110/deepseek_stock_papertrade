import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useTaskStore } from '../../store/taskStore'
import type { StrategyConfig } from '../../types/strategy'
import { StrategyList } from './StrategyList'
import { TemplateSelector } from './TemplateSelector'
import { StrategyForm } from './StrategyForm'

type View = 'list' | 'create' | 'edit'

export function StrategyPanel() {
  const [strategies, setStrategies] = useState<StrategyConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<View>('list')
  const [editId, setEditId] = useState<string | null>(null)
  const [templateId, setTemplateId] = useState<string | null>(null)
  const [showTemplateSelector, setShowTemplateSelector] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listStrategies()
      setStrategies(data)
    } catch (e) {
      console.error('Failed to load strategies', e)
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreateFromTemplate = (tid: string) => {
    setShowTemplateSelector(false)
    setTemplateId(tid)
    setView('create')
  }

  const handleEdit = (s: StrategyConfig) => {
    setEditId(s.config_id)
    setTemplateId(s.template_id)
    setView('edit')
  }

  const handleSaved = () => {
    setView('list')
    setEditId(null)
    setTemplateId(null)
    load()
  }

  const handleCancel = () => {
    setView('list')
    setEditId(null)
    setTemplateId(null)
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {view === 'list' && (
        <>
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-bold">策略管理</h1>
            <button
              onClick={() => setShowTemplateSelector(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer"
            >
              + 從模板建立
            </button>
          </div>
          <StrategyList
            strategies={strategies}
            loading={loading}
            onEdit={handleEdit}
            onRefresh={load}
            onUseStrategy={(s) => {
              useTaskStore.getState().setSelectedStrategy(s.config_id);
              useTaskStore.getState().setCurrentView('new-task');
            }}
            onCreateFromTemplate={(s) => {
              setTemplateId(s.template_id);
              setView('create');
            }}
          />
          {showTemplateSelector && (
            <TemplateSelector
              onSelect={handleCreateFromTemplate}
              onClose={() => setShowTemplateSelector(false)}
            />
          )}
        </>
      )}
      {view === 'create' && templateId && (
        <StrategyForm
          templateId={templateId}
          onSave={handleSaved}
          onCancel={handleCancel}
        />
      )}
      {view === 'edit' && editId && (
        <StrategyForm
          configId={editId}
          templateId={templateId}
          onSave={handleSaved}
          onCancel={handleCancel}
        />
      )}
    </div>
  )
}
