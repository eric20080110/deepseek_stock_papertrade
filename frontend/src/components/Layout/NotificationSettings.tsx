import { useEffect, useState } from 'react'
import { toast } from '../../lib/toast'
import { Bell, Send } from 'lucide-react'

export function NotificationSettings() {
  const [settings, setSettings] = useState<{
    telegram_enabled: boolean
    telegram_bot_token: string
    telegram_chat_id: string
  } | null>(null)

  useEffect(() => {
    fetch('/notifications/settings')
      .then((r) => r.json())
      .then(setSettings)
  }, [])

  const test = async () => {
    try {
      const r = await fetch('/notifications/test', { method: 'POST' })
      if (r.ok) toast.success('測試訊息已發送！請檢查 Telegram')
      else { const e = await r.json(); toast.error(e.detail) }
    } catch { toast.error('發送失敗') }
  }

  if (!settings) return null

  return (
    <div className="border-t pt-3 mt-3">
      <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
        <Bell className="w-3 h-3" />
        通知設定
      </div>
      {settings.telegram_enabled ? (
        <div className="text-xs text-green-600 flex items-center justify-between">
          <span>Telegram 已連線 ({settings.telegram_bot_token})</span>
          <button onClick={test} className="flex items-center gap-1 text-blue-600 hover:underline cursor-pointer">
            <Send className="w-3 h-3" /> 測試
          </button>
        </div>
      ) : (
        <div className="text-xs text-gray-400">
          Telegram 未設定<br />
          請設定環境變數 <code className="text-xs bg-gray-100 px-1">TELEGRAM_BOT_TOKEN</code> 和 <code className="text-xs bg-gray-100 px-1">TELEGRAM_CHAT_ID</code>
        </div>
      )}
    </div>
  )
}
