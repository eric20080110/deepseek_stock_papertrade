import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("ALPACA_API_KEY", "")
API_SECRET = os.environ.get("ALPACA_API_SECRET", "")
BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")

CONFIGURED = bool(API_KEY and API_SECRET)


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID": API_KEY,
        "APCA-API-SECRET-KEY": API_SECRET,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, body: Optional[dict] = None, timeout: int = 10) -> Optional[dict]:
    if not CONFIGURED:
        return None
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.warning("Alpaca HTTP %d on %s %s: %s", e.code, method, path, body)
        return None
    except Exception as e:
        logger.warning("Alpaca request failed %s %s: %s", method, path, e)
        return None


def submit_order(symbol: str, side: str, qty: float, order_type: str = "market",
                 time_in_force: str = "day") -> Optional[dict]:
    body = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "qty": str(qty),
        "time_in_force": time_in_force,
    }
    result = _request("POST", "/v2/orders", body)
    if result:
        logger.info("Alpaca order submitted: %s %s %s qty=%s id=%s", side, symbol, order_type, qty, result.get("id"))
    return result


def get_order(alpaca_order_id: str) -> Optional[dict]:
    return _request("GET", f"/v2/orders/{alpaca_order_id}")


def cancel_order(alpaca_order_id: str) -> bool:
    result = _request("DELETE", f"/v2/orders/{alpaca_order_id}")
    return result is not None


def list_positions() -> list[dict]:
    result = _request("GET", "/v2/positions")
    return result if isinstance(result, list) else []


def get_position(symbol: str) -> Optional[dict]:
    return _request("GET", f"/v2/positions/{symbol}")


def close_position(symbol: str) -> Optional[dict]:
    return _request("DELETE", f"/v2/positions/{symbol}")


def get_account() -> Optional[dict]:
    return _request("GET", "/v2/account")
