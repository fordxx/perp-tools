#!/usr/bin/env bash
set -euo pipefail

# Load `.env` if present (so you don't have to export vars manually).
if [[ -z "${TV_WEBHOOK_SECRET:-}" ]] && [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

# 1) Fill these values (or set TV_WEBHOOK_SECRET)
SECRET="${TV_WEBHOOK_SECRET:-CHANGE_ME}"
INST_ID="HYPE-USDT-SWAP"
TF="1m"
BASE_URL="http://127.0.0.1:8000"

# Optional (used as entry reference for paper mode). Leave empty to let the server use live candles close.
CLOSE=""

echo "[1/3] Health check..."
curl -sS "${BASE_URL}/health" && echo

echo "[2/3] Send ZONE=OVERSOLD..."
TS_ZONE="$(date +%s%3N)"
if [[ -n "${CLOSE}" ]]; then
  CLOSE_FIELD=",\"close\":\"${CLOSE}\""
else
  CLOSE_FIELD=""
fi
curl -sS -X POST "${BASE_URL}/webhook/tradingview" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{"secret":"${SECRET}","type":"ZONE","zone":"OVERSOLD","instId":"${INST_ID}","tf":"${TF}","t":"test_zone_${TS_ZONE}"${CLOSE_FIELD}}
JSON
echo

echo "[3/3] Send DIV..."
TS_DIV="$(date +%s%3N)"
curl -sS -X POST "${BASE_URL}/webhook/tradingview" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{"secret":"${SECRET}","type":"DIV","instId":"${INST_ID}","tf":"${TF}","t":"test_div_${TS_DIV}"${CLOSE_FIELD}}
JSON
echo
