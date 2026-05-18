interface Props {
  name: string
  description: string
  templateName: string
  onChange: (data: { name: string; description: string }) => void
}

export function BasicInfoStep({ name, description, templateName, onChange }: Props) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">基本資訊</h2>
      <div>
        <label className="block text-sm font-medium mb-1">策略名稱 *</label>
        <input
          type="text"
          value={name}
          onChange={(e) => onChange({ name: e.target.value, description })}
          maxLength={50}
          placeholder="如：雙均線 v2"
          className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
        <span className="text-xs text-gray-400">{name.length}/50</span>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">策略描述</label>
        <textarea
          value={description}
          onChange={(e) => onChange({ name, description: e.target.value })}
          maxLength={200}
          placeholder="簡短說明策略用途..."
          rows={3}
          className="w-full px-3 py-2 border rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
        <span className="text-xs text-gray-400">{description.length}/200</span>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">來源模板</label>
        <input
          type="text"
          value={templateName}
          disabled
          className="w-full px-3 py-2 border rounded-lg text-sm bg-gray-50 text-gray-500"
        />
      </div>
    </div>
  )
}
