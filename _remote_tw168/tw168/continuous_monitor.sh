#!/bin/bash
# Continuous monitoring for Lighter WebSocket test

SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"
REMOTE_HOST="ubuntu@3.38.98.169"
INTERVAL=300  # 5分钟检查一次

echo "========================================"
echo "Lighter WebSocket 持续监控"
echo "========================================"
echo "监控间隔: ${INTERVAL}秒 ($(($INTERVAL / 60))分钟)"
echo "按 Ctrl+C 停止监控"
echo ""

# Counter for iterations
iteration=0

while true; do
    iteration=$((iteration + 1))
    clear

    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  Lighter WebSocket 监控 - 第 $iteration 次检查                    "
    echo "║  时间: $(date '+%Y-%m-%d %H:%M:%S')                            "
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    # Get system status
    ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'MONITOR_EOF'
cd /home/ubuntu/tw168

# Container status
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 容器状态"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
container_status=$(docker compose ps --format "{{.Status}}")
if echo "$container_status" | grep -q "Up"; then
    echo "✅ 状态: 运行中"
else
    echo "❌ 状态: 异常 - $container_status"
fi

# Resource usage
echo ""
docker stats --no-stream tw168-tv-okx-1 --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | tail -1 | \
    awk '{printf "   CPU: %s | 内存: %s (%s)\n", $2, $3, $4}'

# Uptime
uptime_sec=$(docker compose logs | grep "health_check" | tail -1 | grep -o "uptime_s=[0-9]*" | cut -d= -f2)
if [ ! -z "$uptime_sec" ]; then
    uptime_min=$((uptime_sec / 60))
    uptime_hour=$((uptime_min / 60))
    uptime_min_remainder=$((uptime_min % 60))
    echo "   运行时长: ${uptime_hour}小时 ${uptime_min_remainder}分钟"
fi

# WebSocket status
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔌 WebSocket 状态"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if WebSocket is enabled
ws_enabled=$(docker compose logs | grep "Lighter WebSocket enabled" | tail -1)
if [ ! -z "$ws_enabled" ]; then
    echo "✅ WebSocket: 已启用 (6/6 symbols)"
else
    echo "❌ WebSocket: 未检测到启用记录"
fi

# Check for recent WebSocket errors
ws_errors=$(docker compose logs --since 5m | grep -i "websocket.*error\|websocket.*failed" | wc -l)
ws_closed=$(docker compose logs --since 5m | grep "connection closed" | wc -l)

if [ $ws_errors -gt 0 ]; then
    echo "⚠️  最近5分钟 WebSocket 错误: $ws_errors 次"
fi

if [ $ws_closed -gt 0 ]; then
    echo "⚠️  最近5分钟连接关闭: $ws_closed 次"
fi

if [ $ws_errors -eq 0 ] && [ $ws_closed -eq 0 ]; then
    echo "✅ 最近5分钟: 无错误，连接稳定"
fi

# Check reconnection attempts
reconnect_count=$(docker compose logs | grep -i "reconnecting to lighter" | wc -l)
echo "   总重连次数: $reconnect_count"

# Trading activity
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 交易活动"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Webhook count
webhook_count=$(docker compose logs | grep "health_check" | tail -1 | grep -o "webhook_count=[0-9]*" | cut -d= -f2)
echo "   Webhook 接收: ${webhook_count:-0} 个信号"

# Recent trades
trade_count=$(docker compose logs --since 1h | grep -i "开仓\|平仓\|order.*filled" | wc -l)
echo "   最近1小时交易: $trade_count 笔"

if [ $trade_count -gt 0 ]; then
    echo ""
    echo "   最近交易:"
    docker compose logs --since 1h | grep -i "开仓\|平仓\|order.*filled" | tail -3 | \
        sed 's/^/     /'
fi

# System health
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚙️  系统健康"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Recent errors
error_count=$(docker compose logs --since 5m | grep -i "error\|exception" | grep -v "websocket.*connection closed" | wc -l)
if [ $error_count -gt 0 ]; then
    echo "⚠️  最近5分钟错误: $error_count 次"
    echo "   最新错误:"
    docker compose logs --since 5m | grep -i "error\|exception" | grep -v "websocket.*connection closed" | tail -2 | \
        sed 's/^/     /'
else
    echo "✅ 最近5分钟: 无错误"
fi

# OKX WebSocket status
okx_ws_subs=$(docker compose logs | grep "Candle WebSocket subscribed" | tail -1 | grep -o "[0-9]* channels")
echo ""
echo "   OKX K线 WebSocket: $okx_ws_subs"

MONITOR_EOF

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "下次检查: $(date -d "+${INTERVAL} seconds" '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Wait for next iteration
    sleep $INTERVAL
done
