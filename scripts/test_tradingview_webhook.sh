#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${1:-http://127.0.0.1:8000}"
INST_ID="${2:-ETH-USDT-SWAP}"
TF="${3:-1m}"
EXCHANGE="${4:-}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

SECRET="${PERPBOT_TV_WEBHOOK_SECRET:-${TV_WEBHOOK_SECRET:-CHANGE_ME}}"

echo "[1/3] Health check..."
curl -sS "${BASE_URL}/health/tradingview" && echo

echo "[2/3] Send ZONE=OVERSOLD..."
TS_ZONE="$(date +%s%3N)"
EX_FIELD=""
if [[ -n "${EXCHANGE}" ]]; then
  EX_FIELD=",\"exchange\":\"${EXCHANGE}\""
fi
curl -sS -X POST "${BASE_URL}/webhook/tradingview" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{"secret":"${SECRET}","type":"ZONE","zone":"OVERSOLD","instId":"${INST_ID}","tf":"${TF}","t":"test_zone_${TS_ZONE}"${EX_FIELD}}
JSON
echo

echo "[3/3] Send DIV..."
TS_DIV="$(date +%s%3N)"
curl -sS -X POST "${BASE_URL}/webhook/tradingview" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{"secret":"${SECRET}","type":"DIV","instId":"${INST_ID}","tf":"${TF}","t":"test_div_${TS_DIV}"${EX_FIELD}}
JSON
echo
