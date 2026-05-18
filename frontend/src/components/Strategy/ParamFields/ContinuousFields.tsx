interface Props {
  min: number
  max: number
  defaultVal: number
  scale: 'linear' | 'logarithmic'
  onChange: (data: { min: number; max: number; default: number; scale: 'linear' | 'logarithmic' }) => void
}

export function ContinuousFields({ min, max, defaultVal, scale, onChange }: Props) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <label>最小值 <input type="number" step="any" value={min} onChange={(e) => onChange({ min: +e.target.value, max, default: defaultVal, scale })} className="w-16 px-1 py-0.5 border rounded text-xs" /></label>
      <label>最大值 <input type="number" step="any" value={max} onChange={(e) => onChange({ min, max: +e.target.value, default: defaultVal, scale })} className="w-16 px-1 py-0.5 border rounded text-xs" /></label>
      <label>預設值 <input type="number" step="any" value={defaultVal} onChange={(e) => onChange({ min, max, default: +e.target.value, scale })} className="w-16 px-1 py-0.5 border rounded text-xs" /></label>
      <label>尺度
        <select value={scale} onChange={(e) => onChange({ min, max, default: defaultVal, scale: e.target.value as any })} className="ml-1 px-1 py-0.5 border rounded text-xs">
          <option value="linear">線性</option>
          <option value="logarithmic">對數</option>
        </select>
      </label>
    </div>
  )
}
