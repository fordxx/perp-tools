#!/bin/bash
# Interactive Telegram notification setup script
set -e

echo "========================================="
echo "TW168 Telegram 通知配置"
echo "========================================="
echo ""

# Check if .env exists
if [ ! -f "/home/ubuntu/tw168/.env" ]; then
    echo "❌ Error: /home/ubuntu/tw168/.env not found"
    exit 1
fi

# Check if already configured
if grep -q "^TELEGRAM_BOT_TOKEN=" /home/ubuntu/tw168/.env 2>/dev/null; then
    echo "⚠️  Telegram配置已存在"
    echo ""
    grep "^TELEGRAM_BOT_TOKEN=" /home/ubuntu/tw168/.env
    grep "^TELEGRAM_CHAT_ID=" /home/ubuntu/tw168/.env
    echo ""
    read -p "是否要更新配置？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消配置"
        exit 0
    fi
fi

echo "📱 第一步：获取Bot Token"
echo "-------------------"
echo "1. 在Telegram中搜索 @BotFather"
echo "2. 发送 /newbot 创建新bot"
echo "3. 按提示设置bot名称和用户名"
echo "4. 复制BotFather给你的Token"
echo ""
echo "Token格式示例: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
echo ""
read -p "请输入Bot Token: " BOT_TOKEN

if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Token不能为空"
    exit 1
fi

# Validate token format
if [[ ! "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
    echo "⚠️  警告: Token格式可能不正确"
    read -p "是否继续？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "✅ Bot Token已记录"
echo ""

echo "🆔 第二步：获取Chat ID"
echo "-------------------"
echo "1. 在Telegram中搜索 @userinfobot"
echo "2. 启动对话，查看你的ID"
echo "   或者"
echo "3. 先向你的bot发送 /start"
echo "4. 访问: https://api.telegram.org/bot${BOT_TOKEN}/getUpdates"
echo "5. 在返回JSON中找到 \"chat\":{\"id\":数字}"
echo ""
echo "个人Chat ID示例: 123456789"
echo "群组Chat ID示例: -1001234567890 (负数)"
echo ""
read -p "请输入Chat ID: " CHAT_ID

if [ -z "$CHAT_ID" ]; then
    echo "❌ Chat ID不能为空"
    exit 1
fi

# Validate chat ID is numeric
if ! [[ "$CHAT_ID" =~ ^-?[0-9]+$ ]]; then
    echo "❌ Chat ID必须是数字（个人ID为正数，群组ID为负数）"
    exit 1
fi

echo ""
echo "✅ Chat ID已记录"
echo ""

# Test configuration
echo "🧪 测试Telegram配置..."
echo ""

TEST_URL="https://api.telegram.org/bot${BOT_TOKEN}/sendMessage"
TEST_RESPONSE=$(curl -s -X POST "$TEST_URL" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${CHAT_ID}\",\"text\":\"[tw168] 测试消息：Telegram通知配置成功！\"}")

if echo "$TEST_RESPONSE" | grep -q '"ok":true'; then
    echo "✅ 测试消息发送成功！请检查Telegram是否收到消息。"
else
    echo "❌ 测试消息发送失败"
    echo "响应: $TEST_RESPONSE"
    echo ""
    read -p "是否仍要保存配置？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "💾 保存配置到 .env 文件..."

# Backup .env
cp /home/ubuntu/tw168/.env /home/ubuntu/tw168/.env.backup_telegram_$(date +%Y%m%d_%H%M%S)

# Remove old config if exists
sed -i '/^TELEGRAM_BOT_TOKEN=/d' /home/ubuntu/tw168/.env
sed -i '/^TELEGRAM_CHAT_ID=/d' /home/ubuntu/tw168/.env

# Add new config
echo "" >> /home/ubuntu/tw168/.env
echo "# Telegram notifications" >> /home/ubuntu/tw168/.env
echo "TELEGRAM_BOT_TOKEN=${BOT_TOKEN}" >> /home/ubuntu/tw168/.env
echo "TELEGRAM_CHAT_ID=${CHAT_ID}" >> /home/ubuntu/tw168/.env

echo "✅ 配置已保存"
echo ""

# Restart service
echo "🔄 重启Docker服务以应用配置..."
cd /home/ubuntu/tw168
sudo docker compose restart

echo ""
echo "⏳ 等待服务启动..."
sleep 5

echo ""
echo "========================================="
echo "✅ Telegram配置完成！"
echo "========================================="
echo ""
echo "📋 配置信息:"
echo "   Bot Token: ${BOT_TOKEN:0:20}..."
echo "   Chat ID: $CHAT_ID"
echo ""
echo "📨 你将收到以下类型的通知:"
echo "   • 止损单失败告警"
echo "   • 紧急平仓执行通知"
echo "   • 止损失败率过高告警"
echo "   • 交易开仓/平仓信息"
echo ""
echo "🧪 测试通知:"
echo "   sudo docker exec -it tw168-tv-okx-1 python3 -c \\"
echo "   from app.notify import notify_info; \\"
echo "   notify_info('手动测试消息')\\"
echo ""
echo "========================================="
