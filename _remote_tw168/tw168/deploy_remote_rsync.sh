#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-ubuntu@3.38.98.169}"
REMOTE_KEY="${REMOTE_KEY:-/home/fordxx/LightsailDefaultKey-ap-northeast-2.pem}"
REMOTE_APP="${REMOTE_APP:-/home/ubuntu/perp-tools/_remote_tw168/tw168}"
REMOTE_BACKUP_DIR="${REMOTE_BACKUP_DIR:-/home/ubuntu/archive}"
CONTAINER_NAME="${CONTAINER_NAME:-tw168-tv-okx-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ssh_key_helper.sh
source "${SCRIPT_DIR}/scripts/ssh_key_helper.sh"

KEY_TO_USE="$(ssh_key_decrypt_to_temp_if_needed "$REMOTE_KEY")"
SSH="ssh -i ${KEY_TO_USE} ${REMOTE_HOST}"

echo "==> Backup remote"
${SSH} "mkdir -p ${REMOTE_BACKUP_DIR} && ts=\$(date +%Y%m%d_%H%M%S) && tar -czf ${REMOTE_BACKUP_DIR}/tw168_backup_\${ts}.tgz -C $(dirname ${REMOTE_APP}) $(basename ${REMOTE_APP}) && echo \"backup:${REMOTE_BACKUP_DIR}/tw168_backup_\${ts}.tgz\""

echo "==> Rsync to remote (code only)"
rsync -az --delete \
  --exclude '.venv' \
  --exclude '.env' \
  --exclude '.env.backup*' \
  --exclude 'logs' \
  --exclude '__pycache__' \
  --exclude '*.log' \
  --exclude 'image.png' \
  -e "ssh -i ${KEY_TO_USE}" \
  "$(pwd)/" \
  "${REMOTE_HOST}:${REMOTE_APP}/"

echo "==> Restart container"
${SSH} "cd ${REMOTE_APP} && docker compose up -d --build"

echo "==> Container status"
${SSH} "docker ps --format 'table {{.Names}}\t{{.Status}}' | sed -n '1,5p'"

echo "==> Recent logs"
${SSH} "docker logs --since 2m ${CONTAINER_NAME} | tail -n 80"

echo "Done."
