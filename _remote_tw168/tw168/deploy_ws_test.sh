#!/bin/bash
# Deploy Lighter WebSocket test configuration

set -e

echo "========================================"
echo "部署 Lighter WebSocket 测试配置"
echo "========================================"
echo ""

REMOTE_HOST="ubuntu@3.38.98.169"
REMOTE_DIR="/home/ubuntu/tw168"
SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"

echo "📋 测试配置："
echo "  - WebSocket 监控: 6 个币种 (ETH, BTC, SOL, LINK, DOGE, BNB)"
echo "  - OKX K线数据: 所有 17 个币种"
echo "  - 交易执行: Lighter DEX"
echo ""

echo "Step 1: 同步更新的代码..."
echo "  - app/main.py (WebSocket 配置)"
rsync -avz \
  -e "ssh -i $SSH_KEY" \
  app/main.py \
  "$REMOTE_HOST:$REMOTE_DIR/app/"

echo "  - Lighter 客户端代码 (WebSocket 支持)"
rsync -avz \
  -e "ssh -i $SSH_KEY" \
  /home/fordxx/perp-tools/src/perpbot/exchanges/lighter.py \
  /home/fordxx/perp-tools/src/perpbot/exchanges/lighter_websocket.py \
  "$REMOTE_HOST:$REMOTE_DIR/src/perpbot/exchanges/"

echo ""
echo "Step 2: 重启容器..."
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'EOF'
cd /home/ubuntu/tw168

echo "停止容器..."
docker compose down

echo "启动容器..."
docker compose up -d

echo "等待容器启动..."
sleep 5

echo ""
echo "========================================"
echo "容器状态:"
echo "========================================"
docker compose ps

echo ""
echo "========================================"
echo "最近日志 (WebSocket):"
echo "========================================"
docker compose logs --tail=100 | grep -i "websocket\|lighter\|订阅\|subscrib" || echo "No WebSocket logs yet"

echo ""
echo "========================================"
echo "✅ 部署完成！"
echo "========================================"
echo ""
echo "监控 WebSocket 日志:"
echo "  docker compose logs -f | grep -i 'ws盘口\|ws成交\|websocket'"
echo ""
echo "查看所有日志:"
echo "  docker compose logs -f"
echo ""
EOF

echo ""
echo "========================================"
echo "✅ 部署完成！"
echo "========================================"
echo ""
echo "查看实时日志:"
echo "  ssh -i $SSH_KEY $REMOTE_HOST 'cd /home/ubuntu/tw168 && docker compose logs -f'"
echo ""
echo "过滤 WebSocket 日志:"
echo "  ssh -i $SSH_KEY $REMOTE_HOST 'cd /home/ubuntu/tw168 && docker compose logs -f | grep -i \"ws盘口\|ws成交\"'"
echo ""
