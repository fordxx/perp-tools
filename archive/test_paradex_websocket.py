#!/usr/bin/env python3
"""
测试 Paradex WebSocket 功能

用法:
    python test_paradex_websocket.py
"""

import logging
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# 先加载环境变量
load_dotenv()

# 添加 src 目录到 Python 路径
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from perpbot.exchanges.paradex import ParadexClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_websocket():
    """测试 WebSocket 连接和消息接收"""
    logger.info("=" * 60)
    logger.info("Paradex WebSocket 测试")
    
    # 从环境变量读取环境配置
    env = os.getenv("PARADEX_ENV", "testnet").lower()
    use_testnet = env in ["testnet", "test"]
    
    logger.info(f"环境: {'测试网' if use_testnet else '主网'}")
    logger.info("=" * 60)
    
    # 创建客户端（自动从 .env 读取环境）
    client = ParadexClient(use_testnet=use_testnet)
    
    # 连接（会自动启动 WebSocket）
    client.connect()
    
    # 等待一下让 WebSocket 连接建立
    time.sleep(2)
    
    # 定义回调函数
    def on_order_update(message: dict):
        """订单更新回调"""
        logger.info("📬 订单更新: %s", message)
    
    def on_position_update(message: dict):
        """持仓更新回调"""
        logger.info("📊 持仓更新: %s", message)
    
    # 设置回调（会自动订阅频道）
    logger.info("\n设置 WebSocket handlers...")
    client.setup_order_update_handler(on_order_update)
    client.setup_position_update_handler(on_position_update)
    
    # 等待接收消息
    logger.info("\n监听 WebSocket 消息 (60秒)...")
    logger.info("提示: 在 Paradex 上下单或修改仓位来触发更新\n")
    
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        logger.info("\n用户中断")
    
    # 清理
    logger.info("\n断开连接...")
    client.disconnect()
    
    logger.info("✅ 测试完成")


if __name__ == "__main__":
    test_websocket()
