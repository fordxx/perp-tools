#!/bin/bash
# Automatic monitoring with logging

SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"
REMOTE_HOST="ubuntu@3.38.98.169"
LOG_FILE="monitoring_data.log"
INTERVAL=600  # 10分钟检查一次

echo "========================================"
echo "Lighter WebSocket 自动监控"
echo "========================================"
echo "监控间隔: ${INTERVAL}秒 ($(($INTERVAL / 60))分钟)"
echo "日志文件: $LOG_FILE"
echo "按 Ctrl+C 停止"
echo ""

# Create log file header if doesn't exist
if [ ! -f "$LOG_FILE" ]; then
    echo "时间,运行时长(秒),CPU%,内存MB,WS状态,WS错误,连接关闭,Webhook数,交易数,系统错误" > "$LOG_FILE"
fi

while true; do
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Collect metrics from remote server
    metrics=$(ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'METRICS_EOF'
cd /home/ubuntu/tw168

# Get container stats
stats=$(docker stats --no-stream tw168-tv-okx-1 --format "{{.CPUPerc}},{{.MemUsage}}")
cpu=$(echo "$stats" | cut -d, -f1 | sed 's/%//')
mem=$(echo "$stats" | cut -d, -f2 | cut -d/ -f1 | sed 's/MiB//' | tr -d ' ')

# Get uptime
uptime_sec=$(docker compose logs | grep "health_check" | tail -1 | grep -o "uptime_s=[0-9]*" | cut -d= -f2)
uptime_sec=${uptime_sec:-0}

# WebSocket status
ws_enabled=$(docker compose logs | grep "Lighter WebSocket enabled" | tail -1 | grep -c "6/6")
ws_errors=$(docker compose logs --since 10m | grep -i "websocket.*error\|websocket.*failed" | wc -l)
ws_closed=$(docker compose logs --since 10m | grep "connection closed" | wc -l)

# Trading stats
webhook_count=$(docker compose logs | grep "health_check" | tail -1 | grep -o "webhook_count=[0-9]*" | cut -d= -f2)
webhook_count=${webhook_count:-0}
trade_count=$(docker compose logs --since 1h | grep -i "开仓\|平仓\|order.*filled" | wc -l)

# System errors
error_count=$(docker compose logs --since 10m | grep -iE "error|exception|failed" | grep -v "websocket.*connection closed\|SignerClient.*失败" | wc -l)

# Output in CSV format
echo "$uptime_sec,$cpu,$mem,$ws_enabled,$ws_errors,$ws_closed,$webhook_count,$trade_count,$error_count"
METRICS_EOF
)

    # Parse metrics
    IFS=',' read -r uptime cpu mem ws_status ws_errors ws_closed webhooks trades errors <<< "$metrics"

    # Log to file
    echo "$timestamp,$uptime,$cpu,$mem,$ws_status,$ws_errors,$ws_closed,$webhooks,$trades,$errors" >> "$LOG_FILE"

    # Display summary
    echo "[$timestamp] 运行:${uptime}s CPU:${cpu}% 内存:${mem}MB WS:${ws_status} 错误:${errors} Webhook:${webhooks} 交易:${trades}"

    # Check for issues
    if [ "$ws_status" = "0" ]; then
        echo "  ⚠️  WARNING: WebSocket 未启用！"
    fi

    if [ "$errors" -gt 0 ]; then
        echo "  ⚠️  WARNING: 检测到 $errors 个错误"
    fi

    if [ "$ws_closed" -gt 5 ]; then
        echo "  ⚠️  WARNING: WebSocket 频繁断开 ($ws_closed 次)"
    fi

    # Wait for next check
    sleep $INTERVAL
done
