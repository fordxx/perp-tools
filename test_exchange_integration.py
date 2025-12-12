#!/usr/bin/env python3
"""Integration test for all exchange clients to verify mock mode support."""

import sys
import logging

# Add src to path
sys.path.insert(0, "src")

from perpbot.exchanges.paradex import ParadexClient
from perpbot.exchanges.extended import ExtendedClient
from perpbot.exchanges.okx import OKXClient
from perpbot.exchanges.lighter import LighterClient
from perpbot.exchanges.edgex import EdgeXClient
from perpbot.exchanges.backpack import BackpackClient
from perpbot.exchanges.grvt import GRVTClient
from perpbot.exchanges.aster import AsterClient
from perpbot.exchanges.hyperliquid import HyperliquidClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s'
)
logger = logging.getLogger(__name__)

def test_exchange(client_class, name: str):
    """Test a single exchange client."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing {name.upper()}")
    logger.info(f"{'='*60}")
    
    try:
        client = client_class()
        client.connect()
        
        # Test price quote
        logger.info(f"📊 Testing {name} price quote...")
        price = client.get_current_price("BTC/USDT")
        logger.info(f"   Price: bid={price.bid}, ask={price.ask}")
        
        # Test orderbook
        logger.info(f"📈 Testing {name} orderbook...")
        orderbook = client.get_orderbook("BTC/USDT", depth=5)
        logger.info(f"   Bids: {len(orderbook.bids)} levels")
        logger.info(f"   Asks: {len(orderbook.asks)} levels")
        if orderbook.bids:
            logger.info(f"   Best bid: {orderbook.bids[0]}")
        if orderbook.asks:
            logger.info(f"   Best ask: {orderbook.asks[0]}")
        
        # Test active orders
        logger.info(f"📋 Testing {name} active orders...")
        orders = client.get_active_orders("BTC/USDT")
        logger.info(f"   Active orders: {len(orders)}")
        
        # Test positions
        logger.info(f"📍 Testing {name} positions...")
        positions = client.get_account_positions()
        logger.info(f"   Open positions: {len(positions)}")
        
        # Test balances
        logger.info(f"💰 Testing {name} balances...")
        balances = client.get_account_balances()
        logger.info(f"   Available balances: {len(balances)}")
        
        logger.info(f"✅ {name} test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ {name} test FAILED: {e}", exc_info=True)
        return False

def main():
    """Test all exchange clients."""
    exchanges = [
        (ParadexClient, "paradex"),
        (ExtendedClient, "extended"),
        (OKXClient, "okx"),
        (LighterClient, "lighter"),
        (EdgeXClient, "edgex"),
        (BackpackClient, "backpack"),
        (GRVTClient, "grvt"),
        (AsterClient, "aster"),
        (HyperliquidClient, "hyperliquid"),
    ]
    
    results = {}
    for client_class, name in exchanges:
        results[name] = test_exchange(client_class, name)
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*60}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status:8} | {name}")
    
    logger.info(f"{'='*60}")
    logger.info(f"Result: {passed}/{total} exchanges passed")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
