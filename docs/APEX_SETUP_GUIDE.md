# ApeX (Omni) Exchange Setup Guide

This document provides a guide for setting up and connecting to the ApeX Omni exchange (API V3).

## API Requirements

ApeX Omni uses a dual authentication system: a standard API key for most private endpoints, and an additional ZK (StarkKey) signature for sensitive operations like withdrawals and transfers.

*   **Standard Authentication**:
    *   Requires an **API Key**, **Secret**, and **Passphrase**.
    *   This is used for most authenticated endpoints like checking account status, viewing orders, and placing trades.
*   **ZK-Proof (StarkKey) Authentication**:
    *   For actions like withdrawals and transfers, an additional layer of signing is required.
    *   This involves a `seeds` value (obtained from Omni Key management) and a layer-2 key (`l2Key`).
*   **Python SDK**: An official Python SDK is available and recommended: `pip3 install apexomni`. The SDK handles the complex signing processes.
*   **Base URLs**: The SDK uses configurable endpoints for testnet and mainnet (e.g., `APEX_OMNI_HTTP_TEST`, `APEX_OMNI_HTTP_MAIN`).

## Configuration

Due to the complex key requirements, the configuration for ApeX will be more extensive.

```yaml
exchanges:
  apex:
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
      api_key_env: APEX_API_KEY
      api_secret_env: APEX_API_SECRET
      api_passphrase_env: APEX_API_PASSPHRASE
      extra_config:
        # ZK / StarkKey credentials
        zk_seeds_env: APEX_ZK_SEEDS
        zk_l2key_env: APEX_ZK_L2KEY
        # Network config for the SDK
        network_id: "NETWORKID_MAIN" # or "NETWORKID_OMNI_TEST_BNB"
        endpoint: "APEX_OMNI_HTTP_MAIN" # or "APEX_OMNI_HTTP_TEST"

```

## API Key Management

You will need to manage two sets of credentials for ApeX Omni.

**1. Standard API Credentials:**
These are generated from the key management page on the ApeX Omni website.

```bash
export APEX_API_KEY="your_api_key"
export APEX_API_SECRET="your_secret_key"
export APEX_API_PASSPHRASE="your_passphrase"
```

**2. ZK (StarkKey) Credentials:**
These are also obtained from the Omni Key management section and are required for the SDK to sign withdrawal and transfer operations.

```bash
export APEX_ZK_SEEDS="your_zk_seeds_value"
export APEX_ZK_L2KEY="your_l2key_value" # Optional, can be derived by the SDK
```

**Implementation Note:** Given the complexity, using the official `apexomni` Python SDK is strongly recommended as it abstracts away the details of both standard and ZK-based signature generation.
