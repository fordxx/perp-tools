#!/bin/bash
# 本地快速检查 tw168 服务器状态

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ssh_key_helper.sh
source "${SCRIPT_DIR}/scripts/ssh_key_helper.sh"

SSH_KEY="${SSH_KEY:-../../LightsailDefaultKey-ap-northeast-2.pem}"
SERVER="${SERVER:-ubuntu@3.38.98.169}"
KEY_TO_USE="$(ssh_key_decrypt_to_temp_if_needed "$SSH_KEY")"

echo "🔗 连接到 tw168 服务器..."
ssh -i "$KEY_TO_USE" "$SERVER" "~/check_tw168_status.sh"
