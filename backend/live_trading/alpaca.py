import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def _config():
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_API_SECRET", "")
    base = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    # Strip /v2 if user included it in the base URL to avoid double pathing
    if base.endswith("/v2"):
        base = base[:-3]
    return key, secret, base


def configured() -> bool:
    k, s, _ = _config()
    return bool(k and s)


def _headers() -> dict:
    k, s, _ = _config()
    return {
        "APCA-API-KEY-ID": k,
        "APCA-API-SECRET-KEY": s,
        "Content-Type": "application/json",
    }


class AlpacaError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _request(method: str, path: str, body: Optional[dict] = None, timeout: int = 10) -> Optional[dict]:
    if not configured():
        return None
    _, _, base = _config()
    url = f"{base}{path}"
    try:
        r = requests.request(method, url, json=body, headers=_headers(), timeout=timeout)
        if r.status_code >= 400:
            details = r.text[:300]
            logger.warning("Alpaca HTTP %d on %s: %s", r.status_code, url, details)
            raise AlpacaError(f"HTTP {r.status_code} on {url}: {details}", r.status_code)
        return r.json()
    except requests.RequestException as e:
        logger.warning("Alpaca request failed %s: %s", url, e)
        raise AlpacaError(f"{url}: {e}")


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
