#!/bin/bash
# Quick start script for local UI server

cd "$(dirname "$0")"

# Check if UI is already running
if ss -tuln | grep -q ":9000"; then
    echo "✅ UI server is already running on http://localhost:9000"
    exit 0
fi

# Activate virtual environment and start UI
source .venv/bin/activate
nohup python ui_server.py > ui_server.log 2>&1 &

# Wait for server to start
sleep 3

# Check if started successfully
if ss -tuln | grep -q ":9000"; then
    echo "✅ UI server started successfully!"
    echo "📱 访问地址: http://localhost:9000"
    echo ""
    echo "管理员密钥 (从 .env 文件获取):"
    grep "^TV_WEBHOOK_SECRET" .env
    echo ""
    echo "查看日志: tail -f ui_server.log"
else
    echo "❌ Failed to start UI server"
    echo "Check ui_server.log for errors"
    exit 1
fi
