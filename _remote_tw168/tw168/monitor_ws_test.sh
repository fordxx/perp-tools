#!/bin/bash
# Monitor Lighter WebSocket test status

SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"
REMOTE_HOST="ubuntu@3.38.98.169"

echo "========================================"
echo "Lighter WebSocket 测试监控"
echo "========================================"
echo ""

# Get current time
echo "检查时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Check container status
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 容器状态"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'EOF'
cd /home/ubuntu/tw168
docker compose ps
echo ""
echo "资源使用:"
docker stats --no-stream tw168-tv-okx-1 | tail -1
EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔌 WebSocket 状态"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'EOF'
cd /home/ubuntu/tw168

# Check WebSocket initialization
echo "WebSocket 初始化:"
docker compose logs | grep "Lighter WebSocket enabled" | tail -1

# Check for WebSocket errors
echo ""
echo "WebSocket 错误 (最近 10 条):"
docker compose logs | grep -i "websocket.*error\|websocket.*failed\|connection closed" | tail -10 | \
    while read line; do echo "  ⚠️  $line"; done || echo "  ✅ 无错误"

# Check reconnection count
echo ""
echo "WebSocket 重连次数:"
reconnect_count=$(docker compose logs | grep -i "reconnecting to lighter websocket" | wc -l)
echo "  总计: $reconnect_count 次"
EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 交易统计"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'EOF'
cd /home/ubuntu/tw168

# Check webhook count
echo "Webhook 接收:"
docker compose logs | grep "health_check" | tail -1 | grep -o "webhook_count=[0-9]*" || echo "  暂无数据"

# Check for any trades
echo ""
echo "交易记录 (最近 5 笔):"
docker compose logs | grep -i "开仓\|平仓\|订单.*成功\|order.*filled" | tail -5 | \
    while read line; do echo "  📈 $line"; done || echo "  暂无交易"
EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚙️  系统健康"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'EOF'
cd /home/ubuntu/tw168

# Check uptime
echo "系统运行时间:"
docker compose logs | grep "health_check" | tail -1 | grep -o "uptime_s=[0-9]*" | \
    awk -F= '{printf "  %d 分钟 (%d 秒)\n", $2/60, $2}'

# Check for errors
echo ""
echo "系统错误 (最近 10 条):"
docker compose logs | grep -i "error\|exception\|failed" | grep -v "websocket.*connection closed" | tail -10 | \
    while read line; do echo "  ❌ $line"; done || echo "  ✅ 无严重错误"

# Check warnings
echo ""
echo "系统警告 (最近 5 条):"
docker compose logs | grep "WARNING\|⚠️" | tail -5 | \
    while read line; do echo "  ⚠️  $line"; done || echo "  ✅ 无警告"
EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 测试配置"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'EOF'
cd /home/ubuntu/tw168

echo "风险配置:"
grep "RISK_PER_TRADE" .env | grep -v "^#" | sed 's/^/  /'

echo ""
echo "WebSocket 币种: ETH, BTC, SOL, LINK, DOGE, BNB (6个)"
echo "K线数据: OKX WebSocket (14个币种)"
echo "交易执行: Lighter DEX"
EOF

echo ""
echo "========================================"
echo "监控完成"
echo "========================================"
echo ""
echo "实时日志: ssh -i $SSH_KEY $REMOTE_HOST 'cd /home/ubuntu/tw168 && docker compose logs -f'"
echo "WebSocket 日志: ssh -i $SSH_KEY $REMOTE_HOST 'cd /home/ubuntu/tw168 && docker compose logs -f | grep -i websocket'"
echo ""
