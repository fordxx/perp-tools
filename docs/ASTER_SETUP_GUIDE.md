# AsterDex Exchange Setup Guide

This document provides a guide for setting up and connecting to the AsterDex exchange for perpetuals trading.

## API Requirements

Information gathered from public documentation indicates the following requirements for the AsterDex API:

*   **Base URL**: All API requests should be sent to `https://fapi.asterdex.com`.
*   **Data Format**: All API responses are in JSON format.
*   **Timestamps**: All timestamp fields are in milliseconds.
*   **Authentication**:
    *   Secure endpoints require an API Key.
    *   The API key must be sent in the `X-MBX-APIKEY` HTTP header.
    *   Signed requests use HMAC-SHA256, which is a common standard. The client will need to implement the signing logic.
*   **Error Handling**: The API uses standard HTTP error codes (4xx for client errors, 5xx for server errors).

## Configuration

Here is a template for adding AsterDex to the `config.yaml` file.

```yaml
exchanges:
  aster:
    market_data:
      rate_limit_per_sec: 10.0 # Placeholder, adjust as needed
      heartbeat_interval_sec: 30.0
      heartbeat_timeout_sec: 60.0
      max_latency_ms: 500.0
      circuit_open_error_streak: 5
      circuit_halfopen_wait_sec: 60.0

    trading:
      rate_limit_per_sec: 5.0 # Placeholder, adjust as needed
      trade_enabled: true
      api_key_env: ASTER_API_KEY
      api_secret_env: ASTER_API_SECRET
      extra_config:
        base_url: "https://fapi.asterdex.com"
```

## API Key Management

API keys can be generated from the API management section on the AsterDex website after connecting a wallet.

**Environment variables:**

Store your credentials securely as environment variables. The application will use these variables for authentication.

```bash
export ASTER_API_KEY="your_api_key"
export ASTER_API_SECRET="your_secret_key"
```

**Security Principles:**
- Create API keys with the principle of least privilege.
- Never expose your secret key. It is only visible upon creation.
- Store keys in environment variables, not in code or configuration files.
