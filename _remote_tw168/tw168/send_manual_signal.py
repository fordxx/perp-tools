#!/usr/bin/env python3
"""
手动信号发送工具
命令行工具，用于发送手动交易信号到远程服务器
"""

import argparse
import requests
import json
import os
from datetime import datetime

def send_manual_signal(inst_id: str, tf: str, side: str, admin_key: str, base_url: str = "https://trader:TW168Trading!2026@3-38-98-169.nip.io") -> dict:
    """发送手动交易信号到远程服务器"""
    url = f"{base_url}/manual/signal"
    payload = {
        "instId": inst_id,
        "tf": tf,
        "side": side,
        "type": "DIV",
        "admin_key": admin_key
    }

    print(f"📤 发送手动信号到 {base_url}")
    print(f"🎯 交易对: {inst_id}")
    print(f"⏰ 时间周期: {tf}")
    print(f"📈 方向: {side}")
    print(f"🔗 端点: {url}")
    print("-" * 50)

    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"📊 HTTP状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print("✅ 信号发送成功!")
            print("-" * 50)

            # 格式化输出结果
            if result.get("ok"):
                print("🎉 交易信号已处理:")
                if "paper" in result and result["paper"]:
                    print("📝 纸上交易模式")
                else:
                    print("💰 实盘交易模式")

                if "instId" in result:
                    print(f"🪙 交易对: {result['instId']}")
                if "side" in result:
                    print(f"📈 方向: {result['side']}")
                if "entry" in result:
                    print(f"💵 入场价: {result['entry']}")
                if "sl" in result:
                    print(f"🛡️ 止损: {result['sl']}")
                if "tp3" in result:
                    print(f"🎯 止盈: {result['tp3']}")
                if "order_sz" in result:
                    print(f"📊 仓位大小: {result['order_sz']}")
                if "r_value" in result:
                    print(f"📏 风险值: {result['r_value']}")
            else:
                print("❌ 信号处理失败:")
                print(json.dumps(result, indent=2, ensure_ascii=False))

            return result

        elif response.status_code == 403:
            print("❌ 权限错误: 管理员密钥无效")
            return {"error": "Invalid admin key"}

        else:
            print(f"❌ 发送失败: HTTP {response.status_code}")
            try:
                error_data = response.json()
                print(f"错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"错误详情: {response.text}")
            return {"error": response.text}

    except requests.exceptions.Timeout:
        print("❌ 超时错误: 服务器响应超时")
        return {"error": "Timeout"}

    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 无法连接到服务器")
        return {"error": "Connection error"}

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误: {e}")
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="手动发送交易信号到远程服务器")
    parser.add_argument("inst_id", help="交易对，如 ETH-USDT-SWAP")
    parser.add_argument("side", choices=["long", "short"], help="交易方向")
    parser.add_argument("-t", "--tf", default="1h", help="时间周期 (默认: 1h)")
    parser.add_argument("-k", "--key", help="管理员密钥 (可通过环境变量 TV_WEBHOOK_SECRET 设置)")
    parser.add_argument("-u", "--url", default="https://trader:TW168Trading!2026@3-38-98-169.nip.io", help="服务器URL (默认: https://3-38-98-169.nip.io with BasicAuth)")

    args = parser.parse_args()

    # 获取管理员密钥
    admin_key = args.key or os.getenv("TV_WEBHOOK_SECRET")
    if not admin_key:
        print("❌ 错误: 必须提供管理员密钥")
        print("   使用 -k 参数或设置 TV_WEBHOOK_SECRET 环境变量")
        return 1

    # 发送信号
    result = send_manual_signal(
        inst_id=args.inst_id,
        tf=args.tf,
        side=args.side,
        admin_key=admin_key,
        base_url=args.url
    )

    # 返回退出码
    if "error" in result:
        return 1
    else:
        return 0

if __name__ == "__main__":
    exit(main())