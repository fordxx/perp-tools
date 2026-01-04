#!/bin/bash

# TW168 UI服务器启动脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 虚拟环境路径
VENV_PATH=".venv"
PYTHON="${VENV_PATH}/bin/python"

# 检查虚拟环境是否存在
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ 虚拟环境不存在: $VENV_PATH"
    echo "请首先运行: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# 检查Python是否可用
if [ ! -f "$PYTHON" ]; then
    echo "❌ Python可执行文件不存在: $PYTHON"
    exit 1
fi

# 检查是否已经有进程在运行
if pgrep -f "ui_server.py" > /dev/null 2>&1; then
    echo "⚠️  UI服务器已在运行"
    echo "如需重启，请先运行: ./stop_ui_server.sh"
    exit 1
fi

# 安装必要的依赖
echo "📦 检查依赖..."
"$PYTHON" -m pip install jinja2 python-multipart -q 2>/dev/null

# 启动服务器
echo "🚀 启动TW168 UI服务器..."
echo "📱 访问地址: http://localhost:9000"
echo ""
echo "功能包括:"
echo "  ✅ 实时系统状态监控"
echo "  ✅ 手动交易信号发送"
echo "  ✅ 信号历史记录查看"
echo "  ✅ 活跃仓位显示"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 启动UI服务器
"$PYTHON" ui_server.py
