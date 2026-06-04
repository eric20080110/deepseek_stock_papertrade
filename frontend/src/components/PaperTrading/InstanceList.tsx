import { useEffect, useState } from 'react'
import { InstanceCard } from './InstanceCard'
import type { PaperInstance } from './InstanceCard'

interface Props {
  onViewDetail: (id: string) => void
}

export function InstanceList({ onViewDetail }: Props) {
  const [instances, setInstances] = useState<PaperInstance[]>([])

  useEffect(() => {
    fetch('/paper-trading')
      .then((r) => r.json())
      .then(setInstances)
  }, [])

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {instances.map((inst) => (
        <InstanceCard key={inst.instance_id} instance={inst} onView={onViewDetail} />
      ))}
      {instances.length === 0 && (
        <div className="col-span-full text-center py-12 text-gray-400">尚無模擬實例</div>
      )}
    </div>
  )
}
