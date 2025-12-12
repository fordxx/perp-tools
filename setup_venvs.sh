#!/bin/bash
# 设置所有交易所虚拟环境和依赖

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================="
echo "  多交易所虚拟环境设置脚本"
echo "=================================="
echo ""

# 交易所配置
declare -A exchanges=(
    [okx]="okx python-dotenv"
    [binance]="ccxt python-dotenv"
    [bitget]="ccxt python-dotenv"
    [hyperliquid]="hyperliquid-python-sdk python-dotenv"
    [paradex]="paradex-py python-dotenv starknet.py"
    [extended]="python-dotenv"
)

# 创建或更新虚拟环境
create_venv() {
    local name=$1
    local packages=$2

    echo "📦 设置 venv_$name..."

    if [ ! -d "venv_$name" ]; then
        echo "   创建虚拟环境..."
        python3 -m venv "venv_$name"
    fi

    echo "   激活虚拟环境并安装包..."
    source "venv_$name/bin/activate"

    # 升级 pip
    pip install --upgrade pip setuptools wheel -q

    # 安装所需包
    for package in $packages; do
        echo "   - 安装 $package..."
        pip install "$package" -q
    done

    deactivate
    echo "   ✅ venv_$name 准备完成"
    echo ""
}

# 主流程
echo "开始设置虚拟环境..."
echo ""

for exchange in "${!exchanges[@]}"; do
    create_venv "$exchange" "${exchanges[$exchange]}"
done

echo "=================================="
echo "  ✅ 所有虚拟环境设置完成"
echo "=================================="
echo ""
echo "可用的虚拟环境："
ls -d venv_* | sed 's/^/  ✅ /'
echo ""
echo "下一步："
echo "  1. 编辑 .env 文件添加交易所凭证"
echo "  2. 运行: python test_multi_exchange.py --exchanges okx hyperliquid"
echo ""
