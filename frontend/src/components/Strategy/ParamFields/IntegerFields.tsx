interface Props {
  min: number
  max: number
  step: number
  defaultVal: number
  onChange: (data: { min: number; max: number; step: number; default: number }) => void
}

export function IntegerFields({ min, max, step, defaultVal, onChange }: Props) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <label>最小值 <input type="number" value={min} onChange={(e) => onChange({ min: +e.target.value, max, step, default: defaultVal })} className="w-16 px-1 py-0.5 border rounded text-xs" /></label>
      <label>最大值 <input type="number" value={max} onChange={(e) => onChange({ min, max: +e.target.value, step, default: defaultVal })} className="w-16 px-1 py-0.5 border rounded text-xs" /></label>
      <label>步進 <input type="number" value={step} onChange={(e) => onChange({ min, max, step: +e.target.value, default: defaultVal })} className="w-16 px-1 py-0.5 border rounded text-xs" /></label>
      <label>預設值 <input type="number" value={defaultVal} onChange={(e) => onChange({ min, max, step, default: +e.target.value })} className="w-16 px-1 py-0.5 border rounded text-xs" /></label>
    </div>
  )
}
