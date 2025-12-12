#!/usr/bin/env python3
"""
简化的 Paradex WebSocket 测试
测试订单和持仓实时推送
"""

import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, 'src')

from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ws_test")

load_dotenv()


async def on_orders(channel, message):
    """订单更新回调"""
    logger.info("📨 [ORDERS 推送] %s", message)


async def on_positions(channel, message):
    """持仓更新回调"""
    logger.info("📊 [POSITIONS 推送] %s", message)


async def main():
    """主测试流程"""
    print("\n" + "=" * 70)
    print("  Paradex WebSocket 实时推送测试")
    print("=" * 70)

    # 初始化客户端
    env_str = os.getenv("PARADEX_ENV", "prod").lower()
    l2_key = os.environ["PARADEX_L2_PRIVATE_KEY"]
    account_addr = os.environ["PARADEX_ACCOUNT_ADDRESS"]

    client = Paradex(
        env=env_str,
        l2_private_key=l2_key,
        l1_address=account_addr,
    )
    logger.info("✅ Paradex 初始化完成，环境=%s", env_str)

    # 连接 WebSocket
    logger.info("🔌 连接 WebSocket...")
    await client.ws_client.connect()
    logger.info("✅ WebSocket 已连接")

    # 订阅订单更新（需要指定 market 参数）
    await client.ws_client.subscribe(
        ParadexWebsocketChannel.ORDERS,
        callback=on_orders,
        params={"market": "ALL"}  # 订阅所有市场的订单
    )
    logger.info("📡 已订阅 ORDERS 频道（所有市场）")

    # 订阅持仓更新
    await client.ws_client.subscribe(
        ParadexWebsocketChannel.POSITIONS,
        callback=on_positions,
    )
    logger.info("📡 已订阅 POSITIONS 频道")

    print("\n" + "=" * 70)
    print("  WebSocket 已就绪，等待推送...")
    print("  提示：去 Paradex 网站下单或修改持仓，观察实时推送")
    print("  按 Ctrl+C 退出")
    print("=" * 70)

    # 保持连接
    try:
        await asyncio.sleep(300)  # 运行5分钟
    except asyncio.CancelledError:
        logger.info("🔄 任务被取消")

    # 关闭连接
    await client.ws_client.close()
    logger.info("👋 WebSocket 已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 用户中断测试")
    except Exception as e:
        logger.exception("❌ 测试出错: %s", e)
