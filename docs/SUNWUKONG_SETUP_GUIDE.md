# Sunwukong Exchange Setup Guide

This document provides a guide for setting up and connecting to the Sunwukong exchange.

## API Requirements

The following are the key requirements for integrating with the Sunwukong exchange API:

*   **API Types**: Both REST API and WebSocket are available.
*   **Authentication**: All API interactions require signature authentication.
*   **WebSocket**: WebSocket connections require a heartbeat mechanism to be maintained.
*   **Error Handling**: Developers must handle the specific error codes returned by the API.

## Configuration

When adding Sunwukong to the `config.yaml`, follow the structure below, referencing the `CONNECTION_MANAGEMENT.md` guide for details on each parameter.

```yaml
exchanges:
  sunwukong:
    market_data:
      rate_limit_per_sec: 10.0
      heartbeat_interval_sec: 30.0
      heartbeat_timeout_sec: 60.0
      max_latency_ms: 500.0
      circuit_open_error_streak: 5
      circuit_halfopen_wait_sec: 60.0

    trading:
      rate_limit_per_sec: 5.0
      trade_enabled: true
      api_key_env: SUNWUKONG_API_KEY
      api_secret_env: SUNWUKONG_API_SECRET
```

## API Key Management

As with other exchanges, API keys for Sunwukong must be managed securely using environment variables.

**Environment variables:**
```bash
export SUNWUKONG_API_KEY="your_api_key"
export SUNWUKONG_API_SECRET="your_api_secret"
```

**Security Principles:**
- Store API keys in environment variables.
- The configuration file should only reference the names of the environment variables.
- Never hardcode keys in source code or configuration files.
