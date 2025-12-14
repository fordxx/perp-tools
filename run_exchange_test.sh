#!/bin/bash
# 🚀 智能交易所测试启动器
#
# 自动检测并使用对应交易所的虚拟环境
# 如果虚拟环境不存在，自动创建并安装依赖
#
# 用法:
#   ./run_exchange_test.sh okx                    # 交互式菜单
#   ./run_exchange_test.sh okx --auto-test        # 自动化测试
#   ./run_exchange_test.sh --all --auto-test      # 测试所有交易所
#   ./run_exchange_test.sh --list                 # 列出所有交易所

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 从参数中提取交易所名称
extract_exchange_name() {
    for arg in "$@"; do
        case "$arg" in
            --all|--list|--auto-test|--trading|--verbose|--interactive|--select|--cex|--dex|--json-report|--help|-h)
                # 跳过选项参数
                continue
                ;;
            --*)
                # 跳过其他选项
                continue
                ;;
            *)
                # 这是交易所名称
                echo "$(sanitize_exchange_candidate "$arg")"
                return
                ;;
        esac
    done
    echo ""
}

sanitize_exchange_candidate() {
    local candidate="$1"
    # 去除末尾的标点/特殊字符
    while [[ "$candidate" =~ [^[:alnum:]_-]$ ]]; do
        candidate="${candidate:0:-1}"
    done
    echo "$candidate"
}

# 安装单个交易所依赖
install_exchange_deps() {
    local exchange=$1
    local venv_dir="venv_${exchange}"
    local req_file="requirements/${exchange}.txt"

    print_info "首次使用 ${exchange}，正在安装依赖..."

    if [ ! -f "$req_file" ]; then
        print_error "未找到 ${req_file}"
        return 1
    fi

    # 创建虚拟环境
    print_info "创建虚拟环境: ${venv_dir}"
    python3 -m venv "$venv_dir"

    # 激活并安装
    source "${venv_dir}/bin/activate"

    print_info "升级 pip..."
    pip install --upgrade pip --quiet

    print_info "安装公共依赖..."
    pip install python-dotenv httpx websockets --quiet

    print_info "安装 ${exchange} 特定依赖..."
    pip install -r "$req_file" --quiet

    print_success "${exchange} 依赖安装完成！"

    deactivate
}

# 主函数
main() {
    # 特殊命令处理
    if [[ " $* " =~ " --list " ]] || [[ " $* " =~ " --help " ]] || [[ " $* " =~ " -h " ]]; then
        # 直接运行，不需要虚拟环境
        python3 test_exchanges.py "$@"
        return
    fi

    # 提取交易所名称
    local exchange_name=$(extract_exchange_name "$@")

    # 如果是测试所有交易所或选择模式，使用默认环境
    if [[ " $* " =~ " --all " ]] || [[ " $* " =~ " --select " ]] || [[ " $* " =~ " --cex " ]] || [[ " $* " =~ " --dex " ]] || [ -z "$exchange_name" ]; then
        print_info "多交易所测试或选择模式，使用系统 Python"
        python3 test_exchanges.py "$@"
        return
    fi

    # 单个交易所测试，使用隔离环境
    local venv_dir="venv_${exchange_name}"

    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║  🚀 启动交易所测试: ${exchange_name}"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""

    # 检查虚拟环境是否存在
    if [ ! -d "$venv_dir" ]; then
        print_warning "虚拟环境不存在，将自动创建"
        if ! install_exchange_deps "$exchange_name"; then
            print_error "依赖安装失败"
            exit 1
        fi
    else
        print_info "使用虚拟环境: ${venv_dir}"
    fi

    # 激活虚拟环境并运行测试
    print_info "激活虚拟环境..."
    source "${venv_dir}/bin/activate"

    # 防止 test_exchanges.py 再次递归委托回本脚本（避免重复一跳与日志噪音）
    export USE_VENV_WRAPPER=1

    # 确保公共依赖已安装
    if ! python -c "import dotenv, httpx, websockets, yaml" 2>/dev/null; then
        print_warning "补充安装公共依赖..."
        pip install python-dotenv httpx websockets pyyaml --quiet
    fi

    print_success "环境准备完成，启动测试..."
    echo ""

    # 运行测试
    python test_exchanges.py "$@"

    # 退出虚拟环境
    deactivate
}

# 运行主函数
main "$@"
