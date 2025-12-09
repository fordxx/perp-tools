#!/usr/bin/env python3
"""
Paradex WebSocket + 平仓 + 本地止盈止损 Demo

功能：
- 连接 SDK（用 L2 私钥认证）
- 打开 WebSocket：
    - 订阅 ORDERS / POSITIONS
- 提供三个 helper：
    - close_position() : 一键按当前仓位方向反向市价平仓
    - place_market_order() : 下市价单
    - run_bracket_loop() : 本地止盈/止损循环（简单版）

说明：
- 不依赖你现有的 paradex.py，可以单独跑
- 等你验证没问题，再考虑合并到 core 代码里
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional, Literal

from dotenv import load_dotenv

from paradex_py import Paradex
from paradex_py.environment import Environment
from paradex_py.signer import PrivateKeySigner
from paradex_py.api.models.order import Order, OrderType, OrderSide, TimeInForce
from paradex_py.api.ws_client import ParadexWebsocketChannel

# -------------------- 基础配置 --------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("paradex_ws_demo")

load_dotenv()  # 读取 .env


def get_env() -> Environment:
    env_str = os.getenv("PARADEX_ENV", "PROD").upper()
    if env_str == "TESTNET":
        return Environment.TESTNET
    return Environment.PROD


def build_paradex() -> Paradex:
    env = get_env()
    l2_key = os.environ["PARADEX_L2_PRIVATE_KEY"]
    account_addr = os.environ["PARADEX_ACCOUNT_ADDRESS"]

    signer = PrivateKeySigner(l2_key)
    client = Paradex(env=env, signer=signer, account_address=account_addr)
    logger.info("Paradex SDK 初始化完成，环境=%s", env.value)
    return client


# 你自己的交易对 → Paradex 市场名字
# 之前我们一直用 ETH/USDT，对应官方市场一般是 ETH-USD-PERP
SYMBOL = "ETH/USDT"
MARKET = os.getenv("PARADEX_MARKET", "ETH-USD-PERP")


@dataclass
class BracketConfig:
    symbol: str
    size: float                               # 下单数量（张数）
    side: Literal["buy", "sell"]              # 开仓方向
    take_profit: Optional[float] = None       # 触发平仓价格（盈利）
    stop_loss: Optional[float] = None         # 触发平仓价格（止损）
    poll_interval: float = 1.0                # 价格轮询间隔（秒）


# -------------------- WebSocket 管理 --------------------


class ParadexWsSession:
    """
    只做三件事：
    - 连接 WebSocket
    - 订阅 ORDERS / POSITIONS
    - 把推送打印出来（你以后可以改为丢进队列 or callback）
    """

    def __init__(self, client: Paradex):
        self.client = client
        self.ws = client.ws_client
        self._connected = False

    async def start(self) -> None:
        if self._connected:
            return
        logger.info("连接 WebSocket ...")
        await self.ws.connect()

        await self.ws.subscribe(
            ParadexWebsocketChannel.ORDERS,
            callback=self._on_orders,
        )
        await self.ws.subscribe(
            ParadexWebsocketChannel.POSITIONS,
            callback=self._on_positions,
        )
        self._connected = True
        logger.info("WebSocket 订阅 ORDERS / POSITIONS 完成")

    async def close(self) -> None:
        if not self._connected:
            return
        await self.ws.close()
        self._connected = False
        logger.info("WebSocket 已关闭")

    # ---- 回调 ----

    async def _on_orders(self, channel, message):
        logger.info("WS[ORDERS]: %s", message)

    async def _on_positions(self, channel, message):
        # 这里面就能看到 avgEntryPrice，而不是 0
        logger.info("WS[POSITIONS]: %s", message)


# -------------------- 下单 & 平仓 helper --------------------


async def place_market_order(
    client: Paradex,
    symbol: str,
    size: float,
    side: Literal["buy", "sell"],
) -> dict:
    """
    下一个简单的市价单。
    """
    side_enum = OrderSide.BUY if side == "buy" else OrderSide.SELL

    order = Order(
        market=MARKET,
        price=None,  # 市价单 price=None
        size=size,
        side=side_enum,
        type=OrderType.MARKET,
        time_in_force=TimeInForce.FILL_OR_KILL,
        reduce_only=False,
        client_order_id=None,
    )

    res = client.submit_order(order)
    logger.info("下市价单: %s %s size=%s, 结果=%s", symbol, side, size, res)
    return res


async def close_position(
    client: Paradex,
    symbol: str,
    market: str,
) -> Optional[dict]:
    """
    一键按当前仓位大小反向市价平仓。
    - 如果没有仓位，直接返回 None
    """
    pos_res = client.fetch_positions()  # {'results': [...]}
    positions = pos_res.get("results", [])

    pos = None
    for p in positions:
        if p.get("market") == market and float(p.get("size", 0)) != 0:
            pos = p
            break

    if not pos:
        logger.info("当前没有 %s 仓位，无需平仓", symbol)
        return None

    side = pos["side"]  # "BUY" 或 "SELL"
    size = abs(float(pos["size"]))
    logger.info(
        "检测到仓位: market=%s side=%s size=%s avgEntryPrice=%s",
        market,
        side,
        size,
        pos.get("avgEntryPrice"),
    )

    close_side = "sell" if side.upper() == "BUY" else "buy"
    return await place_market_order(client, symbol, size, close_side)


# -------------------- 本地止盈/止损循环 --------------------


async def fetch_last_price(client: Paradex, market: str) -> float:
    """
    用 REST 拉一次 BBO 当作“最新价”。
    以后你可以改成 WS BBO。
    """
    bbo = client.fetch_bbo(market)
    best_bid = float(bbo["bestBidPrice"])
    best_ask = float(bbo["bestAskPrice"])
    mid = (best_bid + best_ask) / 2
    return mid


async def run_bracket_loop(client: Paradex, cfg: BracketConfig) -> None:
    """
    非挂单，而是“盯盘式”的本地止盈/止损：
    - 在 while True 里读取价格（BBO mid）
    - 到达止盈或止损价 → 调 close_position() 平仓
    """
    logger.info(
        "启动本地止盈/止损监控: %s side=%s size=%s TP=%s SL=%s",
        cfg.symbol,
        cfg.side,
        cfg.size,
        cfg.take_profit,
        cfg.stop_loss,
    )

    while True:
        price = await fetch_last_price(client, MARKET)
        logger.info("当前价格: %.2f", price)

        triggered = False

        if cfg.take_profit is not None:
            if cfg.side == "buy" and price >= cfg.take_profit:
                logger.info("价格达到止盈 %.2f，开始平仓 ...", cfg.take_profit)
                triggered = True
            elif cfg.side == "sell" and price <= cfg.take_profit:
                logger.info("价格达到止盈 %.2f，开始平仓 ...", cfg.take_profit)
                triggered = True

        if not triggered and cfg.stop_loss is not None:
            if cfg.side == "buy" and price <= cfg.stop_loss:
                logger.info("价格跌破止损 %.2f，开始平仓 ...", cfg.stop_loss)
                triggered = True
            elif cfg.side == "sell" and price >= cfg.stop_loss:
                logger.info("价格突破止损 %.2f，开始平仓 ...", cfg.stop_loss)
                triggered = True

        if triggered:
            await close_position(client, cfg.symbol, MARKET)
            logger.info("止盈/止损执行完毕，退出监控循环")
            return

        await asyncio.sleep(cfg.poll_interval)


# -------------------- 主流程 --------------------


async def main():
    client = build_paradex()

    # 1) 打印一次账户 & 持仓，顺便确认 avgEntryPrice 修复好了
    summary = client.fetch_account_summary()
    logger.info("Account Summary: %s", summary)

    positions = client.fetch_positions()
    logger.info("Positions: %s", positions)

    # 2) 启动 WebSocket（后台打印 ORDERS / POSITIONS）
    ws = ParadexWsSession(client)
    await ws.start()

    # 3) 下一个测试仓位（你可以先手动开好一个，再只跑 bracket_loop）
    size = 0.004
    side = "buy"  # or "sell"
    await place_market_order(client, SYMBOL, size, side)

    # 4) 启动本地止盈 / 止损监控
    cfg = BracketConfig(
        symbol=SYMBOL,
        size=size,
        side=side,
        # 下面两个价格你自己改成合理的水平（美元）
        take_profit=None,      # 例如 3050.0
        stop_loss=None,        # 例如 2900.0
        poll_interval=2.0,
    )

    await run_bracket_loop(client, cfg)

    # 5) 结束后关闭 WebSocket
    await ws.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户手动中断")
    except Exception as e:
        logger.exception("运行出错: %s", e)
