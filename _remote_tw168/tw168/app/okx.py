from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import requests


HttpMethod = Literal["GET", "POST"]


def _iso_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class OKXCredentials:
    api_key: str
    api_secret: str
    passphrase: str


class OKXClient:
    def __init__(self, base_url: str, creds: OKXCredentials, *, enable_rate_limit: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.creds = creds
        self.enable_rate_limit = enable_rate_limit
        self.logger = logging.getLogger("uvicorn.error")

        # Configure session with connection pooling
        self.session = requests.Session()

        # Use HTTPAdapter for connection pooling
        from requests.adapters import HTTPAdapter

        adapter = HTTPAdapter(
            pool_connections=20,  # 连接池大小
            pool_maxsize=20,      # 最大连接数
            max_retries=0,        # 我们自己处理重试
            pool_block=False      # 非阻塞
        )

        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _sign(self, ts: str, method: HttpMethod, path: str, body: str) -> str:
        prehash = f"{ts}{method}{path}{body}".encode("utf-8")
        digest = hmac.new(self.creds.api_secret.encode("utf-8"), prehash, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")

    def request(self, method: HttpMethod, path: str, *, params: dict[str, str] | None = None, json_body: dict[str, Any] | None = None, is_trading: bool = False, max_retries: int = 3) -> Any:
        # Apply rate limiting if enabled
        if self.enable_rate_limit:
            try:
                from app.rate_limiter import acquire_okx_market_sync, acquire_okx_trading_sync
                acquired = acquire_okx_trading_sync() if is_trading else acquire_okx_market_sync()
                if not acquired:
                    self.logger.warning(
                        "Rate limit timeout for OKX %s request to %s",
                        "trading" if is_trading else "market",
                        path,
                    )
            except Exception as e:
                self.logger.debug("Rate limiter not available: %s", str(e))

        last_exception = None
        for attempt in range(max_retries):
            try:
                ts = _iso_ts()
                body_str = "" if json_body is None else json.dumps(json_body, separators=(",", ":"))

                if params:
                    qs = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
                    path_with_qs = f"{path}?{qs}"
                else:
                    path_with_qs = path

                sign = self._sign(ts, method, path_with_qs, body_str)
                headers = {
                    "OK-ACCESS-KEY": self.creds.api_key,
                    "OK-ACCESS-SIGN": sign,
                    "OK-ACCESS-TIMESTAMP": ts,
                    "OK-ACCESS-PASSPHRASE": self.creds.passphrase,
                    "Content-Type": "application/json",
                }
                url = f"{self.base_url}{path}"
                resp = self.session.request(method, url, params=params, data=body_str if body_str else None, headers=headers, timeout=15)
                resp.raise_for_status()
                return resp.json()
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    import time
                    backoff = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    self.logger.warning(
                        "OKX API %s request failed (attempt %d/%d), retrying in %ds: %s",
                        method, attempt + 1, max_retries, backoff, str(e)
                    )
                    time.sleep(backoff)
                else:
                    self.logger.error("OKX API %s request failed after %d attempts: %s", method, max_retries, str(e))
                    raise
            except requests.exceptions.HTTPError as e:
                # Don't retry on 4xx client errors (except 429 rate limit)
                if e.response is not None and 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    self.logger.error("OKX API client error %s %s: %s", method, path, str(e))
                    raise
                # Retry on 5xx server errors and 429 rate limit
                last_exception = e
                if attempt < max_retries - 1:
                    import time
                    backoff = 2 ** attempt
                    self.logger.warning(
                        "OKX API %s error (attempt %d/%d), retrying in %ds: %s",
                        method, attempt + 1, max_retries, backoff, str(e)
                    )
                    time.sleep(backoff)
                else:
                    self.logger.error("OKX API %s failed after %d attempts: %s", method, max_retries, str(e))
                    raise
            except json.JSONDecodeError as e:
                self.logger.error("OKX API returned invalid JSON for %s %s: %s", method, path, str(e))
                raise

        # Should not reach here, but if we do, raise the last exception
        if last_exception:
            raise last_exception
        raise RuntimeError(f"OKX API request failed unexpectedly for {method} {path}")

    def get_last_price(self, *, inst_id: str) -> float | None:
        payload = self.request("GET", "/api/v5/market/ticker", params={"instId": inst_id})
        data = (payload.get("data") or [])
        if not data:
            return None
        last = data[0].get("last")
        return float(last) if last is not None and last != "" else None

    def get_order(self, *, inst_id: str, cl_ord_id: str) -> dict[str, Any] | None:
        payload = self.request("GET", "/api/v5/trade/order", params={"instId": inst_id, "clOrdId": cl_ord_id})
        data = (payload.get("data") or [])
        return data[0] if data else None

    def get_position(self, *, inst_id: str, pos_side: str) -> dict[str, Any] | None:
        payload = self.request("GET", "/api/v5/account/positions", params={"instId": inst_id})
        for row in payload.get("data") or []:
            if row.get("instId") == inst_id and (row.get("posSide") or "").lower() == pos_side.lower():
                return row
        return None

    def place_order(
        self,
        *,
        inst_id: str,
        td_mode: str,
        side: str,
        pos_side: str,
        ord_type: str,
        sz: str,
        px: str | None,
        cl_ord_id: str,
        sl_trigger_px: str | None,
        tp_trigger_px: str | None,
        reduce_only: bool = False,
    ) -> Any:
        payload: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "posSide": pos_side,
            "ordType": ord_type,
            "sz": sz,
            "clOrdId": cl_ord_id,
        }
        if reduce_only:
            payload["reduceOnly"] = "true"
        if px is not None and ord_type == "limit":
            payload["px"] = px
        if sl_trigger_px is not None or tp_trigger_px is not None:
            attach: dict[str, Any] = {}
            if sl_trigger_px is not None:
                attach["slTriggerPx"] = sl_trigger_px
                attach["slOrdPx"] = "-1"
            if tp_trigger_px is not None:
                attach["tpTriggerPx"] = tp_trigger_px
                attach["tpOrdPx"] = "-1"
            payload["attachAlgoOrds"] = [attach]
        return self.request("POST", "/api/v5/trade/order", json_body=payload, is_trading=True)

    def place_algo_order(
        self,
        *,
        inst_id: str,
        td_mode: str,
        side: str,
        pos_side: str,
        ord_type: str,
        sz: str,
        sl_trigger_px: str | None = None,
        sl_ord_px: str | None = None,
        tp_trigger_px: str | None = None,
        tp_ord_px: str | None = None,
    ) -> Any:
        """Place algorithmic order (stop-loss or take-profit).
        
        Args:
            ord_type: 'conditional' for stop-loss, 'oco' for take-profit
            sl_trigger_px: Stop-loss trigger price
            sl_ord_px: Stop-loss order price ('-1' for market)
            tp_trigger_px: Take-profit trigger price
            tp_ord_px: Take-profit order price ('-1' for market)
        """
        payload: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "posSide": pos_side,
            "ordType": ord_type,
            "sz": sz,
        }
        
        if sl_trigger_px is not None:
            payload["slTriggerPx"] = sl_trigger_px
            payload["slOrdPx"] = sl_ord_px or "-1"
        
        if tp_trigger_px is not None:
            payload["tpTriggerPx"] = tp_trigger_px
            payload["tpOrdPx"] = tp_ord_px or "-1"

        return self.request("POST", "/api/v5/trade/order-algo", json_body=payload, is_trading=True)

    def get_algo_orders(self, *, inst_id: str, ord_type: str = "conditional") -> list[dict[str, Any]]:
        """Get algorithmic orders (stop-loss, take-profit).

        Args:
            inst_id: Instrument ID
            ord_type: Order type - "conditional" (SL/TP), "oco", "trigger", "iceberg", "twap"

        Returns:
            List of algo orders
        """
        try:
            params = {"instId": inst_id, "ordType": ord_type}
            payload = self.request("GET", "/api/v5/trade/orders-algo-pending", params=params, is_trading=True)
            return payload.get("data") or []
        except Exception:
            return []

    def cancel_algo_order(self, *, inst_id: str, algo_id: str) -> Any:
        """Cancel algorithmic order (stop-loss or take-profit).

        Args:
            inst_id: Instrument ID
            algo_id: Algo order ID to cancel
        """
        payload = [{"instId": inst_id, "algoId": algo_id}]
        return self.request("POST", "/api/v5/trade/cancel-algos", json_body=payload, is_trading=True)

    def cancel_order(self, *, inst_id: str, ord_id: str | None = None, cl_ord_id: str | None = None) -> Any:
        """Cancel a normal order (limit or market).

        Args:
            inst_id: Instrument ID
            ord_id: Exchange order ID (optional if cl_ord_id provided)
            cl_ord_id: Client order ID (optional if ord_id provided)
        """
        payload: dict[str, Any] = {"instId": inst_id}
        if ord_id:
            payload["ordId"] = ord_id
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id
        return self.request("POST", "/api/v5/trade/cancel-order", json_body=payload, is_trading=True)

    def get_instrument_info(self, *, inst_id: str) -> dict[str, Any] | None:
        """Get instrument information including contract value (ctVal)."""
        try:
            payload = self.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP", "instId": inst_id})
            data = (payload.get("data") or [])
            return data[0] if data else None
        except Exception:
            return None
