#!/bin/bash
# Dashboard完整启动脚本（HTTP + WebSocket）

cd "$(dirname "$0")"

echo "========================================"
echo "  PERP Trading Dashboard 完整启动"
echo "========================================"
echo ""

# 检查并清理旧进程
echo "🗑️  清理旧进程..."
kill -9 $(lsof -t -i:18888) 2>/dev/null
kill -9 $(lsof -t -i:18889) 2>/dev/null
sleep 1

# 启动HTTP服务器
echo "🚀 启动Dashboard HTTP服务器 (端口18888)..."
nohup ./.venv/bin/python src/perpbot/monitoring/dashboard_api.py > /tmp/dashboard_api.log 2>&1 &
HTTP_PID=$!
sleep 2

# 启动WebSocket服务器
echo "🔌 启动Dashboard WebSocket服务器 (端口18889)..."
nohup ./.venv/bin/python src/perpbot/monitoring/dashboard_websocket.py > /tmp/dashboard_ws.log 2>&1 &
WS_PID=$!
sleep 2

# 测试连接
echo "📊 测试服务连接..."
if curl -s http://localhost:18888/api/system/status > /dev/null 2>&1; then
    echo "✅ Dashboard服务已成功启动！"
    echo ""
    echo "📍 HTTP服务: http://localhost:18888"
    echo "🔌 WebSocket服务: ws://localhost:18889"
    echo "📋 HTTP PID: $HTTP_PID"
    echo "📋 WebSocket PID: $WS_PID"
    echo "📄 HTTP日志: /tmp/dashboard_api.log"
    echo "📄 WebSocket日志: /tmp/dashboard_ws.log"
    echo ""
    echo "停止服务: kill $HTTP_PID $WS_PID"
    echo "查看HTTP日志: tail -f /tmp/dashboard_api.log"
    echo "查看WS日志: tail -f /tmp/dashboard_ws.log"
else
    echo "❌ 启动失败，请查看日志"
    exit 1
fi
