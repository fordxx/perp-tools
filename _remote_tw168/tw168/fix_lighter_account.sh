#!/bin/bash
# 修复 Lighter Account Index 配置

set -e

echo "==================================================================="
echo "修复 Lighter Account Index"
echo "==================================================================="

# 读取用户输入的正确值
read -p "请输入正确的 LIGHTER_ACCOUNT_INDEX (例如: 0): " ACCOUNT_INDEX
read -p "请输入正确的 LIGHTER_API_KEY_INDEX (例如: 0): " API_KEY_INDEX

echo ""
echo "准备修改配置："
echo "  LIGHTER_ACCOUNT_INDEX: 1 → $ACCOUNT_INDEX"
echo "  LIGHTER_API_KEY_INDEX: 2 → $API_KEY_INDEX"
echo ""

read -p "确认修改？(yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "取消修改"
    exit 1
fi

# 备份
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# 修改本地文件
sed -i "s/^LIGHTER_ACCOUNT_INDEX=.*/LIGHTER_ACCOUNT_INDEX=$ACCOUNT_INDEX/" .env
sed -i "s/^LIGHTER_API_KEY_INDEX=.*/LIGHTER_API_KEY_INDEX=$API_KEY_INDEX/" .env

echo ""
echo "✅ 本地 .env 已修改"

# 同步到远程
echo ""
echo "同步到远程服务器..."
scp -i ../../LightsailDefaultKey-ap-northeast-2.pem .env ubuntu@3.38.98.169:/home/ubuntu/tw168/.env

echo ""
echo "✅ 远程 .env 已更新"

# 重启远程服务
echo ""
echo "重启远程服务..."
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 "cd /home/ubuntu/tw168 && docker compose restart"

echo ""
echo "==================================================================="
echo "✅ 修复完成！"
echo "==================================================================="
echo ""
echo "验证配置："
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 "cd /home/ubuntu/tw168 && docker compose logs --tail 50 | grep -i 'lighter\|api key'"

echo ""
echo "如果还有问题，请检查日志："
echo "  ssh ubuntu@3.38.98.169"
echo "  cd /home/ubuntu/tw168"
echo "  docker compose logs -f | grep -i lighter"
