#!/bin/bash
# 本地快速检查 tw168 服务器状态

SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"
SERVER="ubuntu@3.38.98.169"

echo "🔗 连接到 tw168 服务器..."
ssh -i "$SSH_KEY" "$SERVER" "~/check_tw168_status.sh"
