#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-ubuntu@3.38.98.169}"
REMOTE_KEY="${REMOTE_KEY:-/home/fordxx/lightsail.pem}"
REMOTE_REPO="${REMOTE_REPO:-/home/ubuntu/perp-tools}"
REMOTE_APP="${REMOTE_APP:-/home/ubuntu/tw168}"
CONTAINER_NAME="${CONTAINER_NAME:-tw168-tv-okx-1}"

SSH="ssh -i ${REMOTE_KEY} ${REMOTE_HOST}"

echo "==> Pull latest code on remote"
${SSH} "cd ${REMOTE_REPO} && git pull --ff-only"

echo "==> Rebuild and restart container"
${SSH} "cd ${REMOTE_APP} && docker compose up -d --build"

echo "==> Container status"
${SSH} "docker ps --format 'table {{.Names}}\t{{.Status}}' | sed -n '1,5p'"

echo "==> Recent logs"
${SSH} "docker logs --since 2m ${CONTAINER_NAME} | tail -n 80"

echo "Done."
