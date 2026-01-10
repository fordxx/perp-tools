#!/bin/bash

# TW168 UI服务器停止脚本

set -euo pipefail

PID_FILE=".ui_server.pid"

echo "🛑 停止TW168 UI服务器..."

stopped=0

# 先按 pidfile 停
if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${PID:-}" ] && kill -0 "$PID" >/dev/null 2>&1; then
        kill "$PID" || true
        stopped=1
        echo "✅ 已发送停止信号 (pid=$PID)"
        sleep 0.5
        if kill -0 "$PID" >/dev/null 2>&1; then
            echo "⚠️  进程仍在运行，强制终止 (pid=$PID)"
            kill -9 "$PID" || true
        fi
    fi
    rm -f "$PID_FILE" || true
fi

# 杀死ui_server.py进程
if pgrep -f "ui_server.py" > /dev/null 2>&1; then
    pkill -f "ui_server.py"
    echo "✅ UI服务器已停止"
    sleep 1
    stopped=1
else
    echo "ℹ️  UI服务器没有运行"
fi

# 检查是否成功停止
if pgrep -f "ui_server.py" > /dev/null 2>&1; then
    echo "⚠️  强制杀死进程..."
    pkill -9 -f "ui_server.py"
    echo "✅ 进程已强制终止"
    stopped=1
fi

if [ "$stopped" -eq 1 ]; then
    echo "完成！"
else
    echo "完成！（未发现运行中的 UI 进程）"
fi
