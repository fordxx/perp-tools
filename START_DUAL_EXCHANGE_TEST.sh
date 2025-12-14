#!/bin/bash
# ============================================================
# PerpBot V2 - 阶段 1 两所系统同时测试启动脚本
# ============================================================
#
# 使用方法：
#   chmod +x START_DUAL_EXCHANGE_TEST.sh
#   ./START_DUAL_EXCHANGE_TEST.sh
#
# ============================================================

set -e  # 遇到错误立即停止

echo "╔════════════════════════════════════════════════════════╗"
echo "║  PerpBot V2 - 双交易所同时测试启动器                 ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# ============================================================
# 配置区域（根据你的需求选择方案）
# ============================================================

# 默认方案：Paradex + Extended（已验证 ✅）
# 你可以在运行时通过环境变量覆盖，例如：
#   EXCHANGE_A=aster EXCHANGE_B=grvt RUN_DURATION_SEC=3600 AUTO_CONFIRM=true USE_SOAK=true ./START_DUAL_EXCHANGE_TEST.sh
EXCHANGE_A="${EXCHANGE_A:-paradex}"
EXCHANGE_B="${EXCHANGE_B:-extended}"

# 记录：用户是否显式传入 SYMBOL_A/SYMBOL_B（否则允许 runtime config 覆盖）
SYMBOL_A_WAS_SET="${SYMBOL_A+x}"
SYMBOL_B_WAS_SET="${SYMBOL_B+x}"

# 交易对（默认）
# - Paradex 支持 BTC/USDT（内部会映射到 BTC-USD-PERP）
# - Extended 市场更常见为 BTC/USD
SYMBOL_A="${SYMBOL_A:-BTC/USDT}"
SYMBOL_B="${SYMBOL_B:-BTC/USD}"

# 测试交易对（默认）
SYMBOL="BTC/USDT"
# 可选：为每个交易所单独指定交易对（默认继承 SYMBOL）
SYMBOL_A="${SYMBOL_A:-$SYMBOL}"
SYMBOL_B="${SYMBOL_B:-$SYMBOL}"

# 标记：如果用户通过环境变量显式传了 SYMBOL_A/SYMBOL_B，就不要被 runtime config 覆盖
if [ -n "${SYMBOL_A_WAS_SET:-}" ]; then
    SYMBOL_A_EXPLICIT=1
fi
if [ -n "${SYMBOL_B_WAS_SET:-}" ]; then
    SYMBOL_B_EXPLICIT=1
fi

# 如果未显式设置 SYMBOL_A/SYMBOL_B，且存在 `config/exchanges/<exchange>.yaml`，则优先用其 default_symbol。
# 说明：避免脚本里手写 symbol 和测试器内部的默认 symbol 不一致。
resolve_default_symbol() {
    python3 - <<'PY'
import os
from perpbot.exchanges.runtime_config import load_exchange_runtime_config

exchange = os.environ.get("EXCHANGE_NAME", "")
cfg = load_exchange_runtime_config(exchange)
print(cfg.default_symbol if cfg and cfg.default_symbol else "")
PY
}

if [ -z "${SYMBOL_A_EXPLICIT:-}" ]; then
    export EXCHANGE_NAME="$EXCHANGE_A"
    cfg_sym="$(resolve_default_symbol 2>/dev/null || true)"
    if [ -n "$cfg_sym" ]; then SYMBOL_A="$cfg_sym"; fi
fi
if [ -z "${SYMBOL_B_EXPLICIT:-}" ]; then
    export EXCHANGE_NAME="$EXCHANGE_B"
    cfg_sym="$(resolve_default_symbol 2>/dev/null || true)"
    if [ -n "$cfg_sym" ]; then SYMBOL_B="$cfg_sym"; fi
fi

# 是否包含交易测试（谨慎！）
ENABLE_TRADING=false
TRADING_SIZE=0.001

# 是否跳过账户查询（仅测连接+行情）
SKIP_ACCOUNT_CHECKS="${SKIP_ACCOUNT_CHECKS:-false}"

# 可选：报警 webhook（失败时由 test_exchanges.py POST）
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-${PERPBOT_ALERT_WEBHOOK_URL:-}}"

# 监控循环间隔（秒）
MONITOR_INTERVAL=60

# 模式选择：
# - USE_SOAK=true  : 使用 `test_exchanges.py --soak` 单进程长跑（更容易暴露间歇性问题）
# - USE_SOAK=false : 使用当前的“循环启动 auto-test”模式
USE_SOAK="${USE_SOAK:-false}"

# 是否启用守护：当 SOAK 进程异常退出时自动拉起（并记录重启）
ENABLE_GUARDIAN="${ENABLE_GUARDIAN:-true}"
GUARDIAN_CHECK_INTERVAL_SEC="${GUARDIAN_CHECK_INTERVAL_SEC:-5}"
GUARDIAN_RESTART_BACKOFF_SEC="${GUARDIAN_RESTART_BACKOFF_SEC:-5}"

# 自动停止（秒）
# - 0: 不自动停止（手动 kill）
# - >0: 到时间自动停止并生成 summary
RUN_DURATION_SEC="${RUN_DURATION_SEC:-0}"

# ============================================================
# 启动前检查（Pre-flight Checklist）
# ============================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  启动前检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "❌ .env 文件不存在"
    echo "   请运行: cp .env.example .env"
    exit 1
fi
echo "✅ .env 文件存在"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi
echo "✅ Python3 已安装"

# 检查测试脚本
if [ ! -f test_exchanges.py ]; then
    echo "❌ test_exchanges.py 不存在"
    exit 1
fi
echo "✅ 测试脚本存在"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  测试交易所 A: $EXCHANGE_A"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

EXTRA_PRECHECK_ARGS=()
if [[ "$SKIP_ACCOUNT_CHECKS" =~ ^(true|1|yes|y)$ ]]; then
    EXTRA_PRECHECK_ARGS+=(--skip-account)
fi

PERPBOT_ALERT_WEBHOOK_URL="$ALERT_WEBHOOK_URL" \
./run_exchange_test.sh $EXCHANGE_A --auto-test --symbol $SYMBOL_A "${EXTRA_PRECHECK_ARGS[@]}"

if [ $? -ne 0 ]; then
    echo "❌ 交易所 A 测试失败"
    echo "   请检查凭证配置和网络连接"
    exit 1
fi

echo ""
echo "✅ 交易所 A 测试通过，等待 5 秒观察稳定性..."
sleep 5

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  测试交易所 B: $EXCHANGE_B"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PERPBOT_ALERT_WEBHOOK_URL="$ALERT_WEBHOOK_URL" \
./run_exchange_test.sh $EXCHANGE_B --auto-test --symbol $SYMBOL_B "${EXTRA_PRECHECK_ARGS[@]}"

if [ $? -ne 0 ]; then
    echo "❌ 交易所 B 测试失败"
    echo "   请检查凭证配置和网络连接"
    exit 1
fi

echo ""
echo "✅ 交易所 B 测试通过"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  准备启动双交易所同时测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "配置摘要："
echo "  交易所 A: $EXCHANGE_A"
echo "  交易所 B: $EXCHANGE_B"
echo "  交易对 A: $SYMBOL_A"
echo "  交易对 B: $SYMBOL_B"
echo "  交易测试: $ENABLE_TRADING"
if [ "$ENABLE_TRADING" = true ]; then
    echo "  下单大小: $TRADING_SIZE"
fi
echo ""

AUTO_CONFIRM="${AUTO_CONFIRM:-false}"

if [ -t 0 ]; then
    read -p "⚠️  确认启动双交易所同时测试？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 用户取消测试"
        exit 0
    fi
else
    if [[ "$AUTO_CONFIRM" =~ ^(true|1|yes|y)$ ]]; then
        echo "✅ AUTO_CONFIRM enabled (non-interactive run)"
    else
        echo "❌ 非交互环境，未确认启动。"
        echo "   请重新运行并设置: AUTO_CONFIRM=true"
        exit 1
    fi
fi


echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  启动交易所监控（后台运行）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 创建日志目录
mkdir -p logs

if [ "$USE_SOAK" = true ]; then
    echo "🧪 使用 SOAK 模式（单进程长跑，更容易暴露间歇性问题）"
    SOAK_JITTER_SEC="${SOAK_JITTER_SEC:-0.5}"
    SOAK_MAX_FAIL_RATE="${SOAK_MAX_FAIL_RATE:-0.0}"
    # 如果未设置自动停止，则用一个很大的值（约一年）
    if [ "$RUN_DURATION_SEC" -le 0 ]; then
        RUN_DURATION_SEC=31536000
    fi

    start_soak() {
        local exchange="$1"
        local symbol="$2"
        local log_file="$3"
        local extra_args=()
        local jsonl_file="${log_file%.log}.jsonl"
        # SOAK 也支持 verbose，但不要默认打开，避免 wire-level debug 泄露鉴权头/爆日志
        if [ "${VERBOSE:-false}" = "true" ]; then
            extra_args+=(--verbose)
        fi
        if [[ "$SKIP_ACCOUNT_CHECKS" =~ ^(true|1|yes|y)$ ]]; then
            extra_args+=(--skip-account)
            extra_args+=(--account-every 0)
        fi
        nohup PERPBOT_JSONL_LOG="$jsonl_file" PERPBOT_ALERT_WEBHOOK_URL="$ALERT_WEBHOOK_URL" ./run_exchange_test.sh "$exchange" \
            --soak "$RUN_DURATION_SEC" \
            --interval "$MONITOR_INTERVAL" \
            --jitter "$SOAK_JITTER_SEC" \
            --max-fail-rate "$SOAK_MAX_FAIL_RATE" \
            --symbol "$symbol" \
            "${extra_args[@]}" >> "$log_file" 2>&1 &
        echo $!
    }

    echo "🚀 启动交易所 A SOAK..."
    LOG_A="logs/${EXCHANGE_A}_$(date +%Y%m%d_%H%M%S).log"
    PID_A="$(start_soak "$EXCHANGE_A" "$SYMBOL_A" "$LOG_A")"
    echo "✅ 交易所 A PID: $PID_A"

    echo "🚀 启动交易所 B SOAK..."
    LOG_B="logs/${EXCHANGE_B}_$(date +%Y%m%d_%H%M%S).log"
    PID_B="$(start_soak "$EXCHANGE_B" "$SYMBOL_B" "$LOG_B")"
    echo "✅ 交易所 B PID: $PID_B"
else

# 监控函数：循环执行自动化测试，避免交互式菜单导致后台 EOF 退出
run_monitor_loop() {
    local exchange="$1"
    local log_file="$2"
    local symbol="$3"
    local extra_args=()

    # 可选：开启更详细输出，便于定位间歇性问题
    if [ "${VERBOSE:-false}" = "true" ]; then
        extra_args+=(--verbose)
    fi

    if [ "$ENABLE_TRADING" = true ]; then
        while true; do
            echo "[loop] ts=$(date -Iseconds) exchange=$exchange symbol=$symbol" >> "$log_file"
            set +e
            ./run_exchange_test.sh "$exchange" --auto-test --trading --trading-size "$TRADING_SIZE" --symbol "$symbol" "${extra_args[@]}" >> "$log_file" 2>&1
            rc=$?
            set -e
            echo "[loop] ts=$(date -Iseconds) exchange=$exchange rc=$rc" >> "$log_file"
            sleep "$MONITOR_INTERVAL"
        done
    else
        while true; do
            echo "[loop] ts=$(date -Iseconds) exchange=$exchange symbol=$symbol" >> "$log_file"
            set +e
            ./run_exchange_test.sh "$exchange" --auto-test --symbol "$symbol" "${extra_args[@]}" >> "$log_file" 2>&1
            rc=$?
            set -e
            echo "[loop] ts=$(date -Iseconds) exchange=$exchange rc=$rc" >> "$log_file"
            sleep "$MONITOR_INTERVAL"
        done
    fi
}

# 启动交易所 A 监控
echo "🚀 启动交易所 A 监控..."
LOG_A="logs/${EXCHANGE_A}_$(date +%Y%m%d_%H%M%S).log"
nohup bash -c "$(declare -f run_monitor_loop); run_monitor_loop \"$EXCHANGE_A\" \"$LOG_A\" \"$SYMBOL_A\"" >/dev/null 2>&1 &
PID_A=$!
echo "✅ 交易所 A PID: $PID_A"

# 等待 5 秒
echo "⏳ 等待 5 秒，确保交易所 A 稳定运行..."
sleep 5

# 检查进程是否还在运行
if ! ps -p $PID_A > /dev/null; then
    echo "❌ 交易所 A 启动失败（进程已退出）"
    echo "   查看日志: tail -f logs/${EXCHANGE_A}_*.log"
    exit 1
fi
echo "✅ 交易所 A 运行正常"

# 启动交易所 B 监控
echo ""
echo "🚀 启动交易所 B 监控..."
LOG_B="logs/${EXCHANGE_B}_$(date +%Y%m%d_%H%M%S).log"
nohup bash -c "$(declare -f run_monitor_loop); run_monitor_loop \"$EXCHANGE_B\" \"$LOG_B\" \"$SYMBOL_B\"" >/dev/null 2>&1 &
PID_B=$!
echo "✅ 交易所 B PID: $PID_B"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣  双交易所同时运行中"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 运行状态："
echo "  交易所 A ($EXCHANGE_A): PID $PID_A"
echo "  交易所 B ($EXCHANGE_B): PID $PID_B"
echo ""
echo "📝 查看日志："
echo "  交易所 A: tail -f $LOG_A"
echo "  交易所 B: tail -f $LOG_B"
echo ""
echo "🛑 停止测试："
echo "  kill $PID_A $PID_B"
echo ""
echo "⏱️  建议运行时间: 30-60 分钟"
echo ""

# 保存 PID 到文件
echo $PID_A > /tmp/perpbot_exchange_a.pid
echo $PID_B > /tmp/perpbot_exchange_b.pid

START_TS="$(date -Iseconds)"
START_EPOCH="$(date +%s)"

# Soak 模式守护：进程异常退出就自动拉起（并写入 guardian 日志）
if [ "$USE_SOAK" = true ] && [ "$ENABLE_GUARDIAN" = true ]; then
    GUARD_LOG="logs/dual_exchange_guardian_$(date +%Y%m%d_%H%M%S).log"
    (
        echo "[guardian] started: $START_TS" >> "$GUARD_LOG"
        echo "[guardian] start_epoch: $START_EPOCH" >> "$GUARD_LOG"
        echo "[guardian] A=$EXCHANGE_A symbol=$SYMBOL_A log=$LOG_A" >> "$GUARD_LOG"
        echo "[guardian] B=$EXCHANGE_B symbol=$SYMBOL_B log=$LOG_B" >> "$GUARD_LOG"

        a_restarts=0
        b_restarts=0

        while true; do
            sleep "$GUARDIAN_CHECK_INTERVAL_SEC"

            # If duration elapsed, exit (watchdog handles kill/summary).
            if [ "$RUN_DURATION_SEC" -gt 0 ]; then
                now="$(date +%s)"
                if [ $((now - START_EPOCH)) -ge "$RUN_DURATION_SEC" ]; then
                    echo "[guardian] duration elapsed, exiting" >> "$GUARD_LOG"
                    exit 0
                fi
            fi

            pid_a="$(cat /tmp/perpbot_exchange_a.pid 2>/dev/null || true)"
            if [ -n "$pid_a" ] && ! ps -p "$pid_a" >/dev/null 2>&1; then
                a_restarts=$((a_restarts + 1))
                echo "[guardian] A down (pid=$pid_a), restart #$a_restarts" >> "$GUARD_LOG"
                sleep "$GUARDIAN_RESTART_BACKOFF_SEC"
                new_pid="$(start_soak "$EXCHANGE_A" "$SYMBOL_A" "$LOG_A")"
                echo "$new_pid" > /tmp/perpbot_exchange_a.pid
                echo "[guardian] A restarted pid=$new_pid" >> "$GUARD_LOG"
            fi

            pid_b="$(cat /tmp/perpbot_exchange_b.pid 2>/dev/null || true)"
            if [ -n "$pid_b" ] && ! ps -p "$pid_b" >/dev/null 2>&1; then
                b_restarts=$((b_restarts + 1))
                echo "[guardian] B down (pid=$pid_b), restart #$b_restarts" >> "$GUARD_LOG"
                sleep "$GUARDIAN_RESTART_BACKOFF_SEC"
                new_pid="$(start_soak "$EXCHANGE_B" "$SYMBOL_B" "$LOG_B")"
                echo "$new_pid" > /tmp/perpbot_exchange_b.pid
                echo "[guardian] B restarted pid=$new_pid" >> "$GUARD_LOG"
            fi
        done
    ) &
fi

# 可选：自动停止 + 生成 summary（更容易暴露“间歇性失败/抖动”）
if [ "$RUN_DURATION_SEC" -gt 0 ]; then
    echo "⏱️  已设置自动停止: ${RUN_DURATION_SEC}s"
    (
        sleep "$RUN_DURATION_SEC"
        END_TS="$(date -Iseconds)"

        WATCHDOG_LOG="logs/dual_exchange_watchdog_$(date +%Y%m%d_%H%M%S).log"
        echo "[watchdog] started: $START_TS" > "$WATCHDOG_LOG"
        echo "[watchdog] start_epoch: $START_EPOCH" >> "$WATCHDOG_LOG"
        pid_a="$(cat /tmp/perpbot_exchange_a.pid 2>/dev/null || echo "$PID_A")"
        pid_b="$(cat /tmp/perpbot_exchange_b.pid 2>/dev/null || echo "$PID_B")"
        echo "[watchdog] stopping exchanges at: $END_TS (A=$pid_a B=$pid_b)" >> "$WATCHDOG_LOG"

        kill "$pid_a" "$pid_b" 2>/dev/null || true

        SUMMARY="logs/dual_exchange_summary_$(date +%Y%m%d_%H%M%S).txt"
        {
            echo "Dual Exchange Summary"
            echo "Start: $START_TS"
            echo "End:   $END_TS"
            echo ""
            for f in "$LOG_A" "$LOG_B"; do
                echo "===== $f ====="
                if [ -f "$f" ]; then
                    soak_runs=$(rg -n '\[soak\] i=' "$f" 2>/dev/null | wc -l | tr -d ' ')
                    if [ "$soak_runs" -gt 0 ]; then
                        runs="$soak_runs"
                        fails=$(rg -n '\[soak\] i=.* ok=0' "$f" 2>/dev/null | wc -l | tr -d ' ')
                    else
                        runs=$(rg -n '\[loop\].* exchange=.* rc=' "$f" 2>/dev/null | wc -l | tr -d ' ')
                        fails=$(rg -n '\[loop\].* rc=[1-9][0-9]*' "$f" 2>/dev/null | wc -l | tr -d ' ')
                    fi
                    errors=$(rg -n 'ERROR|Traceback|exception' "$f" 2>/dev/null | wc -l | tr -d ' ')
                    warnings=$(rg -n 'WARNING|⚠️' "$f" 2>/dev/null | wc -l | tr -d ' ')
                    echo "runs=$runs fails=$fails errors=$errors warnings=$warnings"
                    echo "--- tail ---"
                    tail -n 30 "$f" || true
                else
                    echo "(missing log file)"
                fi
                echo ""
            done
        } > "$SUMMARY"

        echo "🧾 Summary written: $SUMMARY"
    ) &
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 双交易所同时测试已启动"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
