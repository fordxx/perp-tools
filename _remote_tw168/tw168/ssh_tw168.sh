#!/bin/bash
# 快速 SSH 登录到 tw168 服务器

SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"
SERVER="ubuntu@3.38.98.169"

echo "🔗 SSH 登录到 tw168 服务器..."
echo "💡 提示: 运行 'cat ~/tw168_commands.txt' 查看常用命令"
echo "💡 提示: 运行 '~/check_tw168_status.sh' 查看系统状态"
echo ""

ssh -i "$SSH_KEY" "$SERVER"
