#!/bin/bash

# TW168 UI服务器启动脚本

set -euo pipefail

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 虚拟环境路径
VENV_PATH=""
if [ -d ".venv" ]; then
    VENV_PATH=".venv"
elif [ -d "venv" ]; then
    VENV_PATH="venv"
fi
PYTHON="${VENV_PATH}/bin/python"

PID_FILE=".ui_server.pid"
LOG_FILE="ui_9000.log"

# 检查虚拟环境是否存在
if [ -z "${VENV_PATH:-}" ] || [ ! -d "$VENV_PATH" ]; then
    echo "❌ 虚拟环境不存在: .venv 或 venv"
    echo "请首先运行: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# 检查Python是否可用
if [ ! -f "$PYTHON" ]; then
    echo "❌ Python可执行文件不存在: $PYTHON"
    exit 1
fi

# 检查是否已经有进程在运行（优先 pidfile，其次 pgrep）
if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${PID:-}" ] && kill -0 "$PID" >/dev/null 2>&1; then
        echo "⚠️  UI服务器已在运行 (pid=$PID)"
        echo "如需重启，请先运行: ./stop_ui_server.sh"
        exit 1
    fi
fi
if pgrep -f "ui_server.py" >/dev/null 2>&1; then
    echo "⚠️  UI服务器已在运行 (pgrep 命中)"
    echo "如需重启，请先运行: ./stop_ui_server.sh"
    exit 1
fi

# 安装必要的依赖
echo "📦 检查依赖..."
"$PYTHON" -m pip install jinja2 python-multipart -q 2>/dev/null

# 确保本地 UI 转发走 443（远程通常不开放 8000）
DEFAULT_REMOTE_BASE_URL="https://trader:TW168Trading!2026@3-38-98-169.nip.io"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "📝 已生成 .env（来自 .env.example）"
    else
        cat > .env <<EOF
TRADING_SERVICE_BASE_URL=${DEFAULT_REMOTE_BASE_URL}
TV_WEBHOOK_SECRET=CHANGE_ME
EXCHANGE=lighter
TRADING_ENABLED=false
EOF
        echo "📝 已生成最小 .env"
    fi
fi

# 如果仍指向远程 :8000（常见会超时），自动替换为 443 入口
if rg -n "^TRADING_SERVICE_BASE_URL=http://3\\.38\\.98\\.169:8000\\s*$" .env >/dev/null 2>&1; then
    sed -i 's|^TRADING_SERVICE_BASE_URL=http://3\\.38\\.98\\.169:8000\\s*$|TRADING_SERVICE_BASE_URL='"${DEFAULT_REMOTE_BASE_URL}"'|' .env
    echo "🔧 已将 TRADING_SERVICE_BASE_URL 从 :8000 修正为 443 (${DEFAULT_REMOTE_BASE_URL})"
fi

# 如果没配置 TRADING_SERVICE_BASE_URL，追加默认值（不覆盖用户已有配置）
if ! rg -n "^TRADING_SERVICE_BASE_URL=" .env >/dev/null 2>&1; then
    echo "TRADING_SERVICE_BASE_URL=${DEFAULT_REMOTE_BASE_URL}" >> .env
    echo "🔧 已追加 TRADING_SERVICE_BASE_URL=${DEFAULT_REMOTE_BASE_URL}"
fi

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

# 默认后台常驻运行，避免 terminal 关闭/CTRL+C 导致 UI 掉线。
# 如需前台运行：RUN_FOREGROUND=1 ./start_ui_server.sh
if [ "${RUN_FOREGROUND:-0}" = "1" ]; then
    "$PYTHON" ui_server.py
    exit 0
fi

echo "🧷 以后台模式启动 (日志: $LOG_FILE)"
# Safety: UI 本地只做转发时，强制禁用本地交易相关开关，避免“UI 没读到 .env/没配转发”时误在本机开单。
export TRADING_ENABLED=false
export ENTRY_TWO_LIMIT_ENABLED=false
export LADDER_ENABLED=false

nohup "$PYTHON" ui_server.py >"$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

# 简单健康检查：等待端口监听 + /health 可达
echo "⏳ 等待 UI 启动..."
for i in {1..30}; do
    if ss -tuln 2>/dev/null | grep -q ":9000"; then
        if curl -sS -m 1 http://127.0.0.1:9000/health >/dev/null 2>&1; then
            echo "✅ UI 已启动 (pid=$PID)"
            echo "🌐 直接访问: http://localhost:9000"
            exit 0
        fi
    fi
    sleep 0.2
done

echo "❌ UI 启动失败或健康检查超时 (pid=$PID)"
echo "👉 请查看日志: $LOG_FILE"
exit 1
