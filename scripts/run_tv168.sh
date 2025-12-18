#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

is_port_in_use() {
  local p="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | grep -qE "[:.]${p}\\b"
  else
    netstat -ltn 2>/dev/null | grep -qE "[:.]${p}\\b"
  fi
}

if is_port_in_use "${PORT}"; then
  echo "Port ${PORT} is already in use; searching for a free port..." >&2
  for p in $(seq $((PORT + 1)) $((PORT + 20))); do
    if ! is_port_in_use "${p}"; then
      PORT="${p}"
      echo "Using PORT=${PORT}" >&2
      break
    fi
  done
fi

PYTHONPATH=src exec .venv/bin/python -m perpbot.integrations.tradingview.standalone --host "${HOST}" --port "${PORT}"
