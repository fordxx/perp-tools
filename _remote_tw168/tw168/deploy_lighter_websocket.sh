#!/bin/bash
# Deploy Lighter WebSocket updates to remote server

set -e

echo "========================================"
echo "Deploying Lighter WebSocket Updates"
echo "========================================"
echo ""

REMOTE_HOST="ubuntu@3.38.98.169"
REMOTE_DIR="/home/ubuntu/tw168"
LOCAL_SRC="/home/fordxx/perp-tools/src"
SSH_KEY="../../LightsailDefaultKey-ap-northeast-2.pem"

echo "Step 1: Syncing source code to remote server..."
rsync -avz --progress \
  -e "ssh -i $SSH_KEY" \
  "$LOCAL_SRC/" \
  "$REMOTE_HOST:$REMOTE_DIR/src/"

echo ""
echo "Step 2: Rebuilding Docker image on remote server..."
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'EOF'
cd /home/ubuntu/tw168

echo "Building Docker image with WebSocket support..."
docker compose build

echo ""
echo "Restarting Docker container..."
docker compose down
docker compose up -d

echo ""
echo "Waiting for container to start..."
sleep 5

echo ""
echo "Container status:"
docker compose ps

echo ""
echo "Recent logs:"
docker compose logs --tail=50

echo ""
echo "========================================"
echo "✅ Deployment completed!"
echo "========================================"
EOF

echo ""
echo "Deployment finished. Check logs with:"
echo "  ssh -i $SSH_KEY ubuntu@3.38.98.169 'cd /home/ubuntu/tw168 && docker compose logs -f'"
echo ""
