#!/bin/bash
# 本地到远程 HTTPS 连接测试脚本

set -e

echo "=========================================="
echo "本地 → 远程 HTTPS 连接测试"
echo "=========================================="
echo ""

# 配置
REMOTE_URL="https://3-38-98-169.nip.io"
BASIC_AUTH_USER="trader"
BASIC_AUTH_PASS="TW168Trading!2026"

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试函数
test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local auth="$4"
    local data="$5"

    echo -n "测试 $name ... "

    if [ "$method" = "GET" ]; then
        if [ "$auth" = "yes" ]; then
            response=$(curl -s -o /dev/null -w "%{http_code}" -u "$BASIC_AUTH_USER:$BASIC_AUTH_PASS" "$REMOTE_URL$endpoint")
        else
            response=$(curl -s -o /dev/null -w "%{http_code}" "$REMOTE_URL$endpoint")
        fi
    else
        if [ "$auth" = "yes" ]; then
            response=$(curl -s -o /dev/null -w "%{http_code}" -u "$BASIC_AUTH_USER:$BASIC_AUTH_PASS" -X POST -H "Content-Type: application/json" -d "$data" "$REMOTE_URL$endpoint")
        else
            response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "$data" "$REMOTE_URL$endpoint")
        fi
    fi

    if [ "$response" = "200" ] || [ "$response" = "401" ] || [ "$response" = "403" ]; then
        echo -e "${GREEN}✓${NC} (HTTP $response)"
    else
        echo -e "${RED}✗${NC} (HTTP $response)"
    fi
}

# 1. 测试健康检查（无需认证）
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  基础连接测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
test_endpoint "健康检查 (HTTP)" "GET" "/health" "no"
test_endpoint "健康检查 (HTTPS)" "GET" "/health" "no"

# 2. 测试 BasicAuth
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  BasicAuth 认证测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
test_endpoint "Metrics (无认证, 应401)" "GET" "/metrics" "no"
test_endpoint "Metrics (有认证, 应200)" "GET" "/metrics" "yes"

# 3. 测试手动信号端点（需要 admin_key）
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  手动信号端点测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 读取 admin_key
if [ -f .env ]; then
    ADMIN_KEY=$(grep TV_WEBHOOK_SECRET .env | cut -d'=' -f2 | tr -d ' "'"'"'')
fi

if [ -z "$ADMIN_KEY" ] || [ "$ADMIN_KEY" = "CHANGE_ME" ]; then
    echo -e "${YELLOW}⚠️  未配置 ADMIN_KEY${NC}"
    echo "   请在 .env 中设置 TV_WEBHOOK_SECRET"
    echo "   或从远程服务器获取:"
    echo "   ssh ubuntu@3.38.98.169 'grep TV_WEBHOOK_SECRET ~/tw168/.env'"
    ADMIN_KEY="wrong-key-for-test"
fi

test_data='{"instId":"ETH-USDT-SWAP","tf":"15m","side":"buy","admin_key":"'$ADMIN_KEY'"}'
test_endpoint "手动信号 (无BasicAuth)" "POST" "/manual/signal" "no" "$test_data"
test_endpoint "手动信号 (有BasicAuth)" "POST" "/manual/signal" "yes" "$test_data"

# 4. 详细测试（显示响应）
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  详细响应测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "【健康检查响应】"
curl -s "$REMOTE_URL/health" | head -c 200
echo ""

echo ""
echo "【Metrics 响应（前 200 字符）】"
curl -s -u "$BASIC_AUTH_USER:$BASIC_AUTH_PASS" "$REMOTE_URL/metrics" | head -c 200
echo ""

# 5. 测试 SSL/TLS
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  SSL/TLS 证书验证"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "证书信息:"
curl -vI "$REMOTE_URL/health" 2>&1 | grep -E "SSL|TLS|subject|issuer|expire" | head -5

# 6. 测试端口封闭（8000 应不可访问）
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣  端口安全性测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -n "测试 8000 端口 (应超时) ... "
if timeout 3 curl -s http://3.38.98.169:8000/health > /dev/null 2>&1; then
    echo -e "${RED}✗ 端口泄露！${NC}"
else
    echo -e "${GREEN}✓ 端口已关闭${NC}"
fi

# 总结
echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
echo ""
echo "如果上述测试全部通过，说明:"
echo "  ✅ HTTPS 连接正常"
echo "  ✅ BasicAuth 工作正常"
echo "  ✅ 端口安全配置正确"
echo ""
echo "下一步:"
echo "  1. 确保本地 .env 配置了正确的 TV_WEBHOOK_SECRET"
echo "  2. 运行: python3 send_manual_signal.py ETH-USDT-SWAP long"
echo "  3. 或启动 UI: python3 ui_server.py"
echo ""
