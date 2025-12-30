#!/bin/bash
set -e

echo "========================================================================"
echo "TradingView Webhook SOL/USDT 完整测试（开仓 + 止损）"
echo "========================================================================"
echo ""

# 配置
TV_SECRET="${PERPBOT_TV_WEBHOOK_SECRET:-CHANGE_ME}"
EXCHANGE="okx"
SYMBOL="SOL/USDT"
TF="5m"
PORT="${TV_PORT:-8001}"
BASE_URL="http://127.0.0.1:${PORT}"

echo "📊 配置："
echo "  Webhook: ${BASE_URL}/webhook/tradingview"
echo "  Secret: ${TV_SECRET}"
echo "  Exchange: ${EXCHANGE}"
echo "  Symbol: ${SYMBOL}"
echo "  Timeframe: ${TF}"
echo ""

# Step 1: 健康检查
echo "Step 1: 健康检查"
echo "------------------------------------------------------------------------"
HEALTH=$(curl -s "${BASE_URL}/health/tradingview")
echo "${HEALTH}" | python3 -m json.tool
echo ""

# 检查是否启用交易
TRADING_ENABLED=$(echo "${HEALTH}" | python3 -c "import sys, json; print(json.load(sys.stdin).get('trading_enabled', False))")
if [ "${TRADING_ENABLED}" = "True" ]; then
    echo "⚠️  WARNING: Trading is ENABLED - this will place REAL orders!"
    echo ""
else
    echo "📝 Paper mode - no real orders will be placed"
    echo ""
fi

# Step 2: 获取当前 SOL 价格
echo "Step 2: 获取 SOL/USDT 当前价格"
echo "------------------------------------------------------------------------"
SOL_PRICE=$(curl -s "https://www.okx.com/api/v5/market/ticker?instId=SOL-USDT-SWAP" | \
    python3 -c "import sys, json; d=json.load(sys.stdin); print(d['data'][0]['last'])" 2>/dev/null || echo "124.00")
echo "  当前 SOL 价格: ${SOL_PRICE} USDT"
echo ""

# Step 3: 发送 ZONE 信号
echo "Step 3: 发送 ZONE 信号（OVERSOLD）"
echo "------------------------------------------------------------------------"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ZONE_PAYLOAD=$(cat <<EOF
{
  "secret": "${TV_SECRET}",
  "type": "ZONE",
  "zone": "OVERSOLD",
  "exchange": "${EXCHANGE}",
  "instId": "${SYMBOL}",
  "tf": "${TF}",
  "t": "${TIMESTAMP}",
  "close": "${SOL_PRICE}"
}
EOF
)

echo "发送 ZONE 信号..."
ZONE_RESP=$(curl -s -X POST "${BASE_URL}/webhook/tradingview" \
    -H "Content-Type: application/json" \
    -d "${ZONE_PAYLOAD}")

echo "${ZONE_RESP}" | python3 -m json.tool
echo ""

# 检查 ZONE 响应
ZONE_OK=$(echo "${ZONE_RESP}" | python3 -c "import sys, json; print(json.load(sys.stdin).get('ok', False))")
if [ "${ZONE_OK}" != "True" ]; then
    echo "❌ ZONE 信号失败，终止测试"
    exit 1
fi
echo "✅ ZONE 信号成功"
echo ""

# 等待 2 秒
echo "等待 2 秒..."
sleep 2
echo ""

# Step 4: 发送 DIV 信号（触发开仓 + 止损）
echo "Step 4: 发送 DIV 信号（触发开仓 + 止损）"
echo "------------------------------------------------------------------------"
DIV_CLOSE=$(python3 -c "print(float('${SOL_PRICE}') + 0.05)")  # 稍微高一点确保触发
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
DIV_PAYLOAD=$(cat <<EOF
{
  "secret": "${TV_SECRET}",
  "type": "DIV",
  "exchange": "${EXCHANGE}",
  "instId": "${SYMBOL}",
  "tf": "${TF}",
  "t": "${TIMESTAMP}",
  "close": "${DIV_CLOSE}"
}
EOF
)

echo "发送 DIV 信号（close=${DIV_CLOSE}）..."
DIV_RESP=$(curl -s -X POST "${BASE_URL}/webhook/tradingview" \
    -H "Content-Type: application/json" \
    -d "${DIV_PAYLOAD}")

echo "${DIV_RESP}" | python3 -m json.tool | tee /tmp/tv_div_response.json
echo ""

# Step 5: 解析结果
echo "========================================================================"
echo "测试结果分析"
echo "========================================================================"

python3 <<'EOFA'
import json

with open('/tmp/tv_div_response.json') as f:
    resp = json.load(f)

print(f"✓ 交易对: {resp.get('symbol', 'N/A')}")
print(f"✓ 交易所: {resp.get('exchange', 'N/A')}")
print(f"✓ 方向: {resp.get('side', 'N/A')}")
print(f"✓ 入场价: {resp.get('entry', 'N/A')}")
print(f"✓ 止损价: {resp.get('sl', 'N/A')}")
print(f"✓ 止盈价: {resp.get('tp', 'N/A')}")
print(f"✓ Paper 模式: {resp.get('paper', 'N/A')}")
print("")

execution = resp.get('execution')
if execution:
    print(f"📋 执行详情:")
    print(f"  状态: {execution.get('status', 'N/A')}")
    print(f"  成功: {execution.get('ok', 'N/A')}")
    print(f"  耗时: {execution.get('elapsed_ms', 'N/A')} ms")
    if execution.get('error_class'):
        print(f"  错误类型: {execution.get('error_class')}")
        print(f"  错误信息: {execution.get('error_msg')}")
    print("")

if resp.get('paper') == False:
    # 实盘订单
    order = resp.get('order')
    sl_order = resp.get('stop_loss_order')

    if order and not order.get('id', '').startswith('error'):
        print("✅✅✅ 实盘订单成功！")
        print(f"  开仓单 ID: {order.get('id')}")
        print(f"  成交价: {order.get('price')}")
        print(f"  数量: {order.get('size')} SOL")
        print("")

        if sl_order and not sl_order.get('id', '').startswith('error'):
            print(f"  止损单 ID: {sl_order.get('id')}")
            print(f"  止损价: {sl_order.get('price')}")
            print("")
            print("✅ 开仓 + 止损单全部成功！")
        else:
            print("  ⚠️ 止损单未成功")
            print("     请手动在 OKX 设置止损！")

        print("")
        print("🌐 验证订单：")
        print("  https://www.okx.com/trade-swap/sol-usdt-swap")
        print("  1. 持仓页面：应该有 SOL-USDT-SWAP 多仓")
        print("  2. 委托页面：应该有止损条件单")
    else:
        print("❌ 开仓订单失败")
        if order:
            print(f"   订单 ID: {order.get('id')}")
elif resp.get('paper') == True:
    print("📝 Paper 模式（未下单）")
    print("  如需实盘下单，请设置：")
    print("  PERPBOT_TV_TRADING_ENABLED=true")
else:
    print("❌ 测试失败")
    print(f"   响应: {resp}")
EOFA

echo ""
echo "========================================================================"
echo "测试完成"
echo "========================================================================"
