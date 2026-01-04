#!/usr/bin/env python3
"""Quick test for the UI interface"""
import time
import subprocess
import requests
import signal
import sys

def test_ui():
    print("🚀 Starting server on port 9000...")

    # Start server in background
    server = subprocess.Popen([
        "python", "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", "9000"
    ], cwd="/home/fordxx/perp-tools/_remote_tw168/tw168")

    try:
        # Wait for server to start
        print("⏳ Waiting for server to start...")
        time.sleep(5)

        # Test UI endpoint
        print("📡 Testing UI interface...")
        response = requests.get("http://127.0.0.1:9000", timeout=10)

        if response.status_code == 200:
            content = response.text
            if "<!DOCTYPE html>" in content and "TW168 交易控制面板" in content:
                print("✅ UI interface working correctly!")
                print("🌐 Access at: http://127.0.0.1:9000")
                print("📱 UI features:")
                print("  - Real-time status display")
                print("  - Manual signal form")
                print("  - Price display")
                print("  - Signal history")
                print("  - Responsive Bootstrap design")
                return True
            else:
                print("❌ UI content not found")
                print("Response preview:", content[:200])
                return False
        else:
            print(f"❌ HTTP {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False
    finally:
        # Clean shutdown
        print("🛑 Stopping server...")
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

if __name__ == "__main__":
    success = test_ui()
    sys.exit(0 if success else 1)