#!/usr/bin/env python3
"""
快速测试手动信号API端点
"""

import requests
import json
import subprocess
import time
import os

def start_server():
    """启动服务器"""
    print("🚀 启动服务器...")
    env = os.environ.copy()
    env['TV_WEBHOOK_SECRET'] = 'rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6'
    process = subprocess.Popen(
        ['python', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001'],
        cwd='/home/fordxx/perp-tools/_remote_tw168/tw168',
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # 等待服务器启动
    print("⏳ 等待服务器启动...")
    for i in range(10):
        time.sleep(2)
        try:
            response = requests.get("http://127.0.0.1:8001/health", timeout=2)
            if response.status_code == 200:
                print("✅ 服务器启动成功")
                return process
        except:
            print(f"   等待中... ({i+1}/10)")
            continue

    print("❌ 服务器启动失败")
    process.terminate()
    process.wait()
    return None

def test_manual_signal():
    """测试手动信号"""
    url = "http://127.0.0.1:8001/manual/signal"
    payload = {
        "instId": "ETH-USDT-SWAP",
        "tf": "1m",
        "side": "long",
        "type": "DIV",
        "admin_key": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6"
    }

    print("📤 发送手动信号测试...")
    print(f"🔗 URL: {url}")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"📊 响应状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print("✅ 信号发送成功!")
            print(f"📋 响应: {json.dumps(result, indent=2)}")

            if result.get("ok") and not result.get("skipped"):
                print("🎉 测试通过! 手动信号处理成功")
                return True
            else:
                print(f"⚠️ 信号被跳过: {result.get('skipped', 'unknown')}")
                return False
        else:
            print(f"❌ 信号发送失败: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误: {e}")
        return False

def main():
    print("🧪 快速测试手动信号API")
    print("=" * 40)

    # 启动服务器
    server_process = start_server()

    if server_process is None:
        print("❌ 无法启动服务器，退出测试")
        return

    try:
        # 测试API
        success = test_manual_signal()

        if success:
            print("\n✅ 所有测试通过!")
        else:
            print("\n❌ 测试失败!")

    finally:
        # 停止服务器
        print("\n🛑 停止服务器...")
        server_process.terminate()
        server_process.wait()

if __name__ == "__main__":
    main()