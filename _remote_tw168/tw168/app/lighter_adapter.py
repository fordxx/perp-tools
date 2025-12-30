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
    try:
        from app.okx_compat_layer import add_okx_compat_methods
    except ImportError:
        logger.warning("okx_compat_layer not found, skipping OKX compatibility methods")
        add_okx_compat_methods = None
    
    # 创建 LighterClient
    client = LighterClient(use_testnet=use_testnet)
    
    # 添加 OKX 兼容方法（如果可用）
    if add_okx_compat_methods is not None:
        add_okx_compat_methods(client)
    
    # 创建适配器
    adapter = LighterAsyncAdapter(client)
    
    logger.info(f"Created Lighter adapter (testnet={use_testnet})")
    
    return adapter
