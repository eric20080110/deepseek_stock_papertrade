import { Plus, X } from 'lucide-react'

interface Props {
  options: string[]
  defaultVal: string
  onChange: (data: { options: string[]; default: string }) => void
}

export function CategoricalFields({ options, defaultVal, onChange }: Props) {
  const addOption = () => {
    const label = prompt('輸入選項名稱：')
    if (label && !options.includes(label)) {
      onChange({ options: [...options, label], default: defaultVal })
    }
  }

  const removeOption = (opt: string) => {
    const newOpts = options.filter((o) => o !== opt)
    onChange({ options: newOpts, default: newOpts.includes(defaultVal) ? defaultVal : newOpts[0] || '' })
  }

  return (
    <div className="flex items-center gap-2 text-sm flex-wrap">
      {options.map((opt) => (
        <span key={opt} className="flex items-center gap-1 px-2 py-0.5 bg-gray-100 rounded-full text-xs">
          {opt}
          <button onClick={() => removeOption(opt)} className="cursor-pointer"><X className="w-3 h-3" /></button>
        </span>
      ))}
      <button onClick={addOption} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 cursor-pointer">
        <Plus className="w-3 h-3" /> 新增
      </button>
      <label className="ml-2 text-xs">
        預設：
        <select value={defaultVal} onChange={(e) => onChange({ options, default: e.target.value })} className="ml-1 px-1 py-0.5 border rounded text-xs">
          {options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      </label>
    </div>
  )
}
