from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx


@dataclass(frozen=True)
class Market:
    exchange: str
    symbol: str  # canonical BASE/QUOTE
    raw: str  # exchange-native symbol/instId


def _canonical(base: str, quote: str) -> str:
    return f"{base.upper()}/{quote.upper()}"


def _http_get(url: str, *, params: Optional[dict[str, str]] = None, timeout_sec: float = 10.0) -> Any:
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_binance_usdt_perp(*, base_url: str = "https://fapi.binance.com") -> list[Market]:
    payload = _http_get(f"{base_url}/fapi/v1/exchangeInfo")
    markets: list[Market] = []
    for row in payload.get("symbols", []) or []:
        if row.get("contractType") != "PERPETUAL":
            continue
        if row.get("quoteAsset") != "USDT":
            continue
        if row.get("status") != "TRADING":
            continue
        base = row.get("baseAsset")
        quote = row.get("quoteAsset")
        sym = row.get("symbol")
        if not base or not quote or not sym:
            continue
        markets.append(Market(exchange="binance", symbol=_canonical(base, quote), raw=str(sym)))
    return markets


def fetch_okx_swap(*, base_url: str = "https://www.okx.com") -> list[Market]:
    payload = _http_get(
        f"{base_url.rstrip('/')}/api/v5/public/instruments",
        params={"instType": "SWAP"},
    )
    markets: list[Market] = []
    for row in payload.get("data", []) or []:
        inst_id = row.get("instId")
        state = row.get("state")
        if state and str(state).lower() not in {"live"}:
            continue
        if not inst_id:
            continue
        parts = str(inst_id).split("-")
        if len(parts) < 3:
            continue
        base, quote = parts[0], parts[1]
        markets.append(Market(exchange="okx", symbol=_canonical(base, quote), raw=str(inst_id)))
    return markets


def fetch_bybit_usdt_perp(*, base_url: str = "https://api.bybit.com") -> list[Market]:
    # Unified v5: /v5/market/instruments-info?category=linear
    payload = _http_get(
        f"{base_url.rstrip('/')}/v5/market/instruments-info",
        params={"category": "linear"},
    )
    result = payload.get("result") or {}
    markets: list[Market] = []
    for row in result.get("list", []) or []:
        status = row.get("status")
        if status and str(status).upper() not in {"TRADING"}:
            continue
        if row.get("quoteCoin") != "USDT":
            continue
        base = row.get("baseCoin")
        quote = row.get("quoteCoin")
        sym = row.get("symbol")
        if not base or not quote or not sym:
            continue
        markets.append(Market(exchange="bybit", symbol=_canonical(base, quote), raw=str(sym)))
    return markets


def fetch_bitget_usdt_perp(*, base_url: str = "https://api.bitget.com") -> list[Market]:
    # Bitget MIX USDT Perp contracts list
    # Endpoint may vary by version; try v2 first, fallback to v1.
    markets: list[Market] = []
    try:
        payload = _http_get(
            f"{base_url.rstrip('/')}/api/v2/mix/market/contracts",
            params={"productType": "USDT-FUTURES"},
        )
        data = payload.get("data") or []
        for row in data:
            if (row.get("quoteCoin") or "").upper() != "USDT":
                continue
            if (row.get("status") or "").upper() not in {"NORMAL", "TRADING"} and row.get("status") is not None:
                continue
            base = row.get("baseCoin")
            quote = row.get("quoteCoin")
            sym = row.get("symbol") or row.get("symbolName")
            if not base or not quote or not sym:
                continue
            markets.append(Market(exchange="bitget", symbol=_canonical(base, quote), raw=str(sym)))
        if markets:
            return markets
    except Exception:
        pass

    payload = _http_get(
        f"{base_url.rstrip('/')}/api/mix/v1/market/contracts",
        params={"productType": "umcbl"},
    )
    data = payload.get("data") or []
    for row in data:
        base = row.get("baseCoin")
        quote = row.get("quoteCoin")
        sym = row.get("symbol")
        if not base or not quote or not sym:
            continue
        if str(quote).upper() != "USDT":
            continue
        markets.append(Market(exchange="bitget", symbol=_canonical(base, quote), raw=str(sym)))
    return markets


def fetch_hyperliquid_perps(*, base_url: str = "https://api.hyperliquid.xyz") -> list[Market]:
    # Hyperliquid meta endpoint is POST /info {"type":"meta"}.
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(f"{base_url.rstrip('/')}/info", json={"type": "meta"})
        resp.raise_for_status()
        payload = resp.json()

    universe = payload.get("universe") or []
    markets: list[Market] = []
    for row in universe:
        coin = row.get("name")
        if not coin:
            continue
        # Hyperliquid perps are quoted in USD; we still present as COIN/USD for canonical.
        markets.append(Market(exchange="hyperliquid", symbol=_canonical(str(coin), "USD"), raw=str(coin)))
    return markets


FETCHERS: dict[str, Callable[[], list[Market]]] = {
    "binance": lambda: fetch_binance_usdt_perp(),
    "okx": lambda: fetch_okx_swap(),
    "bybit": lambda: fetch_bybit_usdt_perp(),
    "bitget": lambda: fetch_bitget_usdt_perp(),
    "hyperliquid": lambda: fetch_hyperliquid_perps(),
}


class MarketCache:
    def __init__(self, *, ttl_sec: int = 600) -> None:
        self.ttl_sec = ttl_sec
        self._cache: dict[str, tuple[float, list[Market]]] = {}

    def get(self, exchange: str) -> Optional[list[Market]]:
        key = exchange.lower()
        item = self._cache.get(key)
        if not item:
            return None
        ts, data = item
        if (time.time() - ts) > self.ttl_sec:
            self._cache.pop(key, None)
            return None
        return data

    def set(self, exchange: str, markets: list[Market]) -> None:
        self._cache[exchange.lower()] = (time.time(), markets)
