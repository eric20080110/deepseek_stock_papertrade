import type { ParamDef, ConstraintDef } from '../../types/strategy'
import { ParamList } from './ParamList'
import { ConstraintList } from './ConstraintList'

interface Props {
  params: ParamDef[]
  constraints: ConstraintDef[]
  onParamsChange: (params: ParamDef[]) => void
  onConstraintsChange: (constraints: ConstraintDef[]) => void
  errors: Record<string, string>
}

export function ParamSpaceEditor({ params, constraints, onParamsChange, onConstraintsChange, errors }: Props) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">參數空間設定</h2>
      <ParamList params={params} onChange={onParamsChange} />
      <div className="border-t pt-4">
        <ConstraintList constraints={constraints} params={params} onChange={onConstraintsChange} />
      </div>
      {Object.keys(errors).length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          {Object.entries(errors).map(([key, msg]) => (
            <p key={key} className="text-sm text-red-600">{msg}</p>
          ))}
        </div>
      )}
    </div>
  )
}
