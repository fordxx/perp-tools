#!/usr/bin/env python3
"""自动重构 LighterClient 为原生 async"""
import re
import sys

def refactor_lighter_to_async(input_file: str, output_file: str):
    """重构 LighterClient 为原生 async"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 移除线程相关属性
    content = re.sub(
        r'        self\._loop: Optional\[asyncio\.AbstractEventLoop\] = None\n',
        '',
        content
    )
    content = re.sub(
        r'        self\._loop_thread: Optional\[threading\.Thread\] = None\n',
        '',
        content
    )
    
    # 2. 移除 _ensure_loop 方法
    content = re.sub(
        r'    def _ensure_loop\(self\) -> None:.*?self\._loop_thread = thread\n\n',
        '',
        content,
        flags=re.DOTALL
    )
    
    # 3. 移除 _run_coro 方法
    content = re.sub(
        r'    def _run_coro\(self, coro, timeout: float = 15\.0\):.*?return fut\.result\(timeout=timeout\)\n\n',
        '',
        content,
        flags=re.DOTALL
    )
    
    # 4. 修改 connect() 为 async
    content = re.sub(
        r'(    )def connect\(self\) -> None:',
        r'\1async def connect(self) -> None:',
        content
    )
    
    # 5. 移除 connect() 中的 _ensure_loop 和 _run_coro 调用
    content = re.sub(
        r'            self\._ensure_loop\(\)\n',
        '',
        content
    )
    content = re.sub(
        r'            self\._run_coro\(self\._async_initialize\(\), timeout=30\.0\)\n',
        '            await self._async_initialize()\n',
        content
    )
    
    # 6. 修改 disconnect() 为 async
    content = re.sub(
        r'(    )def disconnect\(self\) -> None:',
        r'\1async def disconnect(self) -> None:',
        content
    )
    
    # 7. 修改 disconnect() 中的异步调用
    content = re.sub(
        r'            if self\._ws_client and self\._loop and self\._loop\.is_running\(\):\n\s+try:\n\s+self\._run_coro\(self\._ws_client\.disconnect\(\), timeout=5\.0\)',
        '            if self._ws_client:\n                try:\n                    await self._ws_client.disconnect()',
        content
    )
    content = re.sub(
        r'            if self\._api_client and self\._loop and self\._loop\.is_running\(\):\n\s+try:\n\s+self\._run_coro\(self\._api_client\.close\(\), timeout=5\.0\)',
        '            if self._api_client:\n                try:\n                    await self._api_client.close()',
        content
    )
    
    # 8. 移除 disconnect() 中的 loop.stop() 调用
    content = re.sub(
        r'\n\s+if self\._loop and self\._loop\.is_running\(\):\n\s+try:\n\s+self\._loop\.call_soon_threadsafe\(self\._loop\.stop\)\n\s+except Exception:\n\s+pass',
        '',
        content
    )
    
    # 9. 将所有 def xxx(...) 改为 async def xxx(...) (排除特殊方法)
    # 匹配公共方法（不是 _ 开头，不是 __xxx__）
    def_pattern = r'(\n    )(def )([a-z_][a-z0-9_]*)\('
    async_def_replacement = r'\1async def \3('
    
    # 找出所有需要改的方法
    methods_to_async = [
        'place_order', 'cancel_order', 'cancel_all_orders',
        'get_account_positions', 'get_current_price', 'get_orderbook',
        'get_open_orders', 'get_order_history', 'get_position',
        'get_account_balance', 'get_fills', 'estimate_liquidation_price'
    ]
    
    for method in methods_to_async:
        content = re.sub(
            rf'(\n    )(def )({method})\(',
            r'\1async def \3(',
            content
        )
    
    # 10. 替换所有 self._run_coro(...) 为 await ...
    # 简单模式：self._run_coro(xxx, timeout=N) -> await xxx
    content = re.sub(
        r'self\._run_coro\(([^,]+)(?:, timeout=[0-9.]+)?\)',
        r'await \1',
        content
    )
    
    # 11. 移除 threading import (如果不再需要)
    # 保留，因为可能还有其他用途（如 lock）
    
    # 12. 修改 __del__ 为同步（移除异步调用）
    content = re.sub(
        r'    def __del__\(self\) -> None:\n\s+try:\n\s+self\.disconnect\(\)',
        r'    def __del__(self) -> None:\n        # Note: __del__ cannot be async, disconnect should be called explicitly\n        pass',
        content
    )
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 重构完成: {output_file}")
    print(f"   - 移除了 _loop 和 _loop_thread 属性")
    print(f"   - 移除了 _ensure_loop() 和 _run_coro() 方法")
    print(f"   - 将 {len(methods_to_async)} 个公开方法改为 async")
    print(f"   - 替换了所有 self._run_coro() 调用为 await")

if __name__ == '__main__':
    refactor_lighter_to_async(
        'app/lighter_client.py',
        'app/lighter_client_async.py'
    )
