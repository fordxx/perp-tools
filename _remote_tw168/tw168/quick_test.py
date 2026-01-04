#!/usr/bin/env python3
import requests
import os
from dotenv import load_dotenv

load_dotenv()
admin_key = os.getenv('TV_WEBHOOK_SECRET')

url = 'http://127.0.0.1:8001/manual/signal'
payload = {
    'instId': 'ETH-USDT-SWAP',
    'tf': '1h',
    'side': 'long',
    'type': 'DIV',
    'admin_key': admin_key
}

print('测试手动信号API...')
try:
    response = requests.post(url, json=payload, timeout=10)
    print(f'状态码: {response.status_code}')
    if response.status_code == 200:
        print('✅ API响应成功!')
        result = response.json()
        print('响应内容:')
        print(f'  ok: {result.get("ok")}')
        print(f'  type: {result.get("type")}')
        print(f'  zone: {result.get("zone")}')
        print(f'  side: {result.get("side")}')
        print(f'  posSide: {result.get("posSide")}')
        if result.get("ok"):
            print('🎉 手动信号API测试通过!')
        else:
            print('❌ API返回错误:', result)
    else:
        print('❌ API响应失败:', response.text)
except Exception as e:
    print(f'❌ 网络错误: {e}')