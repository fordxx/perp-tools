#!/usr/bin/env python3
"""
Simple manual signal test - direct API call without server startup
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_manual_signal():
    # Get admin key from environment
    admin_key = os.getenv("TV_WEBHOOK_SECRET", "CHANGE_ME")
    if admin_key == "CHANGE_ME":
        print("❌ TV_WEBHOOK_SECRET not set properly")
        return False

    # Test data
    test_data = {
        "instId": "ETH-USDT-SWAP",
        "tf": "1h",
        "side": "long",
        "type": "DIV",
        "admin_key": admin_key
    }

    print("🔍 Testing manual signal API...")
    print(f"📡 URL: http://127.0.0.1:8001/manual/signal")
    print(f"📦 Data: {json.dumps(test_data, indent=2)}")

    try:
        response = requests.post(
            "http://127.0.0.1:8001/manual/signal",
            json=test_data,
            timeout=10
        )

        print(f"📊 Response Status: {response.status_code}")
        print(f"📄 Response Headers: {dict(response.headers)}")

        if response.status_code == 200:
            result = response.json()
            print("✅ API Response:")
            print(json.dumps(result, indent=2))

            # Check if signal was processed
            if result.get("ok"):
                print("✅ Signal accepted and processed")
                if result.get("skipped"):
                    print(f"⚠️  Signal skipped: {result.get('skipped')}")
                else:
                    print("✅ Signal executed successfully")
                return True
            else:
                print(f"❌ Signal rejected: {result.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ HTTP Error {response.status_code}: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - server not running")
        return False
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_manual_signal()
    sys.exit(0 if success else 1)