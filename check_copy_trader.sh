#!/bin/bash
# Quick Check: Ultra-Fast Copy Trader Status
# 快速检查超高速跟单交易系统状态

echo "🔍 Checking Ultra-Fast Copy Trader Status"
echo "=========================================="

# 检查进程
echo "📊 Process Status:"
ps aux | grep -E "(copy_trader|run_copy_trader)" | grep -v grep || echo "❌ No copy trader process found"

# 检查supervisor状态
echo ""
echo "👔 Supervisor Status:"
sudo supervisorctl status 2>/dev/null | grep -E "(perpbot|copy)" || echo "❌ Supervisor not running or no services found"

# 检查日志文件
echo ""
echo "📝 Recent Logs:"
if [ -f logs/copy_trader.log ]; then
    echo "Last 5 lines of copy_trader.log:"
    tail -5 logs/copy_trader.log
else
    echo "❌ copy_trader.log not found"
fi

# 检查配置文件
echo ""
echo "⚙️  Configuration:"
if [ -f .env ]; then
    echo "✅ .env file exists"
    grep -E "(POLL_INTERVAL|TARGET_ADDRESS|HYPERLIQUID)" .env | head -5
else
    echo "❌ .env file not found"
fi

echo ""
echo "🎯 Performance Targets:"
echo "   • Polling Interval: 0.5s"
echo "   • Cache Duration: 1s"
echo "   • Target Response: <1s"
echo "   • Background: 24/7"