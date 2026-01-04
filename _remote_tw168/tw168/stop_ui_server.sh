#!/bin/bash

# TW168 UI服务器停止脚本

echo "🛑 停止TW168 UI服务器..."

# 杀死ui_server.py进程
if pgrep -f "ui_server.py" > /dev/null 2>&1; then
    pkill -f "ui_server.py"
    echo "✅ UI服务器已停止"
    sleep 1
else
    echo "ℹ️  UI服务器没有运行"
fi

# 检查是否成功停止
if pgrep -f "ui_server.py" > /dev/null 2>&1; then
    echo "⚠️  强制杀死进程..."
    pkill -9 -f "ui_server.py"
    echo "✅ 进程已强制终止"
fi

echo "完成！"
