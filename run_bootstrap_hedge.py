#!/usr/bin/env python3
"""
Bootstrap 双交易所对冲系统 - 主程序

目标：验证 Binance + OKX 双交易所对冲最小系统
- 同时市价开仓（对冲）
- 同时市价平仓
- 真实下单、真实成交、真实 PnL

环境变量要求：
- BINANCE_API_KEY, BINANCE_API_SECRET
- OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import logging
from bootstrap.hedge_executor import BootstrapHedgeExecutor, HedgeConfig
from perpbot.exchanges.binance import BinanceClient
from perpbot.exchanges.okx import OKXClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主程序"""
    logger.info("\n")
    logger.info("🚀" * 30)
    logger.info("Bootstrap 双交易所对冲系统")
    logger.info("🚀" * 30)

    # Step 1: 连接交易所
    logger.info("\n" + "=" * 60)
    logger.info("Connecting to Exchanges")
    logger.info("=" * 60)

    try:
        binance = BinanceClient(use_testnet=True)
        binance.connect()

        okx = OKXClient(use_testnet=True)
        okx.connect()

    except Exception as e:
        logger.exception("❌ Failed to connect to exchanges: %s", e)
        logger.error("\n💡 请检查环境变量配置：")
        logger.error("   - BINANCE_API_KEY")
        logger.error("   - BINANCE_API_SECRET")
        logger.error("   - OKX_API_KEY")
        logger.error("   - OKX_API_SECRET")
        logger.error("   - OKX_PASSPHRASE")
        sys.exit(1)

    # Step 2: 检查现有持仓
    logger.info("\n" + "=" * 60)
    logger.info("Checking Existing Positions")
    logger.info("=" * 60)

    config = HedgeConfig(
        symbol="BTC/USDT",
        notional_usdt=300.0,
        max_position_duration_seconds=10.0,
    )

    executor = BootstrapHedgeExecutor(binance, okx, config)
    positions_binance, positions_okx = executor.get_positions()

    if positions_binance or positions_okx:
        logger.warning("⚠️ Found existing positions!")
        logger.warning("Please close all positions before running hedge test")

        response = input("\n是否继续执行对冲测试？(yes/no): ")
        if response.lower() != 'yes':
            logger.info("Aborted by user")
            sys.exit(0)

    # Step 3: 执行对冲测试
    logger.info("\n" + "=" * 60)
    logger.info("⚠️ READY TO EXECUTE REAL HEDGE CYCLE")
    logger.info("=" * 60)
    logger.info("Configuration:")
    logger.info("  Symbol: %s", config.symbol)
    logger.info("  Notional: %.2f USDT", config.notional_usdt)
    logger.info("  Hold Duration: %.1f seconds", config.max_position_duration_seconds)
    logger.info("=" * 60)

    response = input("\n⚠️ 确认执行真实对冲测试？这将在 Testnet 上真实下单！(yes/no): ")
    if response.lower() != 'yes':
        logger.info("Aborted by user")
        sys.exit(0)

    # 执行对冲
    result = executor.execute_hedge_cycle()

    # Step 4: 显示结果
    logger.info("\n" + "=" * 60)
    logger.info("FINAL RESULT")
    logger.info("=" * 60)

    if result.success:
        logger.info("✅ Status: SUCCESS")
        logger.info("✅ Total PnL: $%.2f", result.total_pnl)
        logger.info("   - Binance PnL: $%.2f", result.pnl_a)
        logger.info("   - OKX PnL: $%.2f", result.pnl_b)

        if result.open_order_a:
            logger.info("\nOpen Orders:")
            logger.info("   Binance: %s %.4f @ %.2f",
                       result.open_order_a.side, result.open_order_a.size, result.open_order_a.price)
            logger.info("   OKX: %s %.4f @ %.2f",
                       result.open_order_b.side, result.open_order_b.size, result.open_order_b.price)

        if result.close_order_a:
            logger.info("\nClose Orders:")
            logger.info("   Binance: %s %.4f @ %.2f",
                       result.close_order_a.side, result.close_order_a.size, result.close_order_a.price)
            logger.info("   OKX: %s %.4f @ %.2f",
                       result.close_order_b.side, result.close_order_b.size, result.close_order_b.price)

        logger.info("\n🎉 双交易所对冲测试成功完成！")
        logger.info("=" * 60)

    else:
        logger.error("❌ Status: FAILED")
        logger.error("❌ Error: %s", result.error_message)
        logger.info("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Interrupted by user (Ctrl+C)")
        logger.warning("⚠️ Please manually check positions on both exchanges!")
        sys.exit(1)
    except Exception as e:
        logger.exception("❌ Unexpected error: %s", e)
        sys.exit(1)
