# Bitget Exchange Setup Guide

This document provides a guide for setting up and connecting to the Bitget exchange.

## API Requirements

Bitget's API authentication is similar to OKX, requiring a passphrase.

*   **Authentication**: Signed requests use **HMAC-SHA256**. The signature is a Base64 encoding of the pre-string: `timestamp + method.toUpperCase() + requestPath + "?" + queryString + body`.
*   **Request Headers**: All private REST requests must include:
    *   `ACCESS-KEY`: Your API Key.
    *   `ACCESS-SIGN`: The HMAC-SHA256 signature.
    *   `ACCESS-TIMESTAMP`: The timestamp of your request in milliseconds since the Epoch.
    *   `ACCESS-PASSPHRASE`: Your unique API passphrase.
    *   `Content-Type`: `application/json` for POST requests.
*   **Base URLs**:
    *   **REST API**: `https://api.bitget.com`
    *   **WebSocket**: (Refer to official docs for specific stream URLs)
*   **Rate Limits**: The default rate limit is 10 requests/second, with public market data endpoints having a limit of 20 requests/second.

## Configuration

Here is a template for adding Bitget to the `config.yaml` file.

```yaml
exchanges:
  bitget:
    market_data:
      rate_limit_per_sec: 20
      heartbeat_interval_sec: 25 # WebSocket requires ping every 30s
      heartbeat_timeout_sec: 35
      max_latency_ms: 500.0
      circuit_open_error_streak: 5
      circuit_halfopen_wait_sec: 60.0

    trading:
      rate_limit_per_sec: 10
      trade_enabled: true
      api_key_env: BITGET_API_KEY
      api_secret_env: BITGET_API_SECRET
      api_passphrase_env: BITGET_API_PASSPHRASE # Specific to Bitget
      extra_config:
        base_url: "https://api.bitget.com"
```

## API Key Management

API keys, secrets, and passphrases can be generated from your Bitget account settings.

**Environment variables:**

Store all three credentials securely as environment variables.

```bash
export BITGET_API_KEY="your_api_key"
export BITGET_API_SECRET="your_secret_key"
export BITGET_API_PASSPHRASE="your_passphrase"
```

**Security Principles:**
- It is strongly recommended to bind your API keys to a specific IP address for security.
- The passphrase is required for every signed request and should be treated with the same level of security as your secret key.
- Do not hardcode credentials in source code.
