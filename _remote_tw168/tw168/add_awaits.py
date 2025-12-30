#!/usr/bin/env python3
"""
批量在 exchange 方法调用前添加 await 关键字。
这个脚本会：
1. 查找所有 exchange.xxx() 调用
2. 在它们前面添加 await（如果还没有）
3. 保持代码格式不变
"""
import re
import sys

def add_awaits_to_file(filepath):
    """在文件中的 exchange 方法调用前添加 await"""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # 需要添加 await 的方法列表
    methods = [
        'place_order',
        'cancel_order',
        'get_order',
        'get_position',
        'get_last_price',
        'get_instrument_info',
        'place_algo_order',
        'get_open_orders',
        'get_account_positions',
        'cancel_all_orders',
        'cancel_all_orders_for_symbol',
    ]
    
    changes_made = 0
    
    for method in methods:
        # 匹配模式：
        # 1. 捕获前面的空白
        # 2. 确保前面没有 await
        # 3. 匹配 exchange.method_name(
        pattern = r'(\s+)(?!await\s+)(exchange\.' + re.escape(method) + r'\()'
        
        def replacement(match):
            nonlocal changes_made
            changes_made += 1
            whitespace = match.group(1)
            call = match.group(2)
            return f"{whitespace}await {call}"
        
        content = re.sub(pattern, replacement, content)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 完成修改: {changes_made} 处添加了 await")
        return True
    else:
        print("ℹ️  没有需要修改的地方")
        return False

if __name__ == '__main__':
    filepath = 'app/main.py'
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    
    print(f"处理文件: {filepath}")
    add_awaits_to_file(filepath)
