#!/usr/bin/env python3
"""
手动信号发送测试脚本
测试新添加的 /manual/signal API 端点
"""

import requests
import json
from datetime import datetime

def send_manual_signal(inst_id: str, tf: str, side: str, admin_key: str, base_url: str = "http://127.0.0.1:8000") -> dict:
    """发送手动交易信号"""
    url = f"{base_url}/manual/signal"
    payload = {
        "instId": inst_id,
        "tf": tf,
        "side": side,
        "type": "DIV",
        "admin_key": admin_key
    }

    print(f"📤 发送手动信号: {inst_id} {tf} {side}")
    print(f"🔗 URL: {url}")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"📊 响应状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print("✅ 信号发送成功!")
            print(f"📋 响应: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"❌ 信号发送失败: {response.text}")
            return {"error": response.text}

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误: {e}")
        return {"error": str(e)}

def test_manual_signal():
    """测试手动信号功能"""
    print("🧪 测试手动信号发送功能")
    print("=" * 50)

    # 测试参数
    test_cases = [
        {
            "inst_id": "ETH-USDT-SWAP",
            "tf": "1h",
            "side": "long",
            "description": "做多 ETH 1小时"
        },
        {
            "inst_id": "BTC-USDT-SWAP",
            "tf": "4h",
            "side": "short",
            "description": "做空 BTC 4小时"
        }
    ]

    # 从环境变量或配置文件获取密钥
    import os
    admin_key = os.getenv("TV_WEBHOOK_SECRET", "CHANGE_ME")

    if admin_key == "CHANGE_ME":
        print("⚠️  请设置 TV_WEBHOOK_SECRET 环境变量或直接在脚本中修改 admin_key")
        return

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 测试用例 {i}: {test_case['description']}")
        print("-" * 30)

        result = send_manual_signal(
            inst_id=test_case["inst_id"],
            tf=test_case["tf"],
            side=test_case["side"],
            admin_key=admin_key
        )

        if "error" not in result:
            print("✅ 测试通过")
        else:
            print("❌ 测试失败")

    print("\n" + "=" * 50)
    print("🎯 测试完成")

if __name__ == "__main__":
    test_manual_signal()