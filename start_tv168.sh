#!/usr/bin/env bash
# 一键加载 tv168 专用 env 并启动 TradingView webhook 服务
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env.tv168
set +a
bash scripts/run_tv168.sh
