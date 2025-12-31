"""Lighter Exchange Adapter - 异步适配层

LighterClient 已重构为原生 async，此文件直接透传异步调用。
"""
from __future__ import annotations

import logging
from typing import Any

from app.lighter_client_async import LighterClient

logger = logging.getLogger("uvicorn.error")


class LighterAsyncAdapter:
    """Lighter 交易所异步适配器"""
    
    def __init__(self, lighter_client: LighterClient) -> None:
        self._client = lighter_client
    
    @property
    def is_async_mode(self) -> bool:
        return True
    
    async def connect(self) -> None:
        """异步连接到交易所"""
        await self._client.connect()
        logger.info("✅ Lighter client connected via adapter")
    
    async def disconnect(self) -> None:
        """异步断开连接"""
        await self._client.disconnect()
    
    # ==================== WebSocket 方法显式代理 ====================
    
    def enable_websocket(self, auto_subscribe_account: bool = False) -> None:
        """启用 WebSocket"""
        return self._client.enable_websocket(auto_subscribe_account=auto_subscribe_account)
    
    async def subscribe_orderbook_stream(self, symbol: str, handler: Any) -> None:
        """订阅orderbook流 (async)"""
        return await self._client.subscribe_orderbook_stream(symbol, handler)
    
    def subscribe_trades_stream(self, symbol: str, handler: Any) -> None:
        """订阅trades流 (Lighter不支持)"""
        return self._client.subscribe_trades_stream(symbol, handler)
    
    async def start_websocket(self) -> None:
        """启动 WebSocket"""
        return await self._client.start_websocket()
    
    async def stop_websocket(self) -> None:
        """停止 WebSocket"""
        return await self._client.stop_websocket()
    
    # ==================== 透传所有方法 ====================
    
    def __getattr__(self, name: str) -> Any:
        """透传所有未定义的方法到 LighterClient"""
        return getattr(self._client, name)


def create_lighter_adapter(use_testnet: bool = False) -> LighterAsyncAdapter:
    """创建 Lighter 适配器的便捷函数
    
    Args:
        use_testnet: 是否使用测试网
        
    Returns:
        LighterAsyncAdapter 实例
    """
    # 创建 LighterClient
    client = LighterClient(use_testnet=use_testnet)
    
    # 创建适配器
    adapter = LighterAsyncAdapter(client)
    
    logger.info(f"Created Lighter adapter (testnet={use_testnet})")
    
    return adapter
