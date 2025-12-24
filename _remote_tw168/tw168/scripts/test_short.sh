#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Load `.env` if present (so you don't have to export vars manually).
if [[ -z "${TV_WEBHOOK_SECRET:-}" ]] && [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

SECRET="${TV_WEBHOOK_SECRET:-CHANGE_ME}"
INST_ID="${1:-ETH-USDT-SWAP}"
TF="${2:-1m}"
BASE_URL="${3:-http://127.0.0.1:8000}"

echo "[1/3] Health check..."
curl -sS "${BASE_URL}/health" && echo

TS_ZONE="$(date +%s%3N)"
TS_DIV="$(date +%s%3N)"
NOW_HUMAN="$(date '+%F %T')"

echo "[2/3] ${NOW_HUMAN} ZONE=OVERBOUGHT (short filter)..."
curl -sS -X POST "${BASE_URL}/webhook/tradingview" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{"secret":"${SECRET}","type":"ZONE","zone":"OVERBOUGHT","instId":"${INST_ID}","tf":"${TF}","t":"test_zone_${TS_ZONE}"}
JSON
echo

NOW_HUMAN="$(date '+%F %T')"
echo "[3/3] ${NOW_HUMAN} DIV (should open short in paper mode)..."
curl -sS -X POST "${BASE_URL}/webhook/tradingview" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{"secret":"${SECRET}","type":"DIV","instId":"${INST_ID}","tf":"${TF}","t":"test_div_${TS_DIV}"}
JSON
echo
