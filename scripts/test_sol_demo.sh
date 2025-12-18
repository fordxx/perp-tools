#!/usr/bin/env bash
#
# SOL/USDT Demo Trading 测试脚本
# 用法：bash scripts/test_sol_demo.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

echo "========================================="
echo "SOL/USDT OKX Demo Trading 测试"
echo "========================================="
echo ""

# 检查 .env 配置
echo "Step 1: 检查配置"
echo "--------------------------------------"

if ! grep -q "OKX_API_KEY" .env 2>/dev/null || ! grep -q "PERPBOT_TV_TRADING_ENABLED=true" .env 2>/dev/null; then
  echo "⚠️ 请先配置 .env 文件："
  echo ""
  echo "# OKX Demo Trading 凭据"
  echo "OKX_API_KEY=your_demo_key"
  echo "OKX_API_SECRET=your_demo_secret"
  echo "OKX_PASSPHRASE=your_demo_passphrase"
  echo "OKX_ENV=testnet"
  echo ""
  echo "# 启用实盘下单"
  echo "PERPBOT_TV_TRADING_ENABLED=true"
  echo "PERPBOT_TV_ALLOW_ALL_SYMBOLS=true"
  echo "PERPBOT_TV_ORDER_SIZE=0.1"
  echo "PERPBOT_TV_HEDGE_MODE=true"
  echo "PERPBOT_TV_PLACE_STOP_LOSS=true"
  echo ""
  echo "配置完成后重新运行此脚本"
  exit 1
fi

echo "✅ 配置检查通过"
echo ""

# 检查服务状态
echo "Step 2: 检查服务状态"
echo "--------------------------------------"

if ! curl -s http://127.0.0.1:8001/health/tradingview > /dev/null 2>&1; then
  echo "⚠️ 服务未运行，正在启动..."
  bash scripts/run_tv168.sh > /tmp/tv168_sol_startup.log 2>&1 &
  sleep 5
fi

HEALTH=$(curl -s http://127.0.0.1:8001/health/tradingview)
echo "$HEALTH" | python3 -m json.tool
echo "✅ 服务正常"
echo ""

# 获取当前 SOL 价格（用于测试）
echo "Step 3: 获取 SOL/USDT 市场信息"
echo "--------------------------------------"
SOL_PRICE=$(curl -s "https://www.okx.com/api/v5/market/ticker?instId=SOL-USDT-SWAP" | \
  python3 -c "import sys, json; d=json.load(sys.stdin); print(d['data'][0]['last'])" 2>/dev/null || echo "195.00")

echo "当前 SOL 价格: $SOL_PRICE USDT"
echo ""

# 发送 ZONE 信号
echo "Step 4: 发送 SOL/USDT ZONE (OVERSOLD)"
echo "--------------------------------------"

ZONE_RESP=$(curl -s -X POST http://127.0.0.1:8001/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d "{\"secret\":\"CHANGE_ME\",\"type\":\"ZONE\",\"zone\":\"OVERSOLD\",\"exchange\":\"okx\",\"instId\":\"SOL/USDT\",\"tf\":\"5m\",\"t\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"close\":\"${SOL_PRICE}\"}")

echo "$ZONE_RESP" | python3 -m json.tool
echo ""

if echo "$ZONE_RESP" | grep -q '"ok":true'; then
  echo "✅ ZONE 信号已接受"
else
  echo "❌ ZONE 信号失败"
  exit 1
fi

sleep 3

# 发送 DIV 信号触发下单
echo "Step 5: 发送 SOL/USDT DIV（触发买入）"
echo "--------------------------------------"
echo "⚠️ 警告：这将在 OKX Demo Trading 下真实订单！"
echo "按 Enter 继续，或 Ctrl-C 取消..."
read -r

DIV_CLOSE=$(python3 -c "print(float('${SOL_PRICE}') + 0.1)")

DIV_RESP=$(curl -s -X POST http://127.0.0.1:8001/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d "{\"secret\":\"CHANGE_ME\",\"type\":\"DIV\",\"exchange\":\"okx\",\"instId\":\"SOL/USDT\",\"tf\":\"5m\",\"t\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"close\":\"${DIV_CLOSE}\"}")

echo "$DIV_RESP" | python3 -m json.tool | tee /tmp/sol_demo_result.json

echo ""
echo "========================================="
echo "验证结果"
echo "========================================="

python3 <<'PYEOF'
import json

with open('/tmp/sol_demo_result.json') as f:
    d = json.load(f)

print(f"✓ 交易对: {d.get('symbol')}")
print(f"✓ 交易所: {d.get('exchange')}")
print(f"✓ 方向: {d.get('side')}")
print(f"✓ 入场价: {d.get('entry')}")
print(f"✓ 止损价: {d.get('sl')}")
print(f"✓ 止盈价: {d.get('tp')}")
print(f"✓ Paper 模式: {d.get('paper')}")
print("")

if d.get('paper') == False and d.get('order') and d.get('order', {}).get('id'):
    print("✅✅✅ 实盘订单已下单！")
    print(f"  - 订单 ID: {d.get('order', {}).get('id')}")
    print(f"  - 成交价: {d.get('order', {}).get('price')}")
    print(f"  - 数量: {d.get('order', {}).get('size')} SOL")

    if d.get('stop_loss_order') and d.get('stop_loss_order', {}).get('id'):
        print(f"  - 止损单 ID: {d.get('stop_loss_order', {}).get('id')}")
        print(f"  - 止损价: {d.get('stop_loss_order', {}).get('price')}")
    else:
        print("  ⚠️ 止损单未下单（可能失败或被禁用）")

    print("")
    print("🌐 请登录 OKX Demo Trading 验证：")
    print("  1. 持仓页面：应该有 SOL/USDT 多仓")
    print("  2. 委托页面：应该有止损条件单")

elif d.get('paper') == True:
    print("📝 Paper 模式（未下单）")
    print("  如需实盘下单，请设置：")
    print("  PERPBOT_TV_TRADING_ENABLED=true")
else:
    print("❌ 订单失败")
    if d.get('execution'):
        print(f"  错误类型: {d.get('execution', {}).get('error_class')}")
        print(f"  错误信息: {d.get('execution', {}).get('error_msg')}")
PYEOF

echo ""
echo "========================================="
echo "测试完成"
echo "========================================="
