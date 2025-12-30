#!/bin/bash
# Enable Lighter WebSocket for half of supported trading pairs

echo "========================================"
echo "Lighter WebSocket 测试配置"
echo "========================================"
echo ""

REMOTE_HOST="ubuntu@3.38.98.169"
SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"

echo "配置说明："
echo "- 总共 17 个交易对"
echo "- Lighter 支持: 11 个 (ETH, BTC, SOL, XRP, ONDO, LINK, BCH, LTC, DOGE, BNB, TON)"
echo "- 仅 OKX 支持: 6 个 (JTO, TRX, EIGEN, TAO, PUMP, TRUMP)"
echo ""
echo "测试方案："
echo "- OKX K线 + Lighter WebSocket: 6 个币种 (ETH, BTC, SOL, LINK, DOGE, BNB)"
echo "- OKX K线 + OKX 交易: 11 个币种 (其余所有)"
echo ""

# Update main.py to enable Lighter WebSocket
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'EOF'
cd /home/ubuntu/tw168

echo "Creating backup..."
cp app/main.py app/main.py.backup

echo "Adding Lighter WebSocket configuration..."

# Add WebSocket symbols configuration at the top of main.py
cat > /tmp/lighter_ws_config.py << 'PYTHON_CODE'
# Lighter WebSocket test configuration
# 测试 Lighter WebSocket 的交易对 (一半)
LIGHTER_WS_SYMBOLS = {
    "ETH-USDT-SWAP",
    "BTC-USDT-SWAP",
    "SOL-USDT-SWAP",
    "LINK-USDT-SWAP",
    "DOGE-USDT-SWAP",
    "BNB-USDT-SWAP",
}

def should_use_lighter_ws(symbol: str) -> bool:
    """Check if symbol should use Lighter WebSocket for monitoring."""
    return symbol in LIGHTER_WS_SYMBOLS
PYTHON_CODE

# Check if WebSocket config already exists
if ! grep -q "LIGHTER_WS_SYMBOLS" app/main.py; then
    # Insert after imports, before anything else
    sed -i '/^from perpbot/a\\n# Lighter WebSocket configuration\nLIGHTER_WS_SYMBOLS = {\n    "ETH-USDT-SWAP",\n    "BTC-USDT-SWAP",\n    "SOL-USDT-SWAP",\n    "LINK-USDT-SWAP",\n    "DOGE-USDT-SWAP",\n    "BNB-USDT-SWAP",\n}\n' app/main.py
    echo "✅ Added Lighter WebSocket symbols configuration"
else
    echo "ℹ️  Lighter WebSocket symbols already configured"
fi

# Add WebSocket initialization after exchange connection
if ! grep -q "enable_websocket" app/main.py; then
    # Find the line after exchange connection and add WebSocket init
    cat > /tmp/ws_init.txt << 'WSLOAD'

    # Enable Lighter WebSocket for real-time monitoring
    if settings.exchange == "lighter":
        try:
            logger.info("🔌 Enabling Lighter WebSocket for real-time data...")
            exchange.enable_websocket(auto_subscribe_account=True)

            # Subscribe to orderbook and trades for test symbols
            for symbol in LIGHTER_WS_SYMBOLS:
                try:
                    # Convert OKX format to Lighter format (ETH-USDT-SWAP -> ETH/USDT)
                    lighter_symbol = symbol.replace("-SWAP", "").replace("-", "/")

                    # Orderbook subscription
                    def make_orderbook_handler(sym):
                        def handler(data):
                            bids = data.get("bids", [])
                            asks = data.get("asks", [])
                            if bids and asks:
                                logger.debug(f"📖 {sym}: {len(bids)} bids, {len(asks)} asks")
                        return handler

                    # Trade subscription
                    def make_trade_handler(sym):
                        def handler(data):
                            trade = data.get("trade", {})
                            logger.debug(f"💹 {sym}: {trade.get('side')} {trade.get('size')} @ {trade.get('price')}")
                        return handler

                    exchange.subscribe_orderbook_stream(lighter_symbol, make_orderbook_handler(symbol))
                    exchange.subscribe_trades_stream(lighter_symbol, make_trade_handler(symbol))
                    logger.info(f"✅ Subscribed to Lighter WebSocket: {symbol}")

                except Exception as e:
                    logger.error(f"❌ Failed to subscribe to {symbol}: {e}")

            logger.info(f"✅ Lighter WebSocket enabled for {len(LIGHTER_WS_SYMBOLS)} symbols")

        except Exception as e:
            logger.error(f"❌ Failed to enable Lighter WebSocket: {e}")
WSLOAD

    # This is more reliable - append to the file after we know exchange is created
    echo "Adding WebSocket initialization code..."
    echo "⚠️  Manual integration required - please check app/main.py"
fi

echo ""
echo "Next steps:"
echo "1. Review app/main.py for WebSocket initialization"
echo "2. Test with: docker compose down && docker compose up -d"
echo "3. Monitor logs: docker compose logs -f | grep -i 'websocket\|订阅'"
echo ""

EOF

echo ""
echo "========================================"
echo "Configuration Steps:"
echo "========================================"
echo "1. SSH to server and manually edit app/main.py"
echo "2. Add WebSocket initialization after exchange.connect()"
echo "3. Restart container to apply changes"
echo ""
echo "Quick SSH:"
echo "  ssh -i $SSH_KEY $REMOTE_HOST"
echo ""
