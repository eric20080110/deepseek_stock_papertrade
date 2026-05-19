import type { StrategyConfig } from '../../types/strategy'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Lock, Pencil, Trash2, Copy, Eye } from 'lucide-react'

interface Props {
  strategy: StrategyConfig
  onEdit: (s: StrategyConfig) => void
  onRefresh: () => void
  onUseStrategy?: (s: StrategyConfig) => void
  onCreateFromTemplate?: (s: StrategyConfig) => void
}

export function StrategyCard({ strategy, onEdit, onRefresh, onUseStrategy, onCreateFromTemplate }: Props) {
  const s = strategy
  const isTemplate = s.is_template
  const isLocked = s.is_locked

  const handleDelete = async () => {
    if (!confirm(`確定刪除策略「${s.name}」？`)) return
    try {
      await api.deleteStrategy(s.config_id)
      onRefresh()
    } catch (e: any) {
      toast.error(e.message)
    }
  }

  const handleDuplicate = async () => {
    try {
      await api.duplicateStrategy(s.config_id)
      onRefresh()
    } catch (e: any) {
      toast.error(e.message)
    }
  }

  const paramCount = s.parameters.length
  const constraintCount = s.constraints.length
  const templateName = s.template_id ?? ''

  return (
    <div className="relative border rounded-xl p-5 bg-white shadow-sm hover:shadow-md transition-shadow">
      {isTemplate && (
        <span className="absolute top-3 right-3 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
          系統模板
        </span>
      )}
      {isLocked && (
        <span className="absolute top-3 right-3 text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full font-medium flex items-center gap-1">
          <Lock className="w-3 h-3" /> 鎖定中
        </span>
      )}

      <div className="mb-3">
        <h3 className="font-semibold text-lg">{s.name}</h3>
        {s.description && (
          <p className="text-sm text-gray-500 mt-1 line-clamp-2">{s.description}</p>
        )}
      </div>

      <div className="flex items-center gap-3 text-xs text-gray-400 mb-4">
        {templateName && <span>模板：{templateName}</span>}
        <span>{paramCount} 個參數</span>
        <span>{constraintCount} 個約束</span>
        <span>{new Date(s.created_at * 1000).toLocaleDateString()}</span>
      </div>

      <div className="flex items-center gap-2 pt-3 border-t">
        {isTemplate ? (
          <button
            onClick={() => onEdit(s)}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border rounded-lg hover:bg-gray-50 cursor-pointer"
          >
            <Eye className="w-4 h-4" /> 查看詳情
          </button>
        ) : (
          <button
            onClick={() => onEdit(s)}
            disabled={isLocked}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            title={isLocked ? '此策略正被任務使用中，完成後可編輯' : ''}
          >
            <Pencil className="w-4 h-4" /> 編輯
          </button>
        )}
        <button
          onClick={handleDuplicate}
          className="flex items-center gap-1 px-3 py-1.5 text-sm border rounded-lg hover:bg-gray-50 cursor-pointer"
        >
          <Copy className="w-4 h-4" /> 複製
        </button>
        {!isTemplate && (
          <button
            onClick={handleDelete}
            disabled={isLocked}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            title={isLocked ? '此策略正被任務使用中，完成後可編輯' : ''}
          >
            <Trash2 className="w-4 h-4" /> 刪除
          </button>
        )}
        {!isTemplate && (
          <button
            onClick={() => onUseStrategy?.(s)}
            className="ml-auto flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer"
          >
            使用此策略
          </button>
        )}
        {isTemplate && (
          <button
            onClick={() => onCreateFromTemplate?.(s)}
            className="ml-auto flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer"
          >
            從此模板建立
          </button>
        )}
      </div>
    </div>
  )
}
