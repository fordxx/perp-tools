# Lighter WebSocket Integration

Complete WebSocket support for Lighter DEX real-time data streaming.

## Overview

The Lighter WebSocket integration provides real-time updates for:
- **Orderbook**: Live bid/ask updates (50ms intervals)
- **Trades**: Real-time trade executions
- **Positions**: Account position updates
- **Orders**: Order status changes
- **Account**: Balance and account state updates
- **Market Stats**: 24h volume, price changes, etc.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     LighterClient                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  REST API (lighter-sdk)                               │  │
│  │  - Market orders                                      │  │
│  │  - Limit orders                                       │  │
│  │  - Stop-loss/Take-profit                             │  │
│  │  - Position management                                │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  WebSocket Client (LighterWebSocketClient)           │  │
│  │  - Real-time orderbook                               │  │
│  │  - Trade executions                                   │  │
│  │  - Account updates                                    │  │
│  │  - Position/order updates                             │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### 1. Enable WebSocket

```python
from perpbot.exchanges.lighter import LighterClient

# Connect to Lighter
client = LighterClient()
client.connect()

# Enable WebSocket (auto-subscribes to account updates if trading enabled)
client.enable_websocket(auto_subscribe_account=True)
```

### 2. Subscribe to Public Channels

```python
# Orderbook updates (50ms intervals)
def on_orderbook(data):
    asks = data.get("asks", [])
    bids = data.get("bids", [])
    print(f"Orderbook: {len(bids)} bids, {len(asks)} asks")

client.subscribe_orderbook_stream("ETH/USDT", on_orderbook)

# Trade executions
def on_trade(data):
    trade = data.get("trade", {})
    price = trade.get("price")
    size = trade.get("size")
    side = trade.get("side")
    print(f"Trade: {side} {size} @ {price}")

client.subscribe_trades_stream("ETH/USDT", on_trade)

# Market statistics
def on_market_stats(data):
    stats = data.get("stats", {})
    volume_24h = stats.get("volume_24h")
    price_change = stats.get("price_change_24h")
    print(f"24h Volume: {volume_24h}, Change: {price_change}")

client.subscribe_market_stats_stream("ETH/USDT", on_market_stats)
```

### 3. Subscribe to Private Channels (Account Updates)

```python
# Position updates
def on_position(data):
    position = data.get("position", {})
    symbol = position.get("symbol")
    size = position.get("size")
    pnl = position.get("unrealized_pnl")
    print(f"Position update: {symbol} size={size} PnL={pnl}")

client.setup_position_update_handler(on_position)

# Order updates
def on_order(data):
    order = data.get("order", {})
    order_id = order.get("id")
    status = order.get("status")
    print(f"Order {order_id}: {status}")

client.setup_order_update_handler(on_order)
```

### 4. Disable WebSocket

```python
# Gracefully disconnect WebSocket
client.disable_websocket()

# Full cleanup
client.disconnect()
```

## WebSocket API Reference

### Public Methods

#### `enable_websocket(auto_subscribe_account=True)`
Enable WebSocket streaming.
- **Args**:
  - `auto_subscribe_account` (bool): Auto-subscribe to account updates if trading enabled
- **Raises**: RuntimeError if not connected

#### `disable_websocket()`
Disable and disconnect WebSocket.

#### `subscribe_orderbook_stream(symbol, callback)`
Subscribe to real-time orderbook updates.
- **Args**:
  - `symbol` (str): Trading pair (e.g., "ETH/USDT")
  - `callback` (Callable): Function to handle updates
- **Update frequency**: 50ms

#### `subscribe_trades_stream(symbol, callback)`
Subscribe to real-time trade executions.
- **Args**:
  - `symbol` (str): Trading pair (e.g., "ETH/USDT")
  - `callback` (Callable): Function to handle trades

#### `subscribe_market_stats_stream(symbol, callback)`
Subscribe to market statistics.
- **Args**:
  - `symbol` (str): Trading pair or "all" for all markets
  - `callback` (Callable): Function to handle stats

#### `setup_position_update_handler(handler)`
Set callback for position updates (requires trading enabled).
- **Args**:
  - `handler` (Callable): Function to handle position updates

#### `setup_order_update_handler(handler)`
Set callback for order updates (requires trading enabled).
- **Args**:
  - `handler` (Callable): Function to handle order updates

## Message Formats

### Orderbook Update
```json
{
  "channel": "order_book/1",
  "type": "orderbook",
  "asks": [
    {"price": "3425.50", "size": "1.234"},
    {"price": "3425.60", "size": "0.567"}
  ],
  "bids": [
    {"price": "3425.40", "size": "2.345"},
    {"price": "3425.30", "size": "1.678"}
  ]
}
```

### Trade Execution
```json
{
  "channel": "trade/1",
  "type": "trade",
  "trade": {
    "price": "3425.45",
    "size": "0.123",
    "side": "buy",
    "timestamp": 1703001234567
  }
}
```

### Position Update
```json
{
  "channel": "account_all_positions/694324",
  "type": "position_update",
  "position": {
    "market_id": 1,
    "symbol": "ETH",
    "size": "0.5",
    "entry_price": "3400.00",
    "unrealized_pnl": "12.75",
    "liquidation_price": "2800.00"
  }
}
```

### Order Update
```json
{
  "channel": "account_all_orders/694324",
  "type": "order_update",
  "order": {
    "id": "123456",
    "market_id": 1,
    "side": "buy",
    "price": "3420.00",
    "size": "0.1",
    "filled_size": "0.05",
    "status": "partially_filled"
  }
}
```

## Implementation Details

### Connection Management
- **Auto-reconnection**: Exponential backoff (5s → 60s max)
- **Heartbeat**: 20s ping interval, 10s timeout
- **Resubscription**: Automatic after reconnection

### Threading Model
- WebSocket runs in background asyncio event loop (same as REST client)
- Callbacks executed in event loop context
- Thread-safe access via `_run_coro()`

### Authentication
- Public channels: No authentication required
- Private channels: Requires Account Index
- Auth token: Optional, managed by WebSocket client

### Error Handling
- Connection errors: Automatic reconnection
- Callback errors: Logged, don't crash WebSocket
- Subscription errors: Logged and retried on reconnection

## Testing

Run the WebSocket integration test:

```bash
cd /home/fordxx/perp-tools
python test_lighter_websocket.py
```

Expected output:
```
[1/5] Connecting to Lighter REST API...
✅ Connected successfully
   Trading enabled: True
   Markets loaded: 15

[2/5] Enabling WebSocket...
✅ WebSocket enabled
   WS enabled: True
   WS client: active

[3/5] Subscribing to orderbook for ETH/USDT...
✅ Subscribed to Lighter orderbook stream: ETH/USDT (market_id=1)

[4/5] Subscribing to trades for ETH/USDT...
✅ Subscribed to Lighter trades stream: ETH/USDT (market_id=1)

[5/5] Setting up account update handlers...
✅ Registered Lighter position update handler
✅ Registered Lighter order update handler

Collecting WebSocket updates for 30 seconds...
📖 Orderbook update [order_book/1]: 50 asks, 50 bids
   Best bid: 3425.40 | Best ask: 3425.50 | Spread: 0.10
💹 Trade executed: BUY 0.1230 @ 3425.45
...
```

## Configuration

WebSocket settings are controlled via environment variables:

```bash
# Lighter credentials (required for private channels)
LIGHTER_API_KEY_PRIVATE_KEY=0xf3ea53c474f622e2171e26fec3c8cd93c30d0e211c5d4807f6f2584c5c3253ea373db728d443631b
LIGHTER_ACCOUNT_INDEX=694324
LIGHTER_API_KEY_INDEX=0

# Environment (default: mainnet)
LIGHTER_ENV=mainnet

# WebSocket endpoints (auto-selected based on env)
# Mainnet: wss://mainnet.zklighter.elliot.ai/stream
# Testnet: wss://testnet.zklighter.elliot.ai/stream
```

## Troubleshooting

### WebSocket not connecting
1. Check network connectivity to `wss://mainnet.zklighter.elliot.ai/stream`
2. Verify firewall allows WebSocket connections
3. Check logs for connection errors

### No account updates received
1. Verify `LIGHTER_ACCOUNT_INDEX` is correct (e.g., 694324)
2. Check trading is enabled: `client._trading_enabled == True`
3. Ensure you have an active position or open order

### Orderbook updates missing
1. Verify market exists: Check `client._markets` for symbol
2. Ensure subscription succeeded (check logs)
3. Market may be inactive (low volume)

### High CPU usage
1. Reduce number of subscriptions
2. Use specific symbols instead of "all" markets
3. Implement throttling in callbacks

## Performance

- **Orderbook updates**: ~20 messages/second (50ms intervals)
- **Trade updates**: Variable (depends on market activity)
- **Account updates**: Triggered by state changes
- **Memory overhead**: ~5-10MB per WebSocket connection
- **CPU overhead**: <1% for typical usage

## Deployment

Deploy WebSocket updates to remote server:

```bash
cd /home/fordxx/perp-tools/_remote_tw168/tw168
./deploy_lighter_websocket.sh
```

This will:
1. Sync source code to remote server
2. Rebuild Docker image with WebSocket support
3. Restart container
4. Verify deployment

## Next Steps

1. **Integration with Trading Bot**: Connect WebSocket callbacks to trading logic
2. **Risk Management**: Use real-time position updates for risk monitoring
3. **Order Management**: Track order status in real-time
4. **Market Making**: Use orderbook stream for tight spreads
5. **Analytics**: Collect trade data for analysis

## References

- [Lighter WebSocket API Documentation](https://apidocs.lighter.xyz/docs/websocket-reference)
- [lighter-python SDK](https://github.com/elliottech/lighter-python)
- WebSocket client: `/home/fordxx/perp-tools/src/perpbot/exchanges/lighter_websocket.py`
- Integration: `/home/fordxx/perp-tools/src/perpbot/exchanges/lighter.py`
