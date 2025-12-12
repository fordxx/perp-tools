#!/bin/bash
# 交易所实盘功能测试运行器
# Live Exchange Function Test Runner

echo "================================================================================"
echo "  交易所实盘功能测试"
echo "  Live Exchange Function Testing"
echo "================================================================================"
echo ""
echo "模式: ✅ 只读模式 (READ-ONLY - Safe)"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "================================================================================"
echo ""

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "❌ 错误: .env 文件不存在"
    echo "请从 .env.example 复制并配置你的 API 凭证："
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

echo "✅ .env 文件已找到"
echo ""

# 加载 .env 文件
export $(cat .env | grep -v '^#' | xargs)

# 检测已配置的交易所
CONFIGURED_EXCHANGES=()

if [ ! -z "$OKX_API_KEY" ] && [ "$OKX_API_KEY" != "your_okx_api_key_here" ]; then
    CONFIGURED_EXCHANGES+=("OKX")
fi

if [ ! -z "$PARADEX_L2_PRIVATE_KEY" ] && [ "$PARADEX_L2_PRIVATE_KEY" != "0xyour_l2_private_key_here" ]; then
    CONFIGURED_EXCHANGES+=("Paradex")
fi

if [ ! -z "$HYPERLIQUID_PRIVATE_KEY" ]; then
    CONFIGURED_EXCHANGES+=("Hyperliquid")
fi

if [ ! -z "$EXTENDED_API_KEY" ] && [ "$EXTENDED_API_KEY" != "your_extended_api_key_here" ]; then
    CONFIGURED_EXCHANGES+=("Extended")
fi

if [ ! -z "$EDGEX_API_KEY" ] && [ "$EDGEX_API_KEY" != "your_edgex_api_key_here" ]; then
    CONFIGURED_EXCHANGES+=("EdgeX")
fi

if [ ! -z "$LIGHTER_API_KEY" ] && [ "$LIGHTER_API_KEY" != "your_lighter_api_key_here" ]; then
    CONFIGURED_EXCHANGES+=("Lighter")
fi

# 显示已配置的交易所
if [ ${#CONFIGURED_EXCHANGES[@]} -eq 0 ]; then
    echo "❌ 没有检测到已配置的交易所"
    echo ""
    echo "请在 .env 文件中配置至少一个交易所的 API 凭证"
    echo ""
    echo "支持的交易所："
    echo "  - OKX (Demo Trading)"
    echo "  - Paradex (Starknet DEX)"
    echo "  - Hyperliquid"
    echo "  - Extended (Starknet DEX)"
    echo "  - EdgeX"
    echo "  - Lighter"
    echo ""
    exit 1
fi

echo "已配置的交易所: ${CONFIGURED_EXCHANGES[*]}"
echo ""
echo "================================================================================"
echo ""

# 测试函数
test_exchange() {
    local exchange=$1
    local test_script=$2
    local venv_dir=$3

    echo ""
    echo "--------------------------------------------------------------------------------"
    echo "  测试 $exchange"
    echo "--------------------------------------------------------------------------------"
    echo ""

    if [ ! -f "$test_script" ]; then
        echo "⏭️  跳过 - 测试脚本不存在: $test_script"
        return
    fi

    # 激活虚拟环境（如果存在）
    if [ -d "$venv_dir" ]; then
        echo "📦 使用虚拟环境: $venv_dir"
        source "$venv_dir/bin/activate" 2>/dev/null || {
            echo "⚠️  无法激活虚拟环境，使用系统 Python"
        }
    fi

    # 运行测试
    python3 "$test_script" 2>&1
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo ""
        echo "✅ $exchange 测试完成"
    else
        echo ""
        echo "❌ $exchange 测试失败 (exit code: $exit_code)"
    fi

    # 停用虚拟环境
    if [ -d "$venv_dir" ]; then
        deactivate 2>/dev/null || true
    fi

    echo ""
}

# 运行测试
for exchange in "${CONFIGURED_EXCHANGES[@]}"; do
    case $exchange in
        "OKX")
            test_exchange "OKX" "test_okx.py" "venv_okx"
            ;;
        "Paradex")
            test_exchange "Paradex" "test_paradex.py" "venv_paradex"
            ;;
        "Hyperliquid")
            test_exchange "Hyperliquid" "test_hyperliquid.py" ""
            ;;
        "Extended")
            test_exchange "Extended" "test_extended.py" "venv_extended"
            ;;
        "EdgeX")
            test_exchange "EdgeX" "test_edgex.py" "venv_edgex"
            ;;
        "Lighter")
            test_exchange "Lighter" "test_lighter.py" ""
            ;;
    esac
done

echo "================================================================================"
echo "  测试完成"
echo "================================================================================"
echo ""
echo "📊 测试了 ${#CONFIGURED_EXCHANGES[@]} 个交易所: ${CONFIGURED_EXCHANGES[*]}"
echo ""
echo "================================================================================"
