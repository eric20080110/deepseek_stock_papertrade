import { useState } from 'react'
import { InstanceList } from './InstanceList'
import { CreateInstanceForm } from './CreateInstanceForm'
import { InstanceDetail } from './InstanceDetail'

export function PaperTradingPanel() {
  const [view, setView] = useState<'list' | 'create' | 'detail'>('list')
  const [detailId, setDetailId] = useState<string | null>(null)

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {view === 'list' && (
        <>
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-bold">模擬跑盤</h1>
            <button onClick={() => setView('create')}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer">
              + 新增模擬實例
            </button>
          </div>
          <InstanceList onViewDetail={(id) => { setDetailId(id); setView('detail') }} />
        </>
      )}
      {view === 'create' && (
        <div>
          <button onClick={() => setView('list')}
            className="mb-4 text-sm text-blue-600 hover:text-blue-800 cursor-pointer">← 返回列表</button>
          <CreateInstanceForm />
        </div>
      )}
      {view === 'detail' && detailId && (
        <div>
          <button onClick={() => setView('list')}
            className="mb-4 text-sm text-blue-600 hover:text-blue-800 cursor-pointer">← 返回列表</button>
          <InstanceDetail instanceId={detailId} />
        </div>
      )}
    </div>
  )
}
