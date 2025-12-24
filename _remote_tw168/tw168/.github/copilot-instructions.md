# Copilot instructions (tw168 / tv168)

## Big picture
- This repo is a **FastAPI webhook service** that receives TradingView alerts and trades on **OKX v5** (optionally an **Extended** client).
- Signal gating is **2-step**: a `ZONE` message stores market state, then a `DIV` message triggers a trade using the latest stored zone.
- State is **in-memory only** (no DB): `ZONE` TTL + cooldown + dedupe are enforced per `(instId, tf)`.

## Key files / responsibilities
- [app/main.py](../app/main.py): FastAPI app, `/webhook/tradingview` handler, symbol normalization, gating (secret/allowlist/dedupe/cooldown), stop-loss + sizing, order placement, and plan registration.
- [app/config.py](../app/config.py): `.env` loading + `Settings` (all runtime behavior is driven by env vars).
- [app/state.py](../app/state.py): in-memory `ZONE` store, cooldown timestamps, dedupe cache.
- [app/risk.py](../app/risk.py): candle fetch (OKX REST), ATR + stop methods (`pivot` / `lookback`), and optional pattern filters (`w_bottom`, `head_shoulders_top`).
- [app/okx.py](../app/okx.py): minimal OKX REST client (HMAC signing) + order/position helpers.
- [app/trade_manager.py](../app/trade_manager.py): background manager loop that executes TP ladder + trailing exits using **reduce-only market** closes.
- [app/ws_fills.py](../app/ws_fills.py) + [app/fill_tracker.py](../app/fill_tracker.py): websocket fill notifications and labeling (TP/SL/trail).
- [app/notify.py](../app/notify.py): optional Telegram notifications (best-effort; no hard failure if unset).

## Local run / smoke tests
- Python:
  - `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
  - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Docker: `docker compose up -d --build`
- Smoke test webhooks:
  - `bash scripts/test_long.sh [INST_ID] [TF] [BASE_URL]`
  - `bash scripts/test_short.sh [INST_ID] [TF] [BASE_URL]`
  - Health: `curl http://127.0.0.1:8000/health`

## Webhook contract (what the handler expects)
- Endpoint: `POST /webhook/tradingview` with JSON matching `TvPayload` in [app/main.py](../app/main.py).
- Required fields: `secret`, `type`, `instId` (plus `zone` for `ZONE`).
- `type` is `ZONE` or `DIV`:
  - `ZONE` stores `{zone, close}` for `key = f"{instId}:{tf}"`.
  - `DIV` reads latest `ZONE` and decides direction: `OVERSOLD -> buy/long`, `OVERBOUGHT -> sell/short`.

## Repo-specific conventions to keep
- **Symbol normalization**: TradingView symbols may be mapped (e.g. `ETHUSDT` → `ETH-USDT-SWAP`, strip `.P`). Keep logic in `_normalize_inst_id()`.
- **Per-key state**: use `key = f"{instId}:{tf}"` consistently for zone/cooldown.
- **Dedupe key**: `f"{type}:{instId}:{tf}:{t}"` with a 30-minute TTL (prevents repeated TradingView sends).
- **OKX hedge mode**: entry `side` and `posSide` are coupled (`buy+long`, `sell+short`). Closing uses opposite `side` with same `posSide` and `reduceOnly=true`.
- **Client order IDs**: OKX `clOrdId` is limited to **32 chars**; code truncates (`[:32]`). Preserve this when changing ID composition.
- **Sizing**:
  - If `RISK_PER_TRADE_USDT > 0`, size is computed from `|entry - sl|` and contract `ctVal` from `get_instrument_info()`.
  - Otherwise use `ORDER_SZ`.

## Exchange selection (important dependency note)
- `EXCHANGE=okx` is the default and is the only mode covered by `requirements.txt`.
`EXCHANGE=extended` uses [app/extended.py](../app/extended.py) which imports `x10` + `fast_stark_crypto` and is **not** in `requirements.txt`; avoid changing Extended code unless you also update dependency/install docs accordingly.

## When modifying trade logic
- Keep the flow order in [app/main.py](../app/main.py): validate → dedupe → get zone → cooldown → compute entry → fetch candles → optional pattern filter → compute SL → paper-trade shortcut → live order placement → mark traded + clear zone → register plan.
- If you touch take-profit/trailing behavior, update both:
  - plan management in [app/trade_manager.py](../app/trade_manager.py)
  - fill labeling used by [app/ws_fills.py](../app/ws_fills.py)/[app/fill_tracker.py](../app/fill_tracker.py)

## Repo hygiene
- Avoid editing `*.backup*` files under `app/`; they are historical snapshots.
