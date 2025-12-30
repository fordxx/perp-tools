#!/bin/bash
# TW168 系统监控面板
# 一键查看系统运行状态、配置、资源使用等

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# SSH配置
SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"
SERVER="ubuntu@3.38.98.169"

# 清屏
clear

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           TW168 交易系统监控面板 - $(date '+%Y-%m-%d %H:%M:%S')           ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo

# 1. 系统状态
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📊 系统运行状态${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

ssh -i "$SSH_KEY" "$SERVER" "cd ~/tw168 && docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'" 2>/dev/null | while IFS= read -r line; do
    if echo "$line" | grep -q "Up"; then
        echo -e "${GREEN}✅ $line${NC}"
    elif echo "$line" | grep -q "Exit\|Down"; then
        echo -e "${RED}❌ $line${NC}"
    else
        echo "$line"
    fi
done

echo

# 2. 资源使用
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}💻 资源使用情况${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

STATS=$(ssh -i "$SSH_KEY" "$SERVER" "docker stats --no-stream --format 'CPU: {{.CPUPerc}}|内存: {{.MemUsage}}|网络: {{.NetIO}}' tw168-tv-okx-1" 2>/dev/null)
if [ -n "$STATS" ]; then
    CPU=$(echo "$STATS" | cut -d'|' -f1)
    MEM=$(echo "$STATS" | cut -d'|' -f2)
    NET=$(echo "$STATS" | cut -d'|' -f3)

    echo -e "  ${CYAN}CPU:${NC}    $CPU"
    echo -e "  ${CYAN}内存:${NC}   $MEM"
    echo -e "  ${CYAN}网络:${NC}   $NET"
else
    echo -e "${RED}  ❌ 无法获取资源信息${NC}"
fi

echo

# 3. 关键配置
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}⚙️  关键配置参数${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

CONFIG=$(ssh -i "$SSH_KEY" "$SERVER" "cd ~/tw168 && docker compose exec -T tv-okx python3 -c '
import sys
sys.path.insert(0, \"/app\")
from app.config import SETTINGS, get_lookback_bars

print(\"RISK_PER_TRADE=\" + str(SETTINGS.risk_per_trade_usdt))
print(\"COOLDOWN=\" + str(SETTINGS.cooldown_seconds))
print(\"ATR_BUFFER=\" + str(SETTINGS.atr_buffer_mult))
print(\"MIN_BUFFER=\" + str(SETTINGS.min_buffer_bps))
print(\"TRAIL_START=\" + str(SETTINGS.trail_start_r))
print(\"BACKUP_SL=\" + str(SETTINGS.backup_sl_enabled))
print(\"LADDER=\" + str(SETTINGS.ladder_enabled))
print(\"LOOKBACK_5M=\" + str(get_lookback_bars(\"5m\")))
print(\"LOOKBACK_1H=\" + str(get_lookback_bars(\"1h\")))
print(\"LOOKBACK_4H=\" + str(get_lookback_bars(\"4h\")))
' 2>/dev/null")

if [ -n "$CONFIG" ]; then
    echo "$CONFIG" | while IFS='=' read -r key value; do
        case $key in
            RISK_PER_TRADE)
                echo -e "  ${CYAN}每单风险:${NC}         \$${value}"
                ;;
            COOLDOWN)
                mins=$((value / 60))
                echo -e "  ${CYAN}冷却时间:${NC}         ${value}秒 (${mins}分钟)"
                ;;
            ATR_BUFFER)
                echo -e "  ${CYAN}ATR缓冲:${NC}          ${value}倍"
                ;;
            MIN_BUFFER)
                echo -e "  ${CYAN}最小缓冲:${NC}         ${value}bps ($(echo "scale=2; $value/100" | bc)%)"
                ;;
            TRAIL_START)
                echo -e "  ${CYAN}追踪起始:${NC}         ${value}R"
                ;;
            BACKUP_SL)
                if [ "$value" = "True" ]; then
                    echo -e "  ${CYAN}备用止损:${NC}         ${GREEN}✅ 已启用${NC}"
                else
                    echo -e "  ${CYAN}备用止损:${NC}         ${RED}❌ 未启用${NC}"
                fi
                ;;
            LADDER)
                if [ "$value" = "True" ]; then
                    echo -e "  ${CYAN}分级挂单:${NC}         ${GREEN}✅ 已启用${NC}"
                else
                    echo -e "  ${CYAN}分级挂单:${NC}         ${RED}❌ 未启用${NC}"
                fi
                ;;
            LOOKBACK_5M)
                echo -e "  ${CYAN}止损回溯(5m):${NC}     ${value}根K线 ($(echo "scale=1; $value*5/60" | bc)小时)"
                ;;
            LOOKBACK_1H)
                echo -e "  ${CYAN}止损回溯(1h):${NC}     ${value}根K线 (${value}小时)"
                ;;
            LOOKBACK_4H)
                echo -e "  ${CYAN}止损回溯(4h):${NC}     ${value}根K线 ($(echo "scale=0; $value*4/24" | bc)天)"
                ;;
        esac
    done
else
    echo -e "${RED}  ❌ 无法获取配置信息${NC}"
fi

echo

# 4. 监控币种
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📈 监控币种列表${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

ssh -i "$SSH_KEY" "$SERVER" "cd ~/tw168 && grep '^CANDLE_WS_SYMBOL_TFS=' .env 2>/dev/null | cut -d'=' -f2" | tr ',' '\n' | while IFS=':' read -r symbol tf; do
    symbol=$(echo "$symbol" | xargs)  # trim whitespace
    if [ -z "$tf" ]; then
        tf="默认"
    fi

    # 解析币种名称
    coin=$(echo "$symbol" | cut -d'-' -f1)

    # 根据周期上色
    case $tf in
        5m)
            echo -e "  ${GREEN}●${NC} ${CYAN}$coin${NC} (${YELLOW}$tf${NC})"
            ;;
        *m|*h)
            echo -e "  ${BLUE}●${NC} ${CYAN}$coin${NC} (${YELLOW}$tf${NC})"
            ;;
        *)
            echo -e "  ${PURPLE}●${NC} ${CYAN}$coin${NC} (${YELLOW}$tf${NC})"
            ;;
    esac
done

echo

# 5. 近期日志
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📝 最近日志 (最新10条)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

ssh -i "$SSH_KEY" "$SERVER" "cd ~/tw168 && docker compose logs --tail=10 tv-okx 2>/dev/null" | while IFS= read -r line; do
    if echo "$line" | grep -qi "error\|fail\|exception"; then
        echo -e "${RED}$line${NC}"
    elif echo "$line" | grep -qi "warning\|warn"; then
        echo -e "${YELLOW}$line${NC}"
    elif echo "$line" | grep -qi "success\|filled\|completed"; then
        echo -e "${GREEN}$line${NC}"
    else
        echo "$line"
    fi
done

echo

# 6. 快捷操作提示
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🎮 快捷操作${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${CYAN}重启服务:${NC}   ./monitor.sh restart"
echo -e "  ${CYAN}查看日志:${NC}   ./monitor.sh logs"
echo -e "  ${CYAN}SSH登录:${NC}    ./monitor.sh ssh"
echo -e "  ${CYAN}检查仓位:${NC}   ./monitor.sh positions"
echo -e "  ${CYAN}刷新面板:${NC}   ./monitor.sh"
echo

# 处理命令行参数
case "${1:-}" in
    restart)
        echo -e "${YELLOW}🔄 重启服务中...${NC}"
        ssh -i "$SSH_KEY" "$SERVER" "cd ~/tw168 && docker compose restart"
        echo -e "${GREEN}✅ 服务已重启${NC}"
        ;;
    logs)
        echo -e "${CYAN}📋 实时日志 (按Ctrl+C退出)${NC}"
        echo
        ssh -i "$SSH_KEY" "$SERVER" "cd ~/tw168 && docker compose logs -f --tail=50 tv-okx"
        ;;
    ssh)
        echo -e "${CYAN}🔗 SSH登录到服务器...${NC}"
        ssh -i "$SSH_KEY" "$SERVER"
        ;;
    positions)
        echo -e "${CYAN}📊 检查当前仓位...${NC}"
        echo
        ssh -i "$SSH_KEY" "$SERVER" "cd ~/tw168 && docker compose exec -T tv-okx python3 scripts/check_positions.py 2>/dev/null" || \
        echo -e "${YELLOW}⚠️  暂无仓位检查脚本${NC}"
        ;;
esac

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}监控完成 - $(date '+%H:%M:%S')${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo
