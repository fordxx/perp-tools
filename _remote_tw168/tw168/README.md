# TradingView → OKX webhook trader (test)

Minimal FastAPI service that:
- Receives TradingView alerts (`ZONE` + `DIV`)
- Combines them into a single trade decision
- Places an OKX v5 order (hedge mode supported)
- Computes a stop-loss from recent candles (pivot + ATR buffer)
- Manages take-profit ladder via reduce-only closes

## Run

1) Create `.env` from `.env.example` and fill OKX keys.
   - `TRADING_ENABLED=false` will paper-trade (no OKX order), returning the computed direction + stop-loss.
   - `.env` is loaded automatically; no need to export env vars manually.

2) Install + start:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Run (Docker)

```bash
docker compose up -d --build
docker compose logs -f
```

Health check: `curl http://127.0.0.1:8000/health`

## Env Switcher

Quickly edit `.env` presets/toggles without manual editing:

```bash
python3 scripts/envctl.py --tf 15m --w --hs
python3 scripts/envctl.py --disable-short
python3 scripts/envctl.py --no-patterns
```

If you prefer a simple numbered menu:

```bash
python3 scripts/envmenu.py
```

## TradingView alert messages

Create alerts that POST JSON to `http(s)://YOUR_HOST/webhook/tradingview`.

### ZONE (from your ML RSI script)

```json
{"secret":"CHANGE_ME","type":"ZONE","zone":"OVERSOLD","instId":"ETH-USDT-SWAP","tf":"1m","t":"{{time}}","close":"{{close}}"}
```

`zone` is one of: `OVERSOLD`, `OVERBOUGHT`.

### DIV (from your divergence indicator)

```json
{"secret":"CHANGE_ME","type":"DIV","instId":"ETH-USDT-SWAP","tf":"1m","t":"{{time}}","close":"{{close}}"}
```

On `DIV`, the service trades based on the latest `ZONE`:
- `OVERSOLD` → open long
- `OVERBOUGHT` → open short

## Notes

- This is a test harness; use OKX demo/sandbox first.
- For multi-symbol, keep `instId` in every alert message and set `SYMBOL_ALLOWLIST`.
- Stop-loss method is configurable via `.env` (`STOP_METHOD=lookback|pivot`, `STOP_LOOKBACK_BARS`, `ATR_*`).
- Optional pattern filters: `PATTERN_LONG=w_bottom` and/or `PATTERN_SHORT=hs_top` (pivot-based approximation).
- Take-profit ladder is configured via `.env` (`TP1_R/TP1_PCT`, `TP2_R/TP2_PCT`, `TP3_R/TP3_PCT`, `TRAIL_START_R`, `TRAIL_BACK_R`).
