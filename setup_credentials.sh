#!/bin/bash

# 🔐 PerpBot 凭证快速配置脚本

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     🔐 PerpBot 凭证配置向导                                    ║"
echo "║                                                                ║"
echo "║  此脚本将帮助你配置交易所 API 凭证                              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# 检查是否已有 .env 文件
if [ -f .env ]; then
    echo "⚠️  检测到已存在 .env 文件"
    read -p "是否覆盖现有配置？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 1
    fi
    rm .env
fi

# 复制示例文件
echo "📋 复制配置示例..."
cp .env.example .env
echo "✅ .env 文件已创建"
echo ""

# 交互式配置
echo "═══════════════════════════════════════════════════════════════"
echo "现在让我们配置你的 API 凭证"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# OKX 配置
echo "1️⃣  OKX (CEX - Demo Trading)"
echo "   获取方式: https://www.okx.com/account/my-api"
read -p "   API Key (留空跳过): " okx_key
if [ ! -z "$okx_key" ]; then
    read -p "   API Secret: " okx_secret
    read -p "   Passphrase: " okx_pass
    sed -i "s|OKX_API_KEY=.*|OKX_API_KEY=$okx_key|" .env
    sed -i "s|OKX_API_SECRET=.*|OKX_API_SECRET=$okx_secret|" .env
    sed -i "s|OKX_PASSPHRASE=.*|OKX_PASSPHRASE=$okx_pass|" .env
    echo "   ✅ OKX 配置完成"
fi
echo ""

# Binance 配置
echo "2️⃣  Binance (CEX)"
echo "   获取方式: https://www.binance.com/en/account/api-management"
read -p "   API Key (留空跳过): " binance_key
if [ ! -z "$binance_key" ]; then
    read -p "   API Secret: " binance_secret
    sed -i "s|BINANCE_API_KEY=.*|BINANCE_API_KEY=$binance_key|" .env
    sed -i "s|BINANCE_API_SECRET=.*|BINANCE_API_SECRET=$binance_secret|" .env
    echo "   ✅ Binance 配置完成"
fi
echo ""

# Bitget 配置
echo "3️⃣  Bitget (CEX)"
echo "   获取方式: https://www.bitget.com/en/user/account/apimanagement"
read -p "   API Key (留空跳过): " bitget_key
if [ ! -z "$bitget_key" ]; then
    read -p "   API Secret: " bitget_secret
    read -p "   Passphrase: " bitget_pass
    # 在 .env 中添加或更新 Bitget
    if grep -q "BITGET_API_KEY=" .env; then
        sed -i "s|BITGET_API_KEY=.*|BITGET_API_KEY=$bitget_key|" .env
        sed -i "s|BITGET_API_SECRET=.*|BITGET_API_SECRET=$bitget_secret|" .env
        sed -i "s|BITGET_PASSPHRASE=.*|BITGET_PASSPHRASE=$bitget_pass|" .env
    else
        echo "BITGET_API_KEY=$bitget_key" >> .env
        echo "BITGET_API_SECRET=$bitget_secret" >> .env
        echo "BITGET_PASSPHRASE=$bitget_pass" >> .env
    fi
    echo "   ✅ Bitget 配置完成"
fi
echo ""

# Bybit 配置
echo "4️⃣  Bybit (CEX)"
echo "   获取方式: https://www.bybit.com/en/user/api-management"
read -p "   API Key (留空跳过): " bybit_key
if [ ! -z "$bybit_key" ]; then
    read -p "   API Secret: " bybit_secret
    if grep -q "BYBIT_API_KEY=" .env; then
        sed -i "s|BYBIT_API_KEY=.*|BYBIT_API_KEY=$bybit_key|" .env
        sed -i "s|BYBIT_API_SECRET=.*|BYBIT_API_SECRET=$bybit_secret|" .env
    else
        echo "BYBIT_API_KEY=$bybit_key" >> .env
        echo "BYBIT_API_SECRET=$bybit_secret" >> .env
    fi
    echo "   ✅ Bybit 配置完成"
fi
echo ""

# 总结
echo "═══════════════════════════════════════════════════════════════"
echo "✅ 配置完成！"
echo ""
echo "📋 配置信息已保存到 .env 文件"
echo ""
echo "📚 更多帮助:"
echo "   • 详细指南: cat CREDENTIALS_SETUP_GUIDE.md"
echo "   • 查看配置: python test_exchanges.py --list"
echo "   • 测试 OKX: python test_exchanges.py okx"
echo ""
echo "🚀 准备好了？运行: python test_exchanges.py"
echo "═══════════════════════════════════════════════════════════════"
