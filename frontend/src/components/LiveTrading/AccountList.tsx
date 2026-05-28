import { useEffect, useState } from 'react'
import { AccountCard } from './AccountCard'

interface Props {
  onViewDetail: (id: string) => void
}

export function AccountList({ onViewDetail }: Props) {
  const [instances, setInstances] = useState<any[]>([])

  useEffect(() => {
    fetch('/live-trading')
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setInstances(data) })
  }, [])

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {instances.map((inst) => (
        <AccountCard key={inst.instance_id} instance={inst} onView={onViewDetail} />
      ))}
      {instances.length === 0 && (
        <div className="col-span-full text-center py-12 text-gray-400">尚無實盤實例</div>
      )}
    </div>
  )
}
