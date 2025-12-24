from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
    def __init__(self, base_url: str, creds: OKXCredentials) -> None:
        self.base_url = base_url.rstrip("/")
        self.creds = creds
        self.session = requests.Session()

    def _sign(self, ts: str, method: HttpMethod, path: str, body: str) -> str:
        prehash = f"{ts}{method}{path}{body}".encode("utf-8")
        digest = hmac.new(self.creds.api_secret.encode("utf-8"), prehash, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")

    def request(self, method: HttpMethod, path: str, *, params: dict[str, str] | None = None, json_body: dict[str, Any] | None = None) -> Any:
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
        return self.request("POST", "/api/v5/trade/order", json_body=payload)

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
        
        return self.request("POST", "/api/v5/trade/order-algo", json_body=payload)

    def get_instrument_info(self, *, inst_id: str) -> dict[str, Any] | None:
        """Get instrument information including contract value (ctVal)."""
        try:
            payload = self.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP", "instId": inst_id})
            data = (payload.get("data") or [])
            return data[0] if data else None
        except Exception:
            return None
