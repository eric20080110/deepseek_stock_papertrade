import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { Plus } from 'lucide-react'
import type { ParamDef } from '../../types/strategy'
import { ParamRow } from './ParamRow'

interface Props {
  params: ParamDef[]
  onChange: (params: ParamDef[]) => void
}

export function ParamList({ params, onChange }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = params.findIndex((p) => p.name === active.id)
    const newIndex = params.findIndex((p) => p.name === over.id)
    const newParams = [...params]
    const [moved] = newParams.splice(oldIndex, 1)
    newParams.splice(newIndex, 0, moved)
    onChange(newParams)
  }

  const addParam = () => {
    const baseName = `param${params.length + 1}`
    const newParam: ParamDef = { name: baseName, type: 'continuous', min: 0, max: 1, default: 0.5, scale: 'linear' }
    onChange([...params, newParam])
  }

  const updateParam = (index: number, p: ParamDef) => {
    const newParams = params.map((orig, i) => (i === index ? p : orig))
    onChange(newParams)
  }

  const deleteParam = (index: number) => {
    onChange(params.filter((_, i) => i !== index))
  }

  const allNames = params.map((p) => p.name)

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold">參數列表</h3>
        <button onClick={addParam} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 cursor-pointer">
          <Plus className="w-3 h-3" /> 新增參數
        </button>
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={params.map((p) => p.name)} strategy={verticalListSortingStrategy}>
          <div className="space-y-2">
            {params.map((p, i) => (
              <ParamRow key={p.name} param={p} allParamNames={allNames} onChange={(np) => updateParam(i, np)} onDelete={() => deleteParam(i)} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
      {params.length === 0 && <div className="text-xs text-gray-400 py-4 text-center">尚無參數，按上方按鈕新增</div>}
    </div>
  )
}
