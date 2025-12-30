#!/bin/bash
# 持仓监控服务启动脚本

set -e

echo "========================================"
echo "持仓监控服务启动"
echo "========================================"
echo ""

# 检查环境变量
if [ ! -f ".env" ]; then
    echo "❌ .env 文件不存在"
    exit 1
fi

source .env

echo "📊 配置："
echo "  OKX_ENV: ${OKX_ENV:-testnet}"
echo "  检查间隔: ${POSITION_MONITOR_INTERVAL:-5.0} 秒"
echo ""

# 检查是否已在运行
if pgrep -f "perpbot.position_monitor" > /dev/null; then
    echo "⚠️  监控服务已在运行"
    echo "   进程: $(pgrep -f 'perpbot.position_monitor')"
    echo ""
    read -p "是否停止并重启？(y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "停止现有服务..."
        pkill -f "perpbot.position_monitor"
        sleep 2
    else
        echo "取消启动"
        exit 0
    fi
fi

# 启动监控服务
echo "🚀 启动持仓监控服务..."
PYTHONPATH=src .venv/bin/python -m perpbot.position_monitor > /tmp/position_monitor.log 2>&1 &
PID=$!

echo "  进程 PID: $PID"
echo "  日志文件: /tmp/position_monitor.log"
echo ""

# 等待启动
sleep 3

# 检查进程
if ps -p $PID > /dev/null; then
    echo "✅ 监控服务已启动"
    echo ""
    echo "查看日志："
    echo "  tail -f /tmp/position_monitor.log"
    echo ""
    echo "停止服务："
    echo "  pkill -f 'perpbot.position_monitor'"
    echo ""

    # 显示最近日志
    echo "最近日志："
    echo "----------------------------------------"
    tail -20 /tmp/position_monitor.log
else
    echo "❌ 启动失败，请检查日志："
    tail -50 /tmp/position_monitor.log
    exit 1
fi
