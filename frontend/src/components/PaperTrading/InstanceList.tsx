import { useEffect, useState } from 'react'
import { InstanceCard } from './InstanceCard'
import { PageLoading } from '../LoadingSpinner'

interface Props {
  onViewDetail: (id: string) => void
}

export function InstanceList({ onViewDetail }: Props) {
  const [instances, setInstances] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/paper-trading')
      .then((r) => r.json())
      .then(setInstances)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <PageLoading label="載入模擬實例中..." />

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
