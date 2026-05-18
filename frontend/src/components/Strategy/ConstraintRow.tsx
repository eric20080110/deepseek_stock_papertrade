import { Trash2 } from 'lucide-react'
import type { ConstraintDef, ParamDef } from '../../types/strategy'

interface Props {
  constraint: ConstraintDef
  params: ParamDef[]
  onChange: (c: ConstraintDef) => void
  onDelete: () => void
}

export function ConstraintRow({ constraint, params, onChange, onDelete }: Props) {
  const booleanNames = params.filter((p) => p.type === 'boolean').map((p) => p.name)
  const categoricalNames = params.filter((p) => p.type === 'categorical').map((p) => p.name)
  const numericNames = params.filter((p) => p.type === 'continuous' || p.type === 'integer').map((p) => p.name)
  const nonBooleanNames = params.filter((p) => p.type !== 'boolean').map((p) => p.name)

  if (constraint.type === 'ordering') {
    return (
      <div className="flex items-center gap-2 py-2 px-3 border rounded-lg bg-white text-sm">
        <span className="text-xs text-gray-400 w-16">數值大小</span>
        <select
          multiple
          value={constraint.params}
          onChange={(e) => {
            const selected = Array.from(e.target.selectedOptions, (o) => o.value)
            onChange({ ...constraint, params: selected } as ConstraintDef)
          }}
          className="w-40 px-1 py-1 border rounded text-xs"
          size={2}
        >
          {numericNames.map((n) => (
            <option key={n} value={n} selected={constraint.params.includes(n)}>{n}</option>
          ))}
        </select>
        <select
          value={constraint.relation}
          onChange={(e) => onChange({ ...constraint, relation: e.target.value } as any)}
          className="px-1 py-1 border rounded text-xs"
        >
          <option value="less_than">嚴格小於</option>
          <option value="less_equal">小於等於</option>
        </select>
        <select
          value={constraint.repair}
          onChange={(e) => onChange({ ...constraint, repair: e.target.value } as any)}
          className="px-1 py-1 border rounded text-xs"
        >
          <option value="clamp_upper">調整前者</option>
          <option value="clamp_lower">調整後者</option>
          <option value="swap">對調</option>
        </select>
        <button onClick={onDelete} className="ml-auto text-red-400 hover:text-red-600 cursor-pointer">
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    )
  }

  if (constraint.type === 'conditional') {
    return (
      <div className="flex items-center gap-2 py-2 px-3 border rounded-lg bg-white text-sm">
        <span className="text-xs text-gray-400 w-16">條件啟用</span>
        <label className="text-xs">
          控制器
          <select value={constraint.controller} onChange={(e) => onChange({ ...constraint, controller: e.target.value } as any)} className="ml-1 px-1 py-1 border rounded text-xs">
            <option value="">--</option>
            {booleanNames.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="text-xs">
          啟用條件
          <select value={String(constraint.active_when)} onChange={(e) => onChange({ ...constraint, active_when: e.target.value === 'true' } as any)} className="ml-1 px-1 py-1 border rounded text-xs">
            <option value="true">True 時啟用</option>
            <option value="false">False 時啟用</option>
          </select>
        </label>
        <label className="text-xs">
          受控參數
          <select multiple value={constraint.controlled_params} onChange={(e) => onChange({ ...constraint, controlled_params: Array.from(e.target.selectedOptions, (o) => o.value) } as any)} className="ml-1 px-1 py-1 border rounded text-xs" size={2}>
            {nonBooleanNames.filter((n) => n !== constraint.controller).map((n) => (
              <option key={n} value={n} selected={constraint.controlled_params.includes(n)}>{n}</option>
            ))}
          </select>
        </label>
        <button onClick={onDelete} className="ml-auto text-red-400 hover:text-red-600 cursor-pointer">
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    )
  }

  if (constraint.type === 'categorical_group') {
    return (
      <div className="flex flex-col gap-2 py-2 px-3 border rounded-lg bg-white text-sm">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 w-16">類別分組</span>
          <label className="text-xs">
            控制器
            <select value={constraint.controller} onChange={(e) => onChange({ ...constraint, controller: e.target.value, groups: {} } as any)} className="ml-1 px-1 py-1 border rounded text-xs">
              <option value="">--</option>
              {categoricalNames.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button onClick={onDelete} className="ml-auto text-red-400 hover:text-red-600 cursor-pointer">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
        {constraint.controller && params.find((p) => p.name === constraint.controller)?.type === 'categorical' && (
          <div className="ml-16 space-y-1">
            {(() => {
              const catParam = params.find((p) => p.name === constraint.controller)
              const opts = catParam && 'options' in catParam ? (catParam as any).options : []
              return opts.map((opt: string) => (
                <div key={opt} className="flex items-center gap-2 text-xs">
                  <span className="font-medium w-20">{opt}：</span>
                  <select
                    multiple
                    value={constraint.groups[opt] || []}
                    onChange={(e) => {
                      const selected = Array.from(e.target.selectedOptions, (o) => o.value)
                      onChange({ ...constraint, groups: { ...constraint.groups, [opt]: selected } } as any)
                    }}
                    className="w-40 px-1 py-0.5 border rounded text-xs"
                    size={2}
                  >
                    {nonBooleanNames.filter((n) => n !== constraint.controller).map((n) => (
                      <option key={n} value={n} selected={(constraint.groups[opt] || []).includes(n)}>{n}</option>
                    ))}
                  </select>
                </div>
              ))
            })()}
          </div>
        )}
      </div>
    )
  }

  return null
}
