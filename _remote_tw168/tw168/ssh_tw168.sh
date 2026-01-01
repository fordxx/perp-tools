#!/bin/bash
# 快速 SSH 登录到 tw168 服务器

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ssh_key_helper.sh
source "${SCRIPT_DIR}/scripts/ssh_key_helper.sh"

SSH_KEY="${SSH_KEY:-../../LightsailDefaultKey-ap-northeast-2.pem}"
SERVER="${SERVER:-ubuntu@3.38.98.169}"

echo "🔗 SSH 登录到 tw168 服务器..."
echo "💡 提示: 运行 'cat ~/tw168_commands.txt' 查看常用命令"
echo "💡 提示: 运行 '~/check_tw168_status.sh' 查看系统状态"
echo ""

KEY_TO_USE="$(ssh_key_decrypt_to_temp_if_needed "$SSH_KEY")"
ssh -i "$KEY_TO_USE" "$SERVER"
