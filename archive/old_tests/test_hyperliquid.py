#!/usr/bin/env python
"""Test script for Hyperliquid exchange client.

Tests basic functionality:
1. Connection
2. Price fetching
3. Orderbook fetching
4. Account balances and positions
5. Order placement (testnet only)

Usage:
    python test_hyperliquid.py --symbol BTC/USDC --depth 20
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from perpbot.exchanges.hyperliquid import HyperliquidClient
from perpbot.models import OrderRequest, Side


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def test_connection():
    """Test: Connect to Hyperliquid testnet."""
    print_section("TEST 1: Connection")
    
    try:
        client = HyperliquidClient(use_testnet=True)
        client.connect()
        print("✅ Connection successful")
        print(f"   Base URL: {client.base_url}")
        print(f"   Trading enabled: {client._trading_enabled}")
        print(f"   Account: {client.account_address or 'Not configured'}")
        return client
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)


def test_price_fetching(client: HyperliquidClient, symbol: str):
    """Test: Fetch current price."""
    print_section(f"TEST 2: Price Fetching ({symbol})")
    
    try:
        quote = client.get_current_price(symbol)
        print(f"✅ Price fetched successfully")
        print(f"   Symbol: {quote.symbol}")
        print(f"   Bid: ${quote.bid:.4f}")
        print(f"   Ask: ${quote.ask:.4f}")
        print(f"   Mid: ${(quote.bid + quote.ask) / 2:.4f}")
        print(f"   Spread: {((quote.ask - quote.bid) / quote.bid * 100):.3f}%")
        print(f"   Timestamp: {quote.timestamp}")
        return quote
    except Exception as e:
        print(f"❌ Price fetch failed: {e}")
        return None


def test_orderbook(client: HyperliquidClient, symbol: str, depth: int = 20):
    """Test: Fetch orderbook."""
    print_section(f"TEST 3: Orderbook ({symbol}, depth={depth})")
    
    try:
        orderbook = client.get_orderbook(symbol, depth=depth)
        print(f"✅ Orderbook fetched successfully")
        print(f"   Symbol: {orderbook.symbol}")
        print(f"   Bid levels: {len(orderbook.bids)}")
        print(f"   Ask levels: {len(orderbook.asks)}")
        print(f"   Timestamp: {orderbook.timestamp}")
        
        if orderbook.bids:
            print(f"\n   Top 3 Bids:")
            for i, (price, size) in enumerate(orderbook.bids[:3]):
                print(f"     {i+1}. {price:>10.2f} x {size:>10.4f}")
        
        if orderbook.asks:
            print(f"\n   Top 3 Asks:")
            for i, (price, size) in enumerate(orderbook.asks[:3]):
                print(f"     {i+1}. {price:>10.2f} x {size:>10.4f}")
        
        return orderbook
    except Exception as e:
        print(f"❌ Orderbook fetch failed: {e}")
        return None


def test_active_orders(client: HyperliquidClient):
    """Test: Fetch active orders."""
    print_section("TEST 4: Active Orders")
    
    try:
        orders = client.get_active_orders()
        print(f"✅ Active orders fetched")
        print(f"   Total orders: {len(orders)}")
        
        for order in orders[:5]:
            print(f"\n   Order {order.id}")
            print(f"     Symbol: {order.symbol}")
            print(f"     Side: {order.side}")
            print(f"     Price: ${order.price:.4f}")
            print(f"     Quantity: {order.quantity:.4f}")
            print(f"     Filled: {order.filled_quantity:.4f}")
            print(f"     Status: {order.status}")
        
        return orders
    except Exception as e:
        print(f"❌ Active orders fetch failed: {e}")
        return []


def test_positions(client: HyperliquidClient):
    """Test: Fetch positions."""
    print_section("TEST 5: Account Positions")
    
    try:
        positions = client.get_account_positions()
        print(f"✅ Positions fetched")
        print(f"   Total positions: {len(positions)}")
        
        for pos in positions[:5]:
            print(f"\n   Position: {pos.symbol}")
            print(f"     Side: {pos.side}")
            print(f"     Size: {pos.size:.4f}")
            print(f"     Entry Price: ${pos.entry_price:.4f}")
            print(f"     Current Price: ${pos.current_price:.4f}")
            pnl_pct = ((pos.current_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price > 0 else 0
            print(f"     PnL: {pnl_pct:+.2f}%")
        
        return positions
    except Exception as e:
        print(f"❌ Positions fetch failed: {e}")
        return []


def test_balances(client: HyperliquidClient):
    """Test: Fetch account balances."""
    print_section("TEST 6: Account Balances")
    
    try:
        balances = client.get_account_balances()
        print(f"✅ Balances fetched")
        print(f"   Total assets: {len(balances)}")
        
        for balance in balances:
            print(f"\n   {balance.asset}")
            print(f"     Free: {balance.free:.4f}")
            print(f"     Locked: {balance.locked:.4f}")
            print(f"     Total: {balance.total:.4f}")
        
        return balances
    except Exception as e:
        print(f"❌ Balances fetch failed: {e}")
        return []


def test_price_caching(client: HyperliquidClient, symbol: str):
    """Test: Price caching mechanism."""
    print_section("TEST 7: Price Caching")
    
    try:
        import time
        
        # First fetch
        start = time.time()
        quote1 = client.get_current_price(symbol)
        t1 = time.time() - start
        
        # Second fetch (should be cached)
        start = time.time()
        quote2 = client.get_current_price(symbol)
        t2 = time.time() - start
        
        print(f"✅ Cache test completed")
        print(f"   First fetch: {t1*1000:.2f}ms (live)")
        print(f"   Second fetch: {t2*1000:.2f}ms (cached)")
        print(f"   Speed improvement: {t1/t2:.1f}x")
        print(f"   Prices match: {quote1.bid == quote2.bid and quote1.ask == quote2.ask}")
        
    except Exception as e:
        print(f"❌ Cache test failed: {e}")


def test_order_placement(client: HyperliquidClient, symbol: str, size: float):
    """Test: Order placement (testnet only)."""
    print_section(f"TEST 8: Order Placement ({symbol}, size={size})")
    
    if not client._trading_enabled:
        print("⚠️  Trading disabled (credentials not configured)")
        print("   To enable trading, set:")
        print("   - HYPERLIQUID_ACCOUNT_ADDRESS")
        print("   - HYPERLIQUID_PRIVATE_KEY")
        return
    
    try:
        # Get current price
        quote = client.get_current_price(symbol)
        
        # Place a small test order at limit price (unlikely to fill)
        order_request = OrderRequest(
            symbol=symbol,
            side=Side.BUY,
            price=quote.bid * 0.95,  # 5% below bid
            quantity=size,
            order_type="limit",
        )
        
        order = client.place_open_order(order_request)
        print(f"✅ Order placed")
        print(f"   Order ID: {order.id}")
        print(f"   Symbol: {order.symbol}")
        print(f"   Side: {order.side}")
        print(f"   Price: ${order.price:.4f}")
        print(f"   Quantity: {order.quantity:.4f}")
        print(f"   Status: {order.status}")
        
    except Exception as e:
        print(f"❌ Order placement failed: {e}")


def main():
    """Run all tests."""
    parser = argparse.ArgumentParser(description="Test Hyperliquid exchange client")
    parser.add_argument("--symbol", default="BTC/USDC", help="Symbol to test (default: BTC/USDC)")
    parser.add_argument("--depth", type=int, default=20, help="Orderbook depth (default: 20)")
    parser.add_argument("--size", type=float, default=0.001, help="Order size for placement test (default: 0.001)")
    
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print(f"  Hyperliquid Exchange Client - Full Test Suite")
    print(f"{'='*70}")
    print(f"Symbol: {args.symbol}")
    print(f"Depth: {args.depth}")
    print(f"Order size: {args.size}")
    
    # Run tests
    client = test_connection()
    test_price_fetching(client, args.symbol)
    test_orderbook(client, args.symbol, args.depth)
    test_price_caching(client, args.symbol)
    test_active_orders(client)
    test_positions(client)
    test_balances(client)
    test_order_placement(client, args.symbol, args.size)
    
    print(f"\n{'='*70}")
    print(f"  ✅ All tests completed!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
