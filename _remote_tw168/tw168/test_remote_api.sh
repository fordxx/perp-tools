#!/bin/bash
# 完整验证脚本 - 测试远程交易 API

set -euo pipefail

# ========== 配置区 ==========
REMOTE_IP="3.38.98.169"
USE_HTTPS=false  # 改为 true 如果用方案 B
DOMAIN="3-38-98-169.nip.io"  # 方案 B 使用
BASIC_AUTH_USER="trader"  # 方案 B 使用
BASIC_AUTH_PASS=""  # 方案 B 使用
ADMIN_KEY=""  # 替换为你的 .env 中的 ADMIN_KEY

# ========== 自动检测 ==========
if [ "$USE_HTTPS" = true ]; then
    BASE_URL="https://${DOMAIN}"
    AUTH_HEADER="-u ${BASIC_AUTH_USER}:${BASIC_AUTH_PASS}"
else
    BASE_URL="http://${REMOTE_IP}:8000"
    AUTH_HEADER=""
fi

echo "=========================================="
echo "远程交易 API 验证测试"
echo "=========================================="
echo "目标: $BASE_URL"
echo ""

# ========== 测试 1: Health Check ==========
echo "[1/4] 测试健康检查端点..."
if curl -sf --connect-timeout 5 --max-time 10 ${AUTH_HEADER} "${BASE_URL}/health" > /tmp/health.json; then
    echo "✅ Health check 成功"
    cat /tmp/health.json
    echo ""
else
    echo "❌ Health check 失败"
    echo "排查步骤:"
    echo "  1. 检查防火墙: ssh ubuntu@${REMOTE_IP} 'sudo ufw status'"
    echo "  2. 检查容器: ssh ubuntu@${REMOTE_IP} 'docker ps | grep tv-okx'"
    echo "  3. 检查日志: ssh ubuntu@${REMOTE_IP} 'docker logs tw168-tv-okx-1 --tail 50'"
    exit 1
fi

# ========== 测试 2: Metrics 端点 ==========
echo "[2/4] 测试 metrics 端点..."
if curl -sf --connect-timeout 5 ${AUTH_HEADER} "${BASE_URL}/metrics" > /tmp/metrics.json; then
    echo "✅ Metrics 端点成功"
    echo "Active positions: $(jq -r '.active_positions // 0' /tmp/metrics.json)"
    echo "Pending orders: $(jq -r '.pending_orders // 0' /tmp/metrics.json)"
    echo ""
else
    echo "⚠️  Metrics 端点失败（非关键）"
    echo ""
fi

# ========== 测试 3: 验证错误处理 ==========
echo "[3/4] 测试错误处理（缺少参数）..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
    ${AUTH_HEADER} \
    -X POST "${BASE_URL}/manual/signal" \
    -H "Content-Type: application/json" \
    -d '{}')

if [ "$RESPONSE" = "422" ] || [ "$RESPONSE" = "400" ]; then
    echo "✅ 错误处理正常（返回 $RESPONSE）"
else
    echo "⚠️  预期 400/422，实际 $RESPONSE"
fi
echo ""

# ========== 测试 4: 真实信号（需要 ADMIN_KEY）==========
echo "[4/4] 测试真实信号..."
if [ -z "$ADMIN_KEY" ]; then
    echo "⚠️  未配置 ADMIN_KEY，跳过真实信号测试"
    echo "   请在脚本中设置 ADMIN_KEY 变量"
else
    if curl -sf --connect-timeout 10 ${AUTH_HEADER} \
        -X POST "${BASE_URL}/manual/signal" \
        -H "Content-Type: application/json" \
        -d "{
            \"instId\": \"BTC-USDT-SWAP\",
            \"tf\": \"15m\",
            \"side\": \"buy\",
            \"admin_key\": \"${ADMIN_KEY}\"
        }" > /tmp/signal.json; then
        echo "✅ 信号发送成功"
        cat /tmp/signal.json | jq '.'
    else
        echo "❌ 信号发送失败"
        echo "检查 ADMIN_KEY 是否正确"
    fi
fi

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
