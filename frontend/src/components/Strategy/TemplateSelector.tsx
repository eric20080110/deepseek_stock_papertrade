import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { StrategyConfig } from '../../types/strategy'
import { X } from 'lucide-react'

interface Props {
  onSelect: (templateId: string) => void
  onClose: () => void
}

export function TemplateSelector({ onSelect, onClose }: Props) {
  const [templates, setTemplates] = useState<StrategyConfig[]>([])

  useEffect(() => {
    api.listTemplates().then(setTemplates).catch(console.error)
  }, [])

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">選擇模板</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg cursor-pointer">
            <X className="w-5 h-5" />
          </button>
        </div>
        <p className="text-sm text-gray-500 mb-4">選擇一個系統模板作為起點，建立你的策略</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {templates.map((t) => (
            <button
              key={t.config_id}
              onClick={() => onSelect(t.template_id!)}
              className="text-left border rounded-xl p-4 hover:border-blue-500 hover:shadow-md transition-all cursor-pointer"
            >
              <h3 className="font-semibold">{t.name}</h3>
              <p className="text-sm text-gray-500 mt-1 line-clamp-2">{t.description}</p>
              <span className="text-xs text-gray-400 mt-2 block">{t.parameters.length} 個參數</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
