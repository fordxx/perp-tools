#!/usr/bin/env python3
"""
GRVT Credentials Validation Script

This script helps you validate your GRVT API credentials before enabling trading.
Run this after setting up your environment variables.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.grvt import GrvtCredentials


def validate_grvt_credentials():
    """Validate GRVT credentials format and presence."""
    print("🔍 Validating GRVT credentials...")

    # Check environment variables
    required_vars = [
        "GRVT_API_KEY",
        "GRVT_PRIVATE_KEY",
        "GRVT_TRADING_ACCOUNT_ID",
        "GRVT_BASE_URL"
    ]

    missing_vars = []
    for var in required_vars:
        value = os.getenv(var, "").strip()
        if not value:
            missing_vars.append(var)
        else:
            print(f"✅ {var}: {'*' * len(value)} (length: {len(value)})")

    if missing_vars:
        print(f"\n❌ Missing environment variables: {', '.join(missing_vars)}")
        print("\n📝 Please set the following in your .env file:")
        for var in missing_vars:
            print(f"  {var}=your_value_here")
        return False

    # Validate credential formats
    api_key = os.getenv("GRVT_API_KEY", "")
    private_key = os.getenv("GRVT_PRIVATE_KEY", "")
    trading_account_id = os.getenv("GRVT_TRADING_ACCOUNT_ID", "")
    base_url = os.getenv("GRVT_BASE_URL", "")

    issues = []

    # API Key should be alphanumeric
    if not api_key.replace("-", "").replace("_", "").isalnum():
        issues.append("GRVT_API_KEY contains invalid characters")

    # Private key should be hex (64 characters for 32 bytes)
    try:
        int(private_key, 16)
        if len(private_key) != 64:
            issues.append("GRVT_PRIVATE_KEY should be 64 hex characters (32 bytes)")
    except ValueError:
        issues.append("GRVT_PRIVATE_KEY is not valid hex")

    # Trading account ID should be UUID-like or alphanumeric
    if not trading_account_id.replace("-", "").isalnum():
        issues.append("GRVT_TRADING_ACCOUNT_ID contains invalid characters")

    # Base URL should be valid HTTPS URL
    if not base_url.startswith("https://"):
        issues.append("GRVT_BASE_URL should start with https://")

    if issues:
        print(f"\n❌ Credential format issues:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    print("\n✅ All credentials appear valid!")
    print("\n🔗 Next steps:")
    print("1. Run: python test_grvt_full_flow.py")
    print("2. If tests pass, uncomment EXCHANGE=grvt in .env")
    print("3. Restart the service: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")

    return True


if __name__ == "__main__":
    success = validate_grvt_credentials()
    sys.exit(0 if success else 1)