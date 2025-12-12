#!/bin/bash

# 🎬 PerpBot 统一测试框架演示脚本
# 展示新增的交易功能

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  🎬 PerpBot 统一测试框架 - 功能演示 (v2.2)                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 未找到，请先安装 Python 3.8+"
    exit 1
fi

echo "📋 选择演示场景:"
echo ""
echo "1️⃣  列出所有支持的交易所"
echo "2️⃣  自动化测试单个交易所（查询功能）"
echo "3️⃣  交互式菜单演示（单个交易所）"
echo "4️⃣  自动化测试多个交易所"
echo "5️⃣  帮助和文档"
echo ""

read -p "请选择 (1-5): " choice

case $choice in
    1)
        echo ""
        echo "🌍 列出所有支持的交易所..."
        python test_exchanges.py --list
        ;;
    
    2)
        echo ""
        echo "🔄 选择交易所进行自动化测试"
        echo ""
        python test_exchanges.py --list | grep -E "^\s+[0-9]+" | head -5
        echo ""
        read -p "输入交易所名称 (例如: okx, extended, hyperliquid): " exchange
        
        if [ -z "$exchange" ]; then
            exchange="okx"
        fi
        
        echo ""
        echo "⏱️  开始自动化测试 $exchange（约 10 秒）..."
        echo ""
        
        timeout 20 python test_exchanges.py "$exchange" --auto-test --symbol BTC/USDT || true
        ;;
    
    3)
        echo ""
        echo "🔄 选择交易所进行交互式测试"
        echo ""
        python test_exchanges.py --list | grep -E "^\s+[0-9]+" | head -5
        echo ""
        read -p "输入交易所名称 (例如: okx, extended): " exchange
        
        if [ -z "$exchange" ]; then
            exchange="okx"
        fi
        
        echo ""
        echo "💡 即将进入交互式菜单..."
        echo "   功能包括:"
        echo "   • 1️⃣  查询价格"
        echo "   • 2️⃣  查询订单簿"
        echo "   • 3️⃣  查询余额"
        echo "   • 4️⃣  查询持仓"
        echo "   • 5️⃣  下限价单"
        echo "   • 6️⃣  下市价单"
        echo "   • 8️⃣  平仓"
        echo "   • 0️⃣  退出"
        echo ""
        
        read -p "按 Enter 继续..."
        
        python test_exchanges.py "$exchange" || true
        ;;
    
    4)
        echo ""
        echo "🌐 自动化测试多个交易所"
        echo ""
        echo "可用选项:"
        echo "  • --all    : 测试所有交易所"
        echo "  • --cex    : 仅测试 CEX (OKX, Binance, 等)"
        echo "  • --dex    : 仅测试 DEX (Hyperliquid, Paradex, 等)"
        echo ""
        
        read -p "选择 (all/cex/dex): " mode
        
        if [ "$mode" = "cex" ] || [ "$mode" = "dex" ]; then
            echo ""
            echo "⏱️  开始批量测试（约 20-30 秒）..."
            echo ""
            python test_exchanges.py "--$mode" --auto-test --json-report test_report.json || true
            
            if [ -f "test_report.json" ]; then
                echo ""
                echo "📊 测试报告已保存: test_report.json"
                echo ""
                echo "报告摘要:"
                grep -E '"total_exchanges"|"passed_exchanges"|"failed_exchanges"' test_report.json || true
            fi
        else
            echo "❌ 无效选择"
        fi
        ;;
    
    5)
        echo ""
        echo "📚 可用文档:"
        echo ""
        echo "快速开始:"
        echo "  • QUICK_TEST_GUIDE.md - 5 分钟快速开始"
        echo "  • ENHANCED_TEST_GUIDE.md - 新增功能说明（本文件）"
        echo ""
        echo "详细指南:"
        echo "  • EXCHANGE_TEST_GUIDE.md - 完整使用指南"
        echo "  • EXCHANGE_TEST_DEMO.md - 详细演示示例"
        echo "  • CREDENTIALS_SETUP_GUIDE.md - 凭证配置指南"
        echo ""
        echo "速查表:"
        echo "  • COMMAND_CHEATSHEET.md - 常用命令速查"
        echo ""
        echo "查看文档:"
        echo "  cat QUICK_TEST_GUIDE.md"
        echo "  cat ENHANCED_TEST_GUIDE.md"
        echo ""
        ;;
    
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

echo ""
echo "✅ 演示完成"
echo ""
