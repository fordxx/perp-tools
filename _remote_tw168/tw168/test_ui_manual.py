#!/usr/bin/env python3
"""Test UI interface by opening it in browser"""

import webbrowser
import time
import subprocess
import sys

def test_ui():
    """Test the UI interface"""
    print("🧪 Testing TW168 UI Interface")
    print("=" * 50)

    # Start the server in background
    print("🚀 Starting UI server...")
    server_process = subprocess.Popen([
        sys.executable, "start_ui_server.py"
    ], cwd="/home/fordxx/perp-tools/_remote_tw168/tw168",
       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for server to start
    time.sleep(3)

    try:
        # Test health endpoint
        print("🔍 Testing health endpoint...")
        import requests
        response = requests.get("http://127.0.0.1:9000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health check passed")
        else:
            print(f"❌ Health check failed: {response.status_code}")

        # Test UI endpoint
        print("🔍 Testing UI endpoint...")
        response = requests.get("http://127.0.0.1:9000/", timeout=5)
        if response.status_code == 200:
            print("✅ UI endpoint responded")
            content = response.text
            if "TW168 交易控制面板" in content:
                print("✅ UI title found")
            else:
                print("❌ UI title not found")

            if "手动交易信号" in content:
                print("✅ Manual signal form found")
            else:
                print("❌ Manual signal form not found")

            if "Bootstrap" in content or "bootstrap" in content:
                print("✅ Bootstrap CSS found")
            else:
                print("❌ Bootstrap CSS not found")

        else:
            print(f"❌ UI endpoint failed: {response.status_code}")

        # Test manual signal endpoint
        print("🔍 Testing manual signal endpoint...")
        payload = {
            "instId": "BTC-USDT-SWAP",
            "tf": "1h",
            "side": "long",
            "type": "DIV",
            "admin_key": "test_key"
        }
        response = requests.post("http://127.0.0.1:9000/manual/signal",
                               json=payload, timeout=5)
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                print("✅ Manual signal endpoint working")
                print(f"   Response: {result.get('message', 'OK')}")
            else:
                print(f"❌ Manual signal failed: {result}")
        else:
            print(f"❌ Manual signal endpoint failed: {response.status_code}")

        print("\n🎉 UI Testing Complete!")
        print("\n📱 To manually test the UI:")
        print("   1. Open your browser")
        print("   2. Go to: http://127.0.0.1:9000")
        print("   3. Try submitting a signal with admin_key: 'test_key'")
        print("   4. Press Ctrl+C in terminal to stop server")

        # Open browser
        print("\n🌐 Opening browser...")
        webbrowser.open("http://127.0.0.1:9000")

        # Keep server running for manual testing
        print("\n🕐 Server is running. Press Enter to stop...")
        input()

    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP request failed: {e}")
    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        # Stop server
        print("🛑 Stopping server...")
        server_process.terminate()
        server_process.wait()

if __name__ == "__main__":
    test_ui()