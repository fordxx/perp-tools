# Exchange Runtime Configs

These configs are optional. They let you tune:
- default symbols per exchange
- soak/stress behaviour without editing code

Secrets should stay in `.env` (never committed).

Files:
- `okx.yaml`
- `binance.yaml`
- `bybit.yaml`
- `bitget.yaml`
- `hyperliquid.yaml`
- `paradex.yaml`
- `extended.yaml`
- `lighter.yaml`

Usage:
- Normal auto-test default symbol: `python test_exchanges.py extended --auto-test`
- Soak (rotate symbols from YAML): `./run_exchange_test.sh extended --soak 3600 --interval 2`
