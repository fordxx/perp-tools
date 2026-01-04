#!/bin/bash
cd /home/fordxx/perp-tools/_remote_tw168/tw168
source .venv/bin/activate

# 获取admin_key
ADMIN_KEY=$(python -c "from app.config import SETTINGS; print(SETTINGS.tv_webhook_secret)")

# 启动服务器
echo "启动服务器..."
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
SERVER_PID=$!

# 等待服务器启动
echo "等待服务器启动..."
sleep 5

# 测试API
echo "测试手动信号API..."
curl -X POST http://127.0.0.1:8001/manual/signal \
  -H "Content-Type: application/json" \
  -d "{\"instId\": \"ETH-USDT-SWAP\", \"tf\": \"1h\", \"side\": \"long\", \"type\": \"DIV\", \"admin_key\": \"$ADMIN_KEY\"}" \
  -s -w "\nHTTP Status: %{http_code}\n"

echo ""
echo "测试完成，停止服务器..."
kill $SERVER_PID 2>/dev/null