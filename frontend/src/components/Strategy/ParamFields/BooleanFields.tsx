interface Props {
  defaultVal: boolean
  controls: string[]
  allParamNames: string[]
  onChange: (data: { default: boolean; controls: string[] }) => void
}

export function BooleanFields({ defaultVal, controls = [], allParamNames, onChange }: Props) {
  const nonBooleanParams = allParamNames

  const toggleControl = (name: string) => {
    const next = controls.includes(name) ? controls.filter((c) => c !== name) : [...controls, name]
    onChange({ default: defaultVal, controls: next })
  }

  return (
    <div className="flex items-center gap-2 text-sm flex-wrap">
      <label className="flex items-center gap-1">
        預設值：
        <input type="checkbox" checked={defaultVal} onChange={(e) => onChange({ default: e.target.checked, controls })} className="cursor-pointer" />
      </label>
      {nonBooleanParams.length > 0 && (
        <div className="text-xs text-gray-500 flex items-center gap-1 flex-wrap">
          <span>受控子參數：</span>
          {nonBooleanParams.map((name) => (
            <label key={name} className="flex items-center gap-0.5 cursor-pointer">
              <input type="checkbox" checked={controls.includes(name)} onChange={() => toggleControl(name)} />
              {name}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
