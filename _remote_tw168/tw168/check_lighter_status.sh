#!/bin/bash
# 检查 Lighter 账户状态

echo "========================================"
echo "Lighter 账户状态检查"
echo "========================================"
echo ""

WALLET="0x87e04b0fbcb0c5bc661eeff5a1d88b692af41c98"

echo "钱包地址: $WALLET"
echo ""

# 查询账户信息
echo "查询 Lighter 账户..."
curl -s "https://mainnet.zklighter.elliot.ai/accounts?by=l1_address&value=$WALLET" | python3 -m json.tool

echo ""
echo "========================================"
echo "如果看到 account_index，请更新配置:"
echo "  LIGHTER_ACCOUNT_INDEX=<显示的数字>"
echo "========================================"
