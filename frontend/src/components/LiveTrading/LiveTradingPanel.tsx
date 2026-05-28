import { useState, useEffect } from 'react'
import { AccountList } from './AccountList'
import { CreateAccountForm } from './CreateAccountForm'
import { AccountDetail } from './AccountDetail'

interface AccountInfo {
  connected: boolean
  equity?: number
  cash?: number
  buying_power?: number
  status?: string
  currency?: string
  reason?: string
}

function AccountSummary() {
  const [info, setInfo] = useState<AccountInfo | null>(null)

  useEffect(() => {
    const check = () =>
      fetch('/live-trading/account')
        .then((r) => r.json())
        .then(setInfo)
        .catch(() => setInfo({ connected: false }))
    check()
    const t = setInterval(check, 30000)
    return () => clearInterval(t)
  }, [])

  if (!info) return null

  if (!info.connected) {
    return (
      <div className="p-3 bg-gray-50 border rounded-lg text-sm text-gray-500">
        Alpaca 未連線（{info.reason === 'not_configured' ? '未設定 API Key' : info.reason || '連線失敗'}）
      </div>
    )
  }

  return (
    <div className="p-3 bg-gradient-to-r from-rose-50 to-orange-50 border border-rose-200 rounded-lg">
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-rose-600 uppercase tracking-wide">Alpaca 帳戶</span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${info.status === 'ACTIVE' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
          {info.status || 'UNKNOWN'}
        </span>
      </div>
      <div className="flex gap-6 mt-2">
        <div>
          <div className="text-xs text-gray-500">總權益</div>
          <div className="text-lg font-bold text-gray-900">
            {info.currency === 'USD' ? '$' : ''}{info.equity?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">可用現金</div>
          <div className="text-base font-semibold text-gray-700">
            {info.currency === 'USD' ? '$' : ''}{info.cash?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">購買力</div>
          <div className="text-base font-semibold text-gray-700">
            {info.currency === 'USD' ? '$' : ''}{info.buying_power?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
      </div>
    </div>
  )
}

export function LiveTradingPanel() {
  const [view, setView] = useState<'list' | 'create' | 'detail'>('list')
  const [detailId, setDetailId] = useState<string | null>(null)

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {view === 'list' && (
        <>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-rose-700">實盤跑盤</h1>
            </div>
            <button onClick={() => setView('create')}
              className="px-4 py-2 bg-rose-600 text-white rounded-lg hover:bg-rose-700 cursor-pointer">
              + 新增實盤實例
            </button>
          </div>
          <div className="mb-6">
            <AccountSummary />
          </div>
          <AccountList onViewDetail={(id) => { setDetailId(id); setView('detail') }} />
        </>
      )}
      {view === 'create' && (
        <div>
          <button onClick={() => setView('list')}
            className="mb-4 text-sm text-rose-600 hover:text-rose-800 cursor-pointer">← 返回列表</button>
          <CreateAccountForm />
        </div>
      )}
      {view === 'detail' && detailId && (
        <div>
          <button onClick={() => setView('list')}
            className="mb-4 text-sm text-rose-600 hover:text-rose-800 cursor-pointer">← 返回列表</button>
          <AccountDetail instanceId={detailId} />
        </div>
      )}
    </div>
  )
}
