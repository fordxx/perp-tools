# Backpack Exchange Setup Guide

This document provides a guide for setting up and connecting to the Backpack exchange.

## API Requirements

Based on the official documentation, here are the key requirements for the Backpack API:

*   **Authentication**: All requests must be authenticated using a signature from an **ED25519 keypair**. This is a different mechanism from the HMAC-SHA256 used by many other exchanges. The client implementation must be able to generate these signatures.
*   **Base URLs**:
    *   **REST API**: `https://api.backpack.exchange/`
    *   **WebSocket API**: `wss://ws.backpack.exchange/`
*   **Timestamps**: Timestamps are in microseconds for the new WebSocket API, while other parts may use milliseconds. This needs to be handled carefully.
*   **API Keys**: The public and private keys for the ED25519 keypair serve as the API credentials.

## Configuration

Here is a template for adding Backpack to the `config.yaml` file. The private key (secret) needs to be handled carefully by the client that performs the signing.

```yaml
exchanges:
  backpack:
    market_data:
      rate_limit_per_sec: 20 # Placeholder, adjust as needed
      # WebSocket uses a subscription model, not a classic heartbeat
      max_latency_ms: 500.0
      circuit_open_error_streak: 5
      circuit_halfopen_wait_sec: 60.0

    trading:
      rate_limit_per_sec: 20 # Placeholder, adjust as needed
      trade_enabled: true
      api_key_env: BACKPACK_API_KEY # This will be the public key
      api_secret_env: BACKPACK_API_SECRET # This will be the private key
      extra_config:
        base_url: "https://api.backpack.exchange/"
        ws_base_url: "wss://ws.backpack.exchange/"
```

## API Key Management

The API credentials for Backpack are an ED25519 keypair.

**Environment variables:**

You must store your ED25519 keypair as environment variables.

*   `BACKPACK_API_KEY`: The **public key** of your ED25519 keypair.
*   `BACKPACK_API_SECRET`: The **private key** of your ED25519 keypair.

```bash
export BACKPACK_API_KEY="your_ed25519_public_key"
export BACKPACK_API_SECRET="your_ed25519_private_key"
```

**Implementation Note:** The `perp-tools` client for Backpack must be specifically coded to handle ED25519 signing. Standard HMAC-SHA256 libraries will not work. The signature process involves signing the request parameters (as a windowed timestamp and instruction) with the private key.
