import { Plus } from 'lucide-react'
import type { ConstraintDef, ParamDef } from '../../types/strategy'
import { ConstraintRow } from './ConstraintRow'

interface Props {
  constraints: ConstraintDef[]
  params: ParamDef[]
  onChange: (constraints: ConstraintDef[]) => void
}

export function ConstraintList({ constraints, params, onChange }: Props) {
  const addConstraint = (type: ConstraintDef['type']) => {
    let c: ConstraintDef
    if (type === 'ordering') {
      c = { type: 'ordering', params: [], relation: 'less_than', repair: 'clamp_upper' }
    } else if (type === 'conditional') {
      c = { type: 'conditional', controller: '', active_when: true, controlled_params: [] }
    } else {
      c = { type: 'categorical_group', controller: '', groups: {}, common_params: [] }
    }
    onChange([...constraints, c])
  }

  const updateConstraint = (index: number, c: ConstraintDef) => {
    onChange(constraints.map((orig, i) => (i === index ? c : orig)))
  }

  const deleteConstraint = (index: number) => {
    onChange(constraints.filter((_, i) => i !== index))
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold">約束條件</h3>
        <div className="flex gap-1">
          <button onClick={() => addConstraint('ordering')} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 cursor-pointer">
            <Plus className="w-3 h-3" /> 數值大小
          </button>
          <button onClick={() => addConstraint('conditional')} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 cursor-pointer">
            <Plus className="w-3 h-3" /> 條件啟用
          </button>
          <button onClick={() => addConstraint('categorical_group')} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 cursor-pointer">
            <Plus className="w-3 h-3" /> 類別分組
          </button>
        </div>
      </div>
      <div className="space-y-2">
        {constraints.map((c, i) => (
          <ConstraintRow key={i} constraint={c} params={params} onChange={(nc) => updateConstraint(i, nc)} onDelete={() => deleteConstraint(i)} />
        ))}
      </div>
      {constraints.length === 0 && <div className="text-xs text-gray-400 py-4 text-center">尚無約束條件</div>}
    </div>
  )
}
