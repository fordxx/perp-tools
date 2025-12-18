#!/usr/bin/env bash
# 一键加载 tv168 专用 env 并启动 TradingView webhook 服务，并记录日志
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env.tv168
set +a
LOGFILE="tv168_$(date +%Y%m%d_%H%M%S).log"
echo "日志记录到 $LOGFILE"
bash scripts/run_tv168.sh | tee "$LOGFILE"
