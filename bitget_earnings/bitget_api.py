"""Bitget V2 合约 REST 客户端（只包含本策略要用的接口）。"""
import base64
import hashlib
import hmac
import json
import time
from decimal import Decimal, ROUND_DOWN

import requests

BASE = "https://api.bitget.com"
PRODUCT = "USDT-FUTURES"


class BitgetError(RuntimeError):
    def __init__(self, code, msg, path):
        super().__init__(f"[{code}] {msg}  ({path})")
        self.code = code
        self.msg = msg


class BitgetREST:
    def __init__(self, key="", secret="", passphrase="", timeout=10):
        self.key = key
        self.secret = secret
        self.passphrase = passphrase
        self.timeout = timeout
        self.s = requests.Session()

    # ---------- 底层 ----------

    def _sign(self, ts, method, path, body):
        msg = f"{ts}{method}{path}{body}"
        digest = hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def _request(self, method, path, params=None, body=None, auth=True):
        method = method.upper()
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            path = f"{path}?{qs}"
        payload = json.dumps(body, separators=(",", ":")) if body else ""

        headers = {"Content-Type": "application/json", "locale": "en-US"}
        if auth:
            if not (self.key and self.secret and self.passphrase):
                raise BitgetError("no-key", "缺少 API Key/Secret/Passphrase", path)
            ts = str(int(time.time() * 1000))
            headers.update({
                "ACCESS-KEY": self.key,
                "ACCESS-SIGN": self._sign(ts, method, path, payload),
                "ACCESS-TIMESTAMP": ts,
                "ACCESS-PASSPHRASE": self.passphrase,
            })

        r = self.s.request(method, BASE + path, headers=headers,
                           data=payload or None, timeout=self.timeout)
        try:
            out = r.json()
        except ValueError:
            raise BitgetError(r.status_code, r.text[:200], path)
        if out.get("code") != "00000":
            raise BitgetError(out.get("code"), out.get("msg"), path)
        return out.get("data")

    # ---------- 公开行情 ----------

    def contract(self, symbol):
        d = self._request("GET", "/api/v2/mix/market/contracts",
                          {"productType": PRODUCT, "symbol": symbol}, auth=False)
        if not d:
            raise BitgetError("no-symbol", f"{symbol} 不存在或未上线", "contracts")
        return d[0]

    def candles(self, symbol, granularity="5m", limit=20):
        return self._request("GET", "/api/v2/mix/market/candles",
                             {"symbol": symbol, "productType": PRODUCT,
                              "granularity": granularity, "limit": limit}, auth=False)

    def last_price(self, symbol):
        d = self._request("GET", "/api/v2/mix/market/ticker",
                          {"symbol": symbol, "productType": PRODUCT}, auth=False)
        return Decimal(d[0]["lastPr"])

    # ---------- 账户 ----------

    def set_position_mode(self, mode="one_way_mode"):
        return self._request("POST", "/api/v2/mix/account/set-position-mode",
                             body={"productType": PRODUCT, "posMode": mode})

    def set_leverage(self, symbol, leverage, margin_coin="USDT"):
        return self._request("POST", "/api/v2/mix/account/set-leverage",
                             body={"symbol": symbol, "productType": PRODUCT,
                                   "marginCoin": margin_coin, "leverage": str(leverage)})

    def set_margin_mode(self, symbol, mode="crossed", margin_coin="USDT"):
        return self._request("POST", "/api/v2/mix/account/set-margin-mode",
                             body={"symbol": symbol, "productType": PRODUCT,
                                   "marginCoin": margin_coin, "marginMode": mode})

    def available_usdt(self):
        d = self._request("GET", "/api/v2/mix/account/account",
                          {"symbol": "BTCUSDT", "productType": PRODUCT, "marginCoin": "USDT"})
        return Decimal(str(d.get("available", "0")))

    # ---------- 计划委托 ----------

    def place_plan_order(self, *, symbol, side, size, trigger_price, limit_price,
                         stop_loss=None, margin_mode="crossed", margin_coin="USDT",
                         client_oid=None, trigger_type="fill_price"):
        body = {
            "planType": "normal_plan",
            "symbol": symbol,
            "productType": PRODUCT,
            "marginMode": margin_mode,
            "marginCoin": margin_coin,
            "size": str(size),
            "price": str(limit_price),
            "triggerPrice": str(trigger_price),
            "triggerType": trigger_type,
            "side": side,
            "orderType": "limit",
        }
        if stop_loss is not None:
            body["presetStopLossPrice"] = str(stop_loss)
        if client_oid:
            body["clientOid"] = client_oid
        return self._request("POST", "/api/v2/mix/order/place-plan-order", body=body)

    def cancel_plan_order(self, *, symbol, order_id):
        return self._request("POST", "/api/v2/mix/order/cancel-plan-order",
                             body={"orderId": order_id, "symbol": symbol,
                                   "productType": PRODUCT, "planType": "normal_plan"})

    def pending_plan_orders(self, symbol=None):
        d = self._request("GET", "/api/v2/mix/order/orders-plan-pending",
                          {"productType": PRODUCT, "planType": "normal_plan",
                           "symbol": symbol})
        return (d or {}).get("entrustedList") or []

    def position(self, symbol, margin_coin="USDT"):
        d = self._request("GET", "/api/v2/mix/position/single-position",
                          {"symbol": symbol, "productType": PRODUCT,
                           "marginCoin": margin_coin})
        for p in (d or []):
            if Decimal(str(p.get("total", "0") or "0")) != 0:
                return p
        return None

    def flash_close(self, symbol, hold_side=None):
        body = {"symbol": symbol, "productType": PRODUCT}
        if hold_side:
            body["holdSide"] = hold_side
        return self._request("POST", "/api/v2/mix/order/close-positions", body=body)


# ---------- 精度工具 ----------

class Rules:
    """从合约配置里解出下单精度规则。"""

    def __init__(self, info):
        self.symbol = info["symbol"]
        self.price_place = int(info["pricePlace"])
        self.price_end_step = int(info["priceEndStep"])
        self.vol_place = int(info["volumePlace"])
        self.min_qty = Decimal(info["minTradeNum"])
        self.min_usdt = Decimal(info["minTradeUSDT"])
        self.max_lever = int(info["maxLever"])
        self.tick = Decimal(self.price_end_step) / (Decimal(10) ** self.price_place)
        self.qty_step = Decimal(1) / (Decimal(10) ** self.vol_place)

    def px(self, value):
        """把价格对齐到 tick size。"""
        v = Decimal(str(value))
        return (v / self.tick).quantize(Decimal(1), rounding=ROUND_DOWN) * self.tick

    def qty(self, value):
        v = Decimal(str(value))
        return (v / self.qty_step).quantize(Decimal(1), rounding=ROUND_DOWN) * self.qty_step
