# OKX Exchange Setup Guide

This document provides a guide for setting up and connecting to the OKX exchange.

## API Requirements

OKX uses a signature-based authentication method with a unique passphrase component.

*   **Authentication**: Signed requests use **HMAC-SHA256**. The signature is a Base64 encoding of the hash of the pre-string: `timestamp + method + requestPath + body`.
*   **Request Headers**: All private REST requests must include the following headers:
    *   `OK-ACCESS-KEY`: Your API Key.
    *   `OK-ACCESS-SIGN`: The HMAC-SHA256 signature.
    *   `OK-ACCESS-TIMESTAMP`: A UTC timestamp in ISO format (e.g., `2020-12-08T09:08:57.715Z`).
    *   `OK-ACCESS-PASSPHRASE`: Your unique API passphrase.
*   **Base URLs**:
    *   **REST API**: `https://www.okx.com`
    *   **Public WebSocket**: `wss://ws.okx.com:8443/ws/v5/public`
    *   **Private WebSocket**: `wss://ws.okx.com:8443/ws/v5/private`
*   **WebSocket**:
    *   Private WebSocket connections require a login message containing a signature.
    *   A `ping` message should be sent every 30 seconds to maintain the connection, with the server responding with `pong`.
*   **Demo Trading**: OKX provides a demo environment. To use it, add the header `x-simulated-trading: 1` to your requests.

## Configuration

Here is a template for adding OKX to the `config.yaml` file.

```yaml
exchanges:
  okx:
    market_data:
      rate_limit_per_sec: 10 # Placeholder, adjust based on docs
      heartbeat_interval_sec: 25
      heartbeat_timeout_sec: 35
      max_latency_ms: 500.0
      circuit_open_error_streak: 5
      circuit_halfopen_wait_sec: 60.0

    trading:
      rate_limit_per_sec: 10 # Placeholder, adjust based on docs
      trade_enabled: true
      api_key_env: OKX_API_KEY
      api_secret_env: OKX_API_SECRET
      api_passphrase_env: OKX_API_PASSPHRASE # Specific to OKX
      extra_config:
        base_url: "https://www.okx.com"
        ws_private_url: "wss://ws.okx.com:8443/ws/v5/private"
        demo_mode: false # Set to true to use x-simulated-trading header
```

## API Key Management

API keys, secrets, and passphrases can be generated from your OKX account settings.

**Environment variables:**

Store all three credentials securely as environment variables.

```bash
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_secret_key"
export OKX_API_PASSPHRASE="your_passphrase"
```

**Security Principles:**
- The passphrase cannot be recovered if lost, so store it securely.
- Link your API keys to specific IP addresses for enhanced security.
- Be aware that keys without an IP whitelist may expire after 14 days of inactivity.
