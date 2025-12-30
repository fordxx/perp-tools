#!/usr/bin/env python3
"""
Hyperliquid Copy Trader - Production Runner
运行优化的超高速跟单交易系统
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.perpbot.copy_trader import HyperliquidCopyTrader

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/copy_trader.log')
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """主函数"""
    logger.info("🚀 Starting Hyperliquid Ultra-Fast Copy Trader (Production)")

    # 创建trader实例
    trader = HyperliquidCopyTrader()

    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}, 正在停止...")
        asyncio.create_task(trader.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 启动交易器
        await trader.start()
        logger.info("✅ Copy trader started successfully")

        # 保持运行
        while trader.running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("收到键盘中断，正在停止...")
    except Exception as e:
        logger.error(f"启动失败: {e}")
        raise
    finally:
        await trader.stop()
        logger.info("🛑 Copy trader stopped")

if __name__ == "__main__":
    asyncio.run(main())