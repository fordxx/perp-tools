#!/bin/bash
# Test script to compare OKX and Lighter prices

echo "========================================="
echo "OKX vs Lighter Price Comparison"
echo "========================================="
echo ""

# Test webhook endpoint with a Lighter-supported symbol
echo "Testing price fetch for ETH (available on Lighter)..."
curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETH-USDT-SWAP",
    "action": "buy",
    "price": 3000,
    "contracts": 0.01,
    "timeframe": "1h"
  }' | python3 -m json.tool

echo ""
echo "========================================="
echo "Checking OKX candle cache for ETH..."
curl -s "http://localhost:8000/candles/ETH-USDT-SWAP/1h?limit=1" | python3 -m json.tool

echo ""
echo "========================================="
echo "Summary:"
echo "- System is using OKX for K-line data (WebSocket)"
echo "- Trades will execute on Lighter DEX (EXCHANGE=lighter)"
echo "- ETH, BTC, SOL, etc. are available on Lighter"
echo ""
echo "To see full Lighter market list, check container logs:"
echo "  docker compose logs | grep 'Lighter market'"
echo ""
