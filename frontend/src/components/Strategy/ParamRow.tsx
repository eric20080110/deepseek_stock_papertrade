import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Trash2 } from 'lucide-react'
import type { ParamDef } from '../../types/strategy'
import { ContinuousFields } from './ParamFields/ContinuousFields'
import { IntegerFields } from './ParamFields/IntegerFields'
import { CategoricalFields } from './ParamFields/CategoricalFields'
import { BooleanFields } from './ParamFields/BooleanFields'

interface Props {
  param: ParamDef
  allParamNames: string[]
  onChange: (p: ParamDef) => void
  onDelete: () => void
}

export function ParamRow({ param, allParamNames, onChange, onDelete }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: param.name })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div ref={setNodeRef} style={style} className="flex items-center gap-2 py-2 px-3 border rounded-lg bg-white">
      <button {...attributes} {...listeners} className="cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600">
        <GripVertical className="w-4 h-4" />
      </button>
      <input
        type="text"
        value={param.name}
        onChange={(e) => onChange({ ...param, name: e.target.value })}
        className="w-28 px-2 py-1 border rounded text-xs font-mono outline-none focus:ring-1 focus:ring-blue-500"
        placeholder="param_name"
      />
      <select
        value={param.type}
        onChange={(e) => {
          const t = e.target.value
          let base: any = { name: param.name, type: t }
          if (t === 'continuous') base = { ...base, min: 0, max: 1, default: 0.5, scale: 'linear' }
          else if (t === 'integer') base = { ...base, min: 1, max: 100, step: 1, default: 10 }
          else if (t === 'categorical') base = { ...base, options: ['A', 'B'], default: 'A' }
          else base = { ...base, default: false, controls: [] }
          onChange(base as ParamDef)
        }}
        className="px-2 py-1 border rounded text-xs outline-none"
      >
        <option value="continuous">連續型</option>
        <option value="integer">整數型</option>
        <option value="categorical">類別型</option>
        <option value="boolean">布林型</option>
      </select>

      <div className="flex-1">
        {param.type === 'continuous' && (
          <ContinuousFields {...param} defaultVal={param.default} onChange={(d) => onChange({ ...param, ...d } as ParamDef)} />
        )}
        {param.type === 'integer' && (
          <IntegerFields {...param} defaultVal={param.default} onChange={(d) => onChange({ ...param, ...d } as ParamDef)} />
        )}
        {param.type === 'categorical' && (
          <CategoricalFields {...param} defaultVal={param.default} onChange={(d) => onChange({ ...param, ...d } as ParamDef)} />
        )}
        {param.type === 'boolean' && (
          <BooleanFields {...param} defaultVal={param.default} allParamNames={allParamNames} onChange={(d) => onChange({ ...param, ...d } as ParamDef)} />
        )}
      </div>

      <button onClick={onDelete} className="text-red-400 hover:text-red-600 cursor-pointer">
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  )
}
