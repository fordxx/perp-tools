#!/usr/bin/env python3
"""完整的async重构脚本 - 一次性处理所有转换"""
import re

def refactor_to_async(input_file, output_file):
    with open(input_file, 'r') as f:
        content = f.read()
    
    # 1. 移除perpbot依赖
    content = re.sub(r'from perpbot\.exchanges\.base import ExchangeClient\n', '', content)
    content = re.sub(r'from perpbot\.models import [^\n]+\n', '', content)
    content = re.sub(r'class LighterClient\(ExchangeClient\):', 'class LighterClient:', content)
    
    # 2. 替换类型
    type_map = [
        (r'-> PriceQuote:', '-> dict:'),
        (r'-> OrderBookDepth:', '-> dict:'),
        (r'-> Order:', '-> dict:'),
        (r'-> Position:', '-> dict:'),
        (r'-> Balance:', '-> dict:'),
        (r'-> List\[Order\]:', '-> list:'),
        (r'-> List\[Balance\]:', '-> list:'),
        (r', request: OrderRequest', ', request: dict'),
        (r', position: Position', ', position: dict'),
        (r'PriceQuote\(', 'dict('),
        (r'OrderBookDepth\(', 'dict('),
        (r'Order\(', 'dict('),
    ]
    for pattern, repl in type_map:
        content = re.sub(pattern, repl, content)
    
    # 3. 移除threading相关
    content = re.sub(r'^\s*self\._loop:.*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*self\._loop_thread:.*\n', '', content, flags=re.MULTILINE)
    
    # 4. 移除_ensure_loop和_run_coro方法
    content = re.sub(r'    def _ensure_loop\(self\).*?(?=\n    def |\n    async def |\nclass |\Z)', '', content, flags=re.DOTALL)
    content = re.sub(r'    def _run_coro\(self.*?(?=\n    def |\n    async def |\nclass |\Z)', '', content, flags=re.DOTALL)
    
    # 5. 转换公开方法为async
    public_methods = [
        'connect', 'disconnect', 'get_current_price', 'get_orderbook',
        'place_open_order', 'place_close_order', 'cancel_order',
        'cancel_all_orders', 'get_account_positions', 'get_position',
        'get_account_balance', 'get_active_orders'
    ]
    for method in public_methods:
        content = re.sub(rf'(\s+)def ({method})\(', rf'\1async def \2(', content)
    
    # 6. 转换helper方法为async
    helper_methods = [
        '_to_lighter_symbol', '_normalize_symbol', '_get_market_id',
        'get_instrument_info', 'place_stop_loss', 'place_take_profit',
        'get_order_fills', 'get_account_balances',
        'enable_websocket', 'disable_websocket',
        'subscribe_orderbook_stream', 'subscribe_trades_stream', 'subscribe_market_stats_stream'
    ]
    for method in helper_methods:
        content = re.sub(rf'(\s+)def ({method})\(', rf'\1async def \2(', content)
    
    # 7. 替换所有_run_coro调用
    # 简单的单行模式
    content = re.sub(
        r'self\._run_coro\(([^,\)]+),\s*timeout=[0-9.]+\)',
        r'await \1',
        content
    )
    
    # 多行create_order模式
    content = re.sub(
        r'create_order, tx_hash, error = self\._run_coro\(\s*self\._signer_client\.create_order\(',
        r'create_order, tx_hash, error = await self._signer_client.create_order(',
        content,
        flags=re.DOTALL
    )
    
    # 多行cancel_order模式
    content = re.sub(
        r'cancel_result, tx_hash, error = self\._run_coro\(\s*self\._signer_client\.cancel_order\(',
        r'cancel_result, tx_hash, error = await self._signer_client.cancel_order(',
        content,
        flags=re.DOTALL
    )
    
    # 其他resp =模式
    content = re.sub(
        r'resp = self\._run_coro\(',
        r'resp = await ',
        content
    )
    
    # 清理timeout参数和多余括号
    content = re.sub(r',\s*timeout=[0-9.]+\s*\)', ')', content)
    content = re.sub(r',\s*timeout=[0-9.]+', '', content)
    
    # 8. 修复helper方法调用（添加await）
    content = re.sub(r'([^await\s])self\._to_lighter_symbol\(', r'\1await self._to_lighter_symbol(', content)
    content = re.sub(r'([^await\s])self\._get_market_id\(', r'\1await self._get_market_id(', content)
    content = re.sub(r'([^await\s])self\._normalize_symbol\(', r'\1await self._normalize_symbol(', content)
    
    # 9. 修复__del__
    content = re.sub(
        r'def __del__\(self\) -> None:.*?except Exception:\s*pass',
        'def __del__(self) -> None:\n        # Note: __del__ cannot be async\n        pass',
        content,
        flags=re.DOTALL
    )
    
    # 10. 修复await后换行
    content = re.sub(r'await\s*\n\s+', 'await ', content)
    
    with open(output_file, 'w') as f:
        f.write(content)
    
    print(f'✅ 重构完成: {output_file}')
    print(f'   - 移除 perpbot 依赖')
    print(f'   - 移除 threading 代码')
    print(f'   - 转换为原生 async/await')
    print(f'   - async 方法数: {content.count("async def")}')

if __name__ == '__main__':
    refactor_to_async('app/lighter_client.py', 'app/lighter_client_async.py')
