# Lighter WebSocket - Quick Start Guide

## 5-Minute Integration

### 1. Enable WebSocket (1 line of code)

```python
# After connecting to Lighter
client = LighterClient()
client.connect()

# Enable WebSocket - Done!
client.enable_websocket(auto_subscribe_account=True)
```

### 2. Subscribe to Orderbook (3 lines)

```python
def on_orderbook(data):
    print(f"Orderbook update: {len(data.get('bids', []))} bids")

client.subscribe_orderbook_stream("ETH/USDT", on_orderbook)
```

### 3. Subscribe to Trades (3 lines)

```python
def on_trade(data):
    print(f"Trade: {data.get('trade', {})}")

client.subscribe_trades_stream("ETH/USDT", on_trade)
```

### 4. Monitor Positions (3 lines)

```python
def on_position(data):
    print(f"Position: {data}")

client.setup_position_update_handler(on_position)
```

### 5. Monitor Orders (3 lines)

```python
def on_order(data):
    print(f"Order: {data}")

client.setup_order_update_handler(on_order)
```

## Complete Example (Copy-Paste Ready)

```python
#!/usr/bin/env python3
from perpbot.exchanges.lighter import LighterClient
import time

# Connect
client = LighterClient()
client.connect()

# Enable WebSocket
client.enable_websocket(auto_subscribe_account=True)

# Orderbook callback
def on_orderbook(data):
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    if bids and asks:
        print(f"📖 {len(bids)} bids | {len(asks)} asks")

# Trade callback
def on_trade(data):
    trade = data.get("trade", {})
    print(f"💹 {trade.get('side')} {trade.get('size')} @ {trade.get('price')}")

# Subscribe
client.subscribe_orderbook_stream("ETH/USDT", on_orderbook)
client.subscribe_trades_stream("ETH/USDT", on_trade)

# Run for 60 seconds
print("Listening to Lighter WebSocket...")
time.sleep(60)

# Cleanup
client.disable_websocket()
client.disconnect()
print("Done!")
```

## Test on Remote Server

```bash
# SSH to server
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169

# Navigate to project
cd /home/ubuntu/tw168

# Check logs for WebSocket activity
docker compose logs -f | grep -i "websocket\|订阅\|subscrib"
```

## Enable in Production

Edit `/home/ubuntu/tw168/app/main.py`:

```python
# After exchange connection
if exchange.name == "lighter":
    try:
        exchange.enable_websocket(auto_subscribe_account=True)
        logger.info("✅ Lighter WebSocket enabled")
    except Exception as e:
        logger.error("❌ Failed to enable WebSocket: %s", e)
```

## Message Format Examples

### Orderbook Update
```json
{
  "channel": "order_book/1",
  "asks": [{"price": "3425.50", "size": "1.234"}],
  "bids": [{"price": "3425.40", "size": "2.345"}]
}
```

### Trade Execution
```json
{
  "channel": "trade/1",
  "trade": {
    "price": "3425.45",
    "size": "0.123",
    "side": "buy"
  }
}
```

### Position Update
```json
{
  "channel": "account_all_positions/694324",
  "position": {
    "symbol": "ETH",
    "size": "0.5",
    "unrealized_pnl": "12.75"
  }
}
```

## Troubleshooting

### No updates received?
```python
# Check status
print(f"WebSocket enabled: {client._ws_enabled}")
print(f"Connected: {client._ws_client._connected if client._ws_client else False}")
```

### Check logs
```bash
# On server
docker compose logs | grep -i websocket | tail -50
```

### Restart WebSocket
```python
client.disable_websocket()
time.sleep(1)
client.enable_websocket(auto_subscribe_account=True)
```

## Quick Commands

```bash
# Deploy updates
cd /home/fordxx/perp-tools/_remote_tw168/tw168
./deploy_lighter_websocket.sh

# Run test
cd /home/fordxx/perp-tools
python test_lighter_websocket.py

# Check server logs
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 \
  'cd /home/ubuntu/tw168 && docker compose logs -f'
```

## API Reference

| Method | Description |
|--------|-------------|
| `enable_websocket()` | Enable WebSocket streaming |
| `disable_websocket()` | Disable WebSocket |
| `subscribe_orderbook_stream(symbol, callback)` | Real-time orderbook |
| `subscribe_trades_stream(symbol, callback)` | Real-time trades |
| `subscribe_market_stats_stream(symbol, callback)` | Market statistics |
| `setup_position_update_handler(handler)` | Position updates |
| `setup_order_update_handler(handler)` | Order updates |

## Need More Details?

See full documentation: [LIGHTER_WEBSOCKET.md](./LIGHTER_WEBSOCKET.md)
