import os
import json
import urllib.request
import urllib.error
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

class NotificationSettings(BaseModel):
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    notify_on_task_complete: bool = True
    notify_on_task_fail: bool = True
    notify_on_paper_trade: bool = False

def _send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        text = urllib.request.quote(message)
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={text}&parse_mode=HTML"
        urllib.request.urlopen(url, timeout=10)
        return True
    except Exception:
        return False

@router.get("/notifications/settings")
def get_notification_settings():
    return {
        "telegram_enabled": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "telegram_bot_token": TELEGRAM_BOT_TOKEN[:8] + "..." if TELEGRAM_BOT_TOKEN else "",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "notify_on_task_complete": True,
        "notify_on_task_fail": True,
        "notify_on_paper_trade": False,
    }

@router.post("/notifications/test")
def test_notification():
    ok = _send_telegram("<b>QuantGene 通知測試</b>\n✅ 如果收到此訊息，代表通知系統設定正確！")
    if ok:
        return {"detail": "Test message sent"}
    raise HTTPException(400, "Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.")

@router.post("/notifications/send-task-complete")
def notify_task_complete(task_id: str, task_name: str = ""):
    name = task_name or task_id[:8]
    _send_telegram(f"<b>✅ 任務完成</b>\n{name}")
    return {"detail": "sent"}

@router.post("/notifications/send-task-fail")
def notify_task_fail(task_id: str, task_name: str = "", error: str = ""):
    name = task_name or task_id[:8]
    _send_telegram(f"<b>❌ 任務失敗</b>\n{name}\n{error[:200]}")
    return {"detail": "sent"}
