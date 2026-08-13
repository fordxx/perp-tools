"""Bitget V2 私有 WebSocket —— 只订阅合约订单频道，用于秒级感知成交。

WS 是"快"的那条路，不是"可靠"的那条路。掉线、丢包、鉴权过期都可能发生，
所以 bot.py 里必须同时跑 REST 轮询兜底，两条路都调用同一个幂等回调。
"""
import base64
import hashlib
import hmac
import json
import threading
import time

import websocket

WS_URL = "wss://ws.bitget.com/v2/ws/private"


class PrivateWS:
    def __init__(self, key, secret, passphrase, on_order, log=print):
        self.key = key
        self.secret = secret
        self.passphrase = passphrase
        self.on_order = on_order
        self.log = log
        self.app = None
        self.thread = None
        self.connected = threading.Event()
        self._stop = False

    def _login_args(self):
        ts = str(int(time.time()))
        msg = ts + "GET" + "/user/verify"
        sign = base64.b64encode(
            hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).digest()
        ).decode()
        return [{"apiKey": self.key, "passphrase": self.passphrase,
                 "timestamp": ts, "sign": sign}]

    # ---------- 回调 ----------

    def _on_open(self, ws):
        self.log("WS 已连接，登录中")
        ws.send(json.dumps({"op": "login", "args": self._login_args()}))

    def _on_message(self, ws, raw):
        if raw == "pong":
            return
        try:
            msg = json.loads(raw)
        except ValueError:
            return

        event = msg.get("event")
        if event == "login":
            self.log("WS 登录成功，订阅 orders 频道")
            ws.send(json.dumps({"op": "subscribe", "args": [
                {"instType": "USDT-FUTURES", "channel": "orders", "instId": "default"}
            ]}))
            return
        if event == "subscribe":
            self.connected.set()
            self.log("WS 订阅成功")
            return
        if event == "error":
            self.log(f"WS 错误: {msg}")
            return

        if msg.get("arg", {}).get("channel") == "orders":
            for order in msg.get("data") or []:
                try:
                    self.on_order(order)
                except Exception as e:                      # 回调异常不能杀掉 WS
                    self.log(f"订单回调异常: {e!r}")

    def _on_error(self, ws, err):
        self.log(f"WS 异常: {err!r}")

    def _on_close(self, ws, code, reason):
        self.connected.clear()
        if not self._stop:
            self.log(f"WS 断开 ({code}) — 自动重连中")

    # ---------- 生命周期 ----------

    def start(self):
        def run():
            while not self._stop:
                self.app = websocket.WebSocketApp(
                    WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                try:
                    self.app.run_forever(ping_interval=25, ping_payload="ping")
                except Exception as e:
                    self.log(f"WS run_forever 异常: {e!r}")
                if not self._stop:
                    time.sleep(3)

        self.thread = threading.Thread(target=run, daemon=True, name="bitget-ws")
        self.thread.start()
        return self

    def stop(self):
        self._stop = True
        if self.app:
            try:
                self.app.close()
            except Exception:
                pass
