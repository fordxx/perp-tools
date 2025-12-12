# Binance Exchange Setup Guide

This document provides a guide for setting up and connecting to the Binance exchange, specifically for USDⓈ-M Futures.

## API Requirements

Based on the official API documentation, here are the key requirements for integrating with the Binance Futures API:

*   **Authentication**: Signed requests use **HMAC-SHA256**. The API key is sent in the `X-MBX-APIKEY` header.
*   **Base URLs**:
    *   **REST API**: `https://fapi.binance.com`
    *   **WebSocket**: `wss://fstream.binance.com`
*   **Timestamps**: Requests must include a timestamp, and the `recvWindow` parameter is available to specify the validity window for a request.
*   **Rate Limits**: Binance enforces strict rate limits based on IP and UID. The client must handle `429` and `418` error codes gracefully.
*   **WebSocket Heartbeat**: The WebSocket connection must be kept alive by responding to `ping` frames with `pong` frames.

## Configuration

Here is a template for adding Binance to the `config.yaml` file.

```yaml
exchanges:
  binance:
    market_data:
      rate_limit_per_sec: 20 # Placeholder, adjust based on weight limits
      heartbeat_interval_sec: 180 # 3 minutes for ping
      heartbeat_timeout_sec: 600 # 10 minutes for pong response
      max_latency_ms: 500.0
      circuit_open_error_streak: 5
      circuit_halfopen_wait_sec: 60.0

    trading:
      rate_limit_per_sec: 10 # Placeholder, adjust based on weight limits
      trade_enabled: true
      api_key_env: BINANCE_API_KEY
      api_secret_env: BINANCE_API_SECRET
      extra_config:
        base_url: "https://fapi.binance.com"
        ws_base_url: "wss://fstream.binance.com/ws"
        recv_window: 5000
```

## API Key Management

API keys can be generated from your Binance account settings. Ensure the key has permissions enabled for Futures trading.

**Environment variables:**

Store your credentials securely as environment variables.

```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_secret_key"
```

**Security Principles:**
- Do not hardcode API keys in the source code.
- Restrict API key access by IP address if possible.
- Use separate keys for different applications.
