#!/usr/bin/env python3
"""财报双向突破挂单机器人（Bitget USDT 永续）。

时间线（默认北京时间）:
    03:50  拉盘尾 K 线 → 算区间 → 挂多空两张 stop-limit 计划委托
    04:00  财报数字公布，某一边被触发
    触发即  WS 推送成交 → 立刻撤掉另一张（REST 轮询同时兜底）
    05:30  收工：撤掉所有未触发的挂单

默认 DRY RUN，只打印不下单。确认无误后加 --live 才会真实下单。
"""
import argparse
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bitget_api import BitgetREST, BitgetError, Rules   # noqa: E402
from ws_client import PrivateWS                          # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
REPO_ROOT = Path(__file__).resolve().parent.parent


def log(msg):
    print(f"[{datetime.now(TZ):%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- 状态机

class Session:
    """一次财报交易的全部状态。两条监控路径共用，靠锁保证撤单只发生一次。"""

    def __init__(self, api, symbol, dry_run):
        self.api = api
        self.symbol = symbol
        self.dry_run = dry_run
        self.orders = {}          # side -> orderId
        self.lock = threading.Lock()
        self.filled_side = None
        self.done = threading.Event()

    def on_fill(self, side, source):
        """成交回调。WS 和 REST 轮询都会调，必须幂等。"""
        with self.lock:
            if self.filled_side:
                return
            self.filled_side = side
        other = "sell" if side == "buy" else "buy"
        log(f"*** {side.upper()} 成交（来源 {source}）→ 立即撤销 {other.upper()} 挂单")
        self.cancel(other)

    def cancel(self, side):
        oid = self.orders.pop(side, None)
        if not oid:
            return
        if self.dry_run:
            log(f"  [DRY] 撤单 {side} {oid}")
            return
        for attempt in range(4):
            try:
                self.api.cancel_plan_order(symbol=self.symbol, order_id=oid)
                log(f"  已撤销 {side} 挂单 {oid}")
                return
            except BitgetError as e:
                if "not exist" in (e.msg or "").lower():
                    log(f"  {side} 挂单已不存在（可能同时被触发）")
                    return
                log(f"  撤单失败({attempt + 1}/4): {e}")
                time.sleep(0.3)
        log(f"  !! {side} 挂单撤销失败，请立刻手动检查")

    def cancel_all(self):
        for side in list(self.orders):
            self.cancel(side)


# ---------------------------------------------------------------- 计算

def compute_levels(api, rules, window_min, buffer_pct, slip_pct):
    bars = api.candles(rules.symbol, "5m", max(1, window_min // 5))
    if not bars:
        sys.exit(f"{rules.symbol} 拿不到 K 线")

    high = max(Decimal(b[2]) for b in bars)
    low = min(Decimal(b[3]) for b in bars)
    mid = (high + low) / 2
    buf = Decimal(str(buffer_pct)) / 100
    slip = Decimal(str(slip_pct)) / 100

    return {
        "high": rules.px(high), "low": rules.px(low), "mid": rules.px(mid),
        "buy_trigger": rules.px(high * (1 + buf)),
        "buy_limit": rules.px(high * (1 + buf) * (1 + slip)),
        "sell_trigger": rules.px(low * (1 - buf)),
        "sell_limit": rules.px(low * (1 - buf) * (1 - slip)),
        "stop": rules.px(mid),
    }


def compute_size(rules, lv, margin, price):
    notional = Decimal(str(margin)) * Decimal(str(lv))
    size = rules.qty(notional / price)
    if size < rules.min_qty:
        sys.exit(f"仓位太小: {size} < 最小 {rules.min_qty}。提高 --margin 或 --leverage")
    if size * price < rules.min_usdt:
        sys.exit(f"名义价值 {size * price:.2f}U < 最小 {rules.min_usdt}U。提高 --margin")
    return size, notional


# ---------------------------------------------------------------- 主流程

def wait_until(target_hm):
    if not target_hm:
        return
    hh, mm = (int(x) for x in target_hm.split(":"))
    now = datetime.now(TZ)
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    secs = (target - now).total_seconds()
    log(f"等待到 {target:%m-%d %H:%M}（还有 {secs / 3600:.1f} 小时）")
    while (remain := (target - datetime.now(TZ)).total_seconds()) > 0:
        time.sleep(min(remain, 30))


def preflight(api, symbol, leverage, dry_run):
    """单向持仓是关键安全措施：万一没来得及撤单，反向触发只会平仓不会反向开仓。"""
    if dry_run:
        log("[DRY] 跳过账户设置（单向持仓 / 全仓 / 杠杆）")
        return
    for label, fn in (
        ("单向持仓", lambda: api.set_position_mode("one_way_mode")),
        ("全仓保证金", lambda: api.set_margin_mode(symbol, "crossed")),
        (f"{leverage}x 杠杆", lambda: api.set_leverage(symbol, leverage)),
    ):
        try:
            fn()
            log(f"  已设置 {label}")
        except BitgetError as e:
            log(f"  设置{label}失败（可能已是该状态）: {e.msg}")


def monitor(sess, api, cutoff_hm):
    """REST 轮询兜底。WS 掉线时这条路必须还能发现成交。"""
    hh, mm = (int(x) for x in cutoff_hm.split(":"))
    now = datetime.now(TZ)
    cutoff = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if cutoff <= now:
        cutoff += timedelta(days=1)
    if sess.dry_run:
        log(f"[DRY] 实盘时会在这里轮询到 {cutoff:%H:%M}：每 2 秒查一次持仓和挂单，")
        log("[DRY] 一旦发现成交立刻撤另一单（WS 推送更快，这条是兜底）。演练结束。")
        sess.cancel_all()
        return

    log(f"开始监控，收工时间 {cutoff:%H:%M}")

    last_report = 0
    while datetime.now(TZ) < cutoff and not sess.done.is_set():
        try:
            pos = api.position(sess.symbol)
            if pos and not sess.filled_side:
                side = "buy" if pos.get("holdSide") == "long" else "sell"
                sess.on_fill(side, "REST轮询")
            if pos and time.time() - last_report > 60:
                log(f"  持仓 {pos.get('holdSide')} {pos.get('total')} @ "
                    f"{pos.get('openPriceAvg')}  未实现 {pos.get('unrealizedPL')}U")
                last_report = time.time()
            if sess.filled_side and not pos:
                log("持仓已平（止损或止盈触发），收工")
                break
        except BitgetError as e:
            log(f"轮询异常: {e}")
        except Exception as e:
            log(f"轮询未知异常: {e!r}")
        time.sleep(2)

    log("收工，清理剩余挂单")
    sess.cancel_all()


def main():
    p = argparse.ArgumentParser(description="Bitget 财报双向突破机器人")
    p.add_argument("symbol", nargs="?", default="AMAT", help="标的，如 AMAT / NVDA")
    p.add_argument("--at", default="03:50", help="挂单时间 HH:MM，北京时间")
    p.add_argument("--now", action="store_true", help="不等待，立刻执行")
    p.add_argument("--window", type=int, default=30, help="盘尾回看分钟数")
    p.add_argument("--buffer", type=float, default=0.8, help="防插针缓冲 %%")
    p.add_argument("--slip", type=float, default=0.4, help="限价单容许滑点 %%")
    p.add_argument("--leverage", type=int, default=2, help="杠杆倍数")
    p.add_argument("--margin", type=float, default=50, help="单边保证金 USDT")
    p.add_argument("--cutoff", default="05:30", help="收工时间 HH:MM")
    p.add_argument("--live", action="store_true", help="真实下单（默认只演练）")
    args = p.parse_args()

    load_dotenv(REPO_ROOT / ".env")            # 用 perp-tools 根目录的 .env
    key = os.getenv("BITGET_API_KEY", "")
    secret = os.getenv("BITGET_API_SECRET", "")
    passphrase = os.getenv("BITGET_PASSPHRASE", "")
    dry_run = not args.live

    if args.live and not (key and secret and passphrase):
        sys.exit(f"--live 需要在 {REPO_ROOT / '.env'} 里配好 "
                 "BITGET_API_KEY / BITGET_API_SECRET / BITGET_PASSPHRASE")

    api = BitgetREST(key, secret, passphrase)
    symbol = args.symbol.upper()
    if not symbol.endswith("USDT"):
        symbol += "USDT"

    try:
        info = api.contract(symbol)
    except BitgetError as e:
        sys.exit(f"查不到 {symbol}: {e.msg}。确认标的在 Bitget USDT 永续里存在")
    if info["symbolStatus"] != "normal":
        sys.exit(f"{symbol} 当前状态 {info['symbolStatus']}，不可交易")
    rules = Rules(info)
    if args.leverage > rules.max_lever:
        sys.exit(f"杠杆 {args.leverage}x 超过上限 {rules.max_lever}x")

    log(f"{'=' * 56}")
    log(f"标的 {symbol}   杠杆 {args.leverage}x   单边保证金 {args.margin}U")
    log(f"模式 {'*** 实盘 ***' if args.live else 'DRY RUN（只打印，不下单）'}")
    log(f"{'=' * 56}")

    if not args.now:
        wait_until(args.at)

    lv = compute_levels(api, rules, args.window, args.buffer, args.slip)
    last = api.last_price(symbol)
    size, notional = compute_size(rules, args.leverage, args.margin, lv["buy_trigger"])

    rng = (lv["high"] - lv["low"]) / lv["mid"] * 100
    log(f"现价 {last}   盘尾{args.window}分钟区间 {lv['low']} — {lv['high']}（{rng:.2f}%）")
    log(f"  多单  触发 {lv['buy_trigger']}  限价 {lv['buy_limit']}  止损 {lv['stop']}")
    log(f"  空单  触发 {lv['sell_trigger']}  限价 {lv['sell_limit']}  止损 {lv['stop']}")
    log(f"  数量 {size}（名义 {notional}U）")

    risk = abs(lv["buy_trigger"] - lv["stop"]) / lv["buy_trigger"] * 100
    log(f"  名义风险 {risk:.2f}% × {args.leverage}x = 账户 {risk * args.leverage:.2f}%"
        f"（实际成交价滑出触发价越多，真实风险越大）")

    preflight(api, symbol, args.leverage, dry_run)

    sess = Session(api, symbol, dry_run)

    ws = None
    if not dry_run:
        def on_order(o):
            if o.get("instId") != symbol:
                return
            if o.get("status") in ("filled", "partially_filled"):
                sess.on_fill(o.get("side"), "WS")
        ws = PrivateWS(key, secret, passphrase, on_order, log).start()
        ws.connected.wait(timeout=10)
        if not ws.connected.is_set():
            log("!! WS 未能在 10 秒内订阅成功，将只靠 REST 轮询兜底")

    stamp = int(time.time())
    for side, trig, lim in (("buy", lv["buy_trigger"], lv["buy_limit"]),
                            ("sell", lv["sell_trigger"], lv["sell_limit"])):
        if dry_run:
            log(f"  [DRY] 挂 {side} 触发 {trig} 限价 {lim} 止损 {lv['stop']} 数量 {size}")
            sess.orders[side] = f"dry-{side}"
            continue
        try:
            r = api.place_plan_order(
                symbol=symbol, side=side, size=size,
                trigger_price=trig, limit_price=lim, stop_loss=lv["stop"],
                client_oid=f"er-{stamp}-{side}",
            )
            sess.orders[side] = r["orderId"]
            log(f"  已挂 {side} 单 {r['orderId']}  触发 {trig} 限价 {lim}")
        except BitgetError as e:
            log(f"  !! {side} 挂单失败: {e}")
            if sess.orders:
                log("  已挂的单全部撤回，避免单边裸露")
                sess.cancel_all()
            sys.exit(1)

    try:
        monitor(sess, api, args.cutoff)
    except KeyboardInterrupt:
        log("手动中断，清理挂单")
        sess.cancel_all()
    finally:
        if ws:
            ws.stop()
    log("结束")


if __name__ == "__main__":
    main()
