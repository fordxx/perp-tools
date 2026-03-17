#!/usr/bin/env python3
"""
Dashboard WebSocket Server - 实时推送交易数据
监听端口: 18889
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set
import websockets
from websockets.server import WebSocketServerProtocol

# 添加项目路径
import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

# 导入数据聚合器
from perpbot.monitoring.dashboard_api import TradingSystemDataAggregator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 连接的客户端集合
connected_clients: Set[WebSocketServerProtocol] = set()

# 数据聚合器
data_aggregator = TradingSystemDataAggregator()


async def handle_client(websocket: WebSocketServerProtocol, path: str):
    """处理客户端连接"""
    # 添加到连接集合
    connected_clients.add(websocket)
    client_ip = websocket.remote_address[0]
    logger.info(f"客户端已连接: {client_ip}, 总连接数: {len(connected_clients)}")

    try:
        # 发送欢迎消息
        await websocket.send(json.dumps({
            'type': 'connected',
            'message': 'WebSocket连接成功',
            'timestamp': datetime.now().isoformat()
        }))

        # 保持连接，等待客户端消息
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get('type')

                if msg_type == 'ping':
                    await websocket.send(json.dumps({
                        'type': 'pong',
                        'timestamp': datetime.now().isoformat()
                    }))
                elif msg_type == 'subscribe':
                    # 客户端订阅特定数据
                    logger.info(f"客户端订阅: {data.get('channels', [])}")

            except json.JSONDecodeError:
                logger.error(f"无效的JSON消息: {message}")
            except Exception as e:
                logger.error(f"处理消息错误: {e}")

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"客户端断开连接: {client_ip}")
    finally:
        # 从连接集合中移除
        connected_clients.discard(websocket)
        logger.info(f"总连接数: {len(connected_clients)}")


async def broadcast_data():
    """定期广播数据给所有客户端"""
    while True:
        if connected_clients:
            try:
                # 获取系统状态
                system_status = data_aggregator.get_system_status()

                # 获取策略数据
                strategies = data_aggregator.get_all_strategies()

                # 获取交易所连接状态
                # TODO: 真正连接各交易所WebSocket并获取状态
                # 目前返回模拟数据 - 默认所有交易所都已连接
                exchange_statuses = [
                    {'id': 'grvt', 'connected': True},
                    {'id': 'okx', 'connected': True},
                    {'id': 'hyperliquid', 'connected': True},
                    {'id': 'backpack', 'connected': True},
                    {'id': 'ethereal', 'connected': True},
                    {'id': 'extended', 'connected': True}
                ]

                # 构造消息
                message = {
                    'type': 'update',
                    'timestamp': datetime.now().isoformat(),
                    'data': {
                        'system': system_status,
                        'strategies': strategies,
                        'exchange_statuses': exchange_statuses
                    }
                }

                # 广播给所有客户端
                message_json = json.dumps(message)
                disconnected = set()

                for client in connected_clients:
                    try:
                        await client.send(message_json)
                    except websockets.exceptions.ConnectionClosed:
                        disconnected.add(client)
                    except Exception as e:
                        logger.error(f"发送数据错误: {e}")
                        disconnected.add(client)

                # 清理断开的连接
                connected_clients.difference_update(disconnected)

            except Exception as e:
                logger.error(f"广播数据错误: {e}")

        # 每2秒广播一次
        await asyncio.sleep(2)


async def main():
    """启动WebSocket服务器"""
    # 启动广播任务
    asyncio.create_task(broadcast_data())

    # 启动WebSocket服务器
    server = await websockets.serve(
        handle_client,
        "0.0.0.0",
        18889,
        ping_interval=20,
        ping_timeout=10
    )

    logger.info("=" * 50)
    logger.info("  Dashboard WebSocket Server 已启动")
    logger.info("=" * 50)
    logger.info(f"  监听地址: ws://0.0.0.0:18889")
    logger.info(f"  实时推送间隔: 2秒")
    logger.info("=" * 50)

    # 保持服务运行
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务器已停止")
