import time
import yfinance as yf
from fastapi import APIRouter, Query

router = APIRouter(prefix="/symbols", tags=["symbols"])

VALID_EXCHANGES = frozenset({
    "NMS", "NGM", "NCM", "NYQ", "NYS", "ARC", "BTS", "PCX", "NASDAQ",
})

TYPE_MAP = {
    "EQUITY": "us_equity",
    "ETF": "us_etf",
    "INDEX": "us_index",
}

_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 300  # 5 minutes

@router.get("/search")
async def search_symbols(q: str = Query(..., min_length=1)):
    if len(q) < 1:
        return {"results": []}

    key = q.strip().upper()

    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < _CACHE_TTL:
        return {"results": cached[1]}

    results: list[dict] = []

    try:
        search = yf.Search(key, max_results=15)
        for quote in search.quotes or []:
            symbol = quote.get("symbol", "")
            if not symbol:
                continue
            qtype = quote.get("quoteType", "")
            exchange = (quote.get("exchange") or "").upper()
            if qtype in TYPE_MAP and exchange in VALID_EXCHANGES:
                name = quote.get("shortName") or quote.get("longName") or symbol
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "type": TYPE_MAP[qtype],
                    "exchange": exchange,
                })
    except Exception:
        pass

    _cache[key] = (now, results)
    return {"results": results}
