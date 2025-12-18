#!/usr/bin/env bash
#
# OKX tv168 测试脚本 - 渐进式验证流程
# 用法：bash scripts/test_tv168_okx.sh [paper|testnet]
#
set -euo pipefail

cd "$(dirname "$0")/.."

MODE="${1:-paper}"
HOST="${TV168_HOST:-http://127.0.0.1:8000}"
SECRET="${PERPBOT_TV_WEBHOOK_SECRET:-CHANGE_ME}"

echo "========================================="
echo "tv168 OKX 测试：$MODE 模式"
echo "========================================="
echo ""

case "$MODE" in
  paper)
    echo "📝 Paper 模式：只计算，不下单"
    echo ""
    echo "前置条件："
    echo "  1. 启动 tv168 服务：bash scripts/run_tv168.sh"
    echo "  2. .env 里设置 PERPBOT_TV_TRADING_ENABLED=false（或不设置）"
    echo ""
    ;;
  testnet)
    echo "🧪 Testnet 模式：OKX Demo Trading 下单"
    echo ""
    echo "前置条件："
    echo "  1. 启动 tv168 服务：bash scripts/run_tv168.sh"
    echo "  2. .env 里设置："
    echo "     - OKX_API_KEY=..."
    echo "     - OKX_API_SECRET=..."
    echo "     - OKX_PASSPHRASE=..."
    echo "     - OKX_ENV=testnet"
    echo "     - PERPBOT_TV_TRADING_ENABLED=true"
    echo "     - PERPBOT_TV_HEDGE_MODE=true（如果需要双向持仓）"
    echo "     - PERPBOT_TV_PLACE_STOP_LOSS=true（如果需要止损单）"
    echo "  3. OKX 账户设置 → 仓位模式 → 双向持仓"
    echo ""
    ;;
  *)
    echo "❌ 未知模式：$MODE"
    echo "用法：bash scripts/test_tv168_okx.sh [paper|testnet]"
    exit 1
    ;;
esac

read -p "按 Enter 继续测试，或 Ctrl-C 退出..."

echo ""
echo "Step 1: 检查服务健康状态"
echo "--------------------------------------"
curl -s "${HOST}/health/tradingview" | python3 -m json.tool || echo "❌ 服务未启动"

echo ""
echo ""
echo "Step 2: 获取配置选项"
echo "--------------------------------------"
curl -s "${HOST}/api/tv168/options" | python3 -m json.tool

echo ""
echo ""
echo "Step 3: 拉取 OKX USDT 永续合约列表（前 10 个）"
echo "--------------------------------------"
curl -s "${HOST}/api/tv168/markets?exchange=okx&quote=USDT" | \
  python3 -c "import sys, json; data = json.load(sys.stdin); print(json.dumps(data['markets'][:10], indent=2))"

echo ""
echo ""
echo "Step 4: 发送 ZONE (OVERSOLD) 信号"
echo "--------------------------------------"
ZONE_PAYLOAD=$(cat <<EOF
{
  "secret": "${SECRET}",
  "type": "ZONE",
  "zone": "OVERSOLD",
  "exchange": "okx",
  "instId": "ETH/USDT",
  "tf": "1m",
  "t": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "close": "3200.50"
}
EOF
)

echo "$ZONE_PAYLOAD" | python3 -m json.tool
echo ""
curl -s -X POST "${HOST}/webhook/tradingview" \
  -H "Content-Type: application/json" \
  -d "$ZONE_PAYLOAD" | python3 -m json.tool

echo ""
echo ""
echo "Step 5: 等待 2 秒后发送 DIV 信号（触发买入）"
echo "--------------------------------------"
sleep 2

DIV_PAYLOAD=$(cat <<EOF
{
  "secret": "${SECRET}",
  "type": "DIV",
  "exchange": "okx",
  "instId": "ETH/USDT",
  "tf": "1m",
  "t": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "close": "3201.00"
}
EOF
)

echo "$DIV_PAYLOAD" | python3 -m json.tool
echo ""
curl -s -X POST "${HOST}/webhook/tradingview" \
  -H "Content-Type: application/json" \
  -d "$DIV_PAYLOAD" | python3 -m json.tool

echo ""
echo ""
echo "========================================="
echo "✅ 测试完成"
echo "========================================="
echo ""
echo "验证要点（$MODE 模式）："
case "$MODE" in
  paper)
    echo "  ✅ 响应里 'paper': true"
    echo "  ✅ 'order': null（没有下单）"
    echo "  ✅ 'sl' 和 'tp' 有计算值"
    ;;
  testnet)
    echo "  ✅ 响应里 'paper': false"
    echo "  ✅ 'order': { id: '...', price: ... }（有订单）"
    echo "  ✅ 'stop_loss_order': { id: '...', price: ... }（如果启用）"
    echo "  ✅ 'execution': { ok: true, status: 'filled', ... }"
    echo ""
    echo "登录 OKX Demo Trading 验证："
    echo "  - 持仓页面：应该有 ETH/USDT 多仓（如果 hedge mode）"
    echo "  - 委托页面：应该有止损单（如果 place_stop_loss=true）"
    ;;
esac
echo ""
