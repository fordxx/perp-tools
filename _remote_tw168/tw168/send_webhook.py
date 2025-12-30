#!/usr/bin/env python3
"""
发送 TradingView webhook 到本地服务
"""

import requests
import json
import sys
from datetime import datetime

if len(sys.argv) < 3:
    print("用法: python3 send_webhook.py <signal_type> <symbol> [timeframe]")
    print("  signal_type: ZONE 或 DIV")
    print("  symbol: EIGEN, BTC, 等")
    print("  timeframe: 30m, 1h, 等 (默认: 30m)")
    sys.exit(1)

signal_type = sys.argv[1].upper()
symbol = sys.argv[2]
timeframe = sys.argv[3] if len(sys.argv) > 3 else "30m"

# 获取当前价格 (模拟)
price = 0.37  # 默认价格

if signal_type == "ZONE":
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "zone": "OVERSOLD",
        "price": price,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
elif signal_type == "DIV":
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "divergence_type": "BULLISH",
        "price": price,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
else:
    print(f"❌ 未知信号类型: {signal_type}")
    sys.exit(1)

print(f"\n📤 发送 {signal_type} 信号...")
print(json.dumps(payload, indent=2))
print()

try:
    response = requests.post(
        "http://localhost:8000/tradingview/webhook",
        json=payload,
        timeout=10
    )
    print(f"📥 响应:")
    print(f"  Status: {response.status_code}")
    print(f"  Body: {response.text}")
except Exception as e:
    print(f"❌ 请求失败: {e}")
