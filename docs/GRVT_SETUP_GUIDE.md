# GRVT Exchange Setup Guide

This document provides a guide for setting up and connecting to the GRVT exchange.

## API Requirements

Based on the official documentation, here are the key requirements for GRVT API integration:

*   **Hosting**: Services are hosted in AWS Tokyo (ap-northeast-1).
*   **Authentication**:
    *   Authentication uses session cookies and API keys.
    *   An initial POST request to an auth endpoint (e.g., `https://edge.testnet.grvt.io/auth/api_key/login`) with the `api_key` is required.
    *   This returns a session cookie (`gravity=...`) and an `X-Grvt-Account-Id` header, which must be used in subsequent requests.
*   **SDK**: A Python SDK (`grvt-pysdk`) is available.
*   **Encoding**: APIs and WebSockets support "full" and "lite" encoding formats for field names to manage verbosity and performance.
*   **WebSocket Subscriptions**:
    *   Authenticated streams require the `GRVT_COOKIE` and `X-Grvt-Account-Id` to be sent during the handshake.
    *   Subscriptions are managed via JSON-RPC messages.
    *   A `sequence_number` is used to track message order and detect data loss. Snapshots have a sequence number of `0`, and deltas increment from there.

## Configuration

When adding GRVT to the `config.yaml`, the setup will be slightly different due to the session-based authentication. The `api_key` can be stored, but the session cookie will likely need to be managed dynamically by the connection client.

```yaml
exchanges:
  grvt:
    market_data:
      rate_limit_per_sec: 10.0
      heartbeat_interval_sec: 30.0
      # GRVT uses a sequence number system rather than a classic heartbeat
      # The client will need to monitor the sequence number for connection health
      max_latency_ms: 500.0
      circuit_open_error_streak: 5
      circuit_halfopen_wait_sec: 60.0

    trading:
      rate_limit_per_sec: 10.0
      trade_enabled: true
      api_key_env: GRVT_API_KEY
      # The secret/session token is dynamic and should be handled by the client
      # A placeholder for the account ID might be useful
      extra_config:
        account_id_env: GRVT_ACCOUNT_ID
        auth_url: "https://edge.testnet.grvt.io/auth/api_key/login"
```

## API Key Management

API keys must be provisioned from the GRVT UI.

**Environment variables:**
```bash
export GRVT_API_KEY="your_api_key"
# The Account ID is returned during auth and may need to be stored
export GRVT_ACCOUNT_ID="your_account_id"
```

**Authentication Flow:**

The GRVT client in `perp-tools` will need to implement the following logic:
1. On connection, send a POST request to the `auth_url` with the `GRVT_API_KEY`.
2. Extract the `gravity` session cookie and the `X-Grvt-Account-Id` from the response.
3. Use the cookie and account ID in all subsequent API and WebSocket requests.
4. The client must handle session expiry and re-authentication.
