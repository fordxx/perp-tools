#!/bin/bash
# Deploy tw168 updates to remote server
set -e

REMOTE_HOST="ubuntu@3.38.98.169"
REMOTE_DIR="/home/ubuntu/tw168"
SSH_KEY="/home/fordxx/lightsail.pem"
LOCAL_DIR="/home/fordxx/perp-tools/_remote_tw168/tw168"

echo "========================================="
echo "TW168 Deployment Script"
echo "========================================="
echo "Remote: ${REMOTE_HOST}:${REMOTE_DIR}"
echo "Local: ${LOCAL_DIR}"
echo ""

# Check if service is running
echo "1. Checking if tw168 service is running..."
if ssh -i "$SSH_KEY" "$REMOTE_HOST" "systemctl is-active --quiet tw168.service 2>/dev/null || supervisorctl status tw168 2>/dev/null | grep -q RUNNING"; then
    echo "   Service is running, will restart after deployment"
    SERVICE_RUNNING=true
else
    echo "   Service is not running"
    SERVICE_RUNNING=false
fi

# Backup remote .env file
echo ""
echo "2. Backing up remote .env file..."
ssh -i "$SSH_KEY" "$REMOTE_HOST" "cp ${REMOTE_DIR}/.env ${REMOTE_DIR}/.env.backup_$(date +%Y%m%d_%H%M%S)"

# Stop service if running
if [ "$SERVICE_RUNNING" = true ]; then
    echo ""
    echo "3. Stopping tw168 service..."
    ssh -i "$SSH_KEY" "$REMOTE_HOST" "supervisorctl stop tw168 2>/dev/null || systemctl stop tw168.service 2>/dev/null || true"
    sleep 2
fi

# Create backup of remote app directory
echo ""
echo "4. Creating backup of remote app directory..."
ssh -i "$SSH_KEY" "$REMOTE_HOST" "cp -r ${REMOTE_DIR}/app ${REMOTE_DIR}/app.backup_$(date +%Y%m%d_%H%M%S)"

# Sync files to remote
echo ""
echo "5. Syncing files to remote server..."
rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='logs/*' --exclude='.env' \
    -e "ssh -i $SSH_KEY" \
    "${LOCAL_DIR}/app/" \
    "${REMOTE_HOST}:${REMOTE_DIR}/app/"

echo ""
echo "6. Syncing scripts directory..."
rsync -avz \
    -e "ssh -i $SSH_KEY" \
    "${LOCAL_DIR}/scripts/" \
    "${REMOTE_HOST}:${REMOTE_DIR}/scripts/"

echo ""
echo "7. Syncing documentation..."
rsync -avz \
    -e "ssh -i $SSH_KEY" \
    "${LOCAL_DIR}/BUG_FIXES.md" \
    "${LOCAL_DIR}/.env.example" \
    "${REMOTE_HOST}:${REMOTE_DIR}/"

# Update .env with new configuration options if needed
echo ""
echo "8. Checking for new configuration options..."
ssh -i "$SSH_KEY" "$REMOTE_HOST" << 'ENDSSH'
cd /home/ubuntu/tw168
if ! grep -q "BACKUP_SL_ENABLED" .env; then
    echo "" >> .env
    echo "# Backup stop-loss strategy (try limit order if algo order fails)" >> .env
    echo "BACKUP_SL_ENABLED=false" >> .env
    echo "   Added BACKUP_SL_ENABLED to .env"
fi
if ! grep -q "MIN_STOP_DISTANCE_BPS" .env; then
    echo "MIN_STOP_DISTANCE_BPS=0.0" >> .env
    echo "   Added MIN_STOP_DISTANCE_BPS to .env"
fi
ENDSSH

# Install any new dependencies
echo ""
echo "9. Installing dependencies..."
ssh -i "$SSH_KEY" "$REMOTE_HOST" "cd ${REMOTE_DIR} && source .venv/bin/activate && pip install -q -r requirements.txt"

# Make scripts executable
echo ""
echo "10. Making scripts executable..."
ssh -i "$SSH_KEY" "$REMOTE_HOST" "chmod +x ${REMOTE_DIR}/scripts/*.sh ${REMOTE_DIR}/scripts/*.py"

# Restart service if it was running
if [ "$SERVICE_RUNNING" = true ]; then
    echo ""
    echo "11. Starting tw168 service..."
    ssh -i "$SSH_KEY" "$REMOTE_HOST" "supervisorctl start tw168 2>/dev/null || systemctl start tw168.service 2>/dev/null || true"
    sleep 3

    echo ""
    echo "12. Checking service status..."
    ssh -i "$SSH_KEY" "$REMOTE_HOST" "supervisorctl status tw168 2>/dev/null || systemctl status tw168.service --no-pager -l 2>/dev/null || true"
fi

echo ""
echo "========================================="
echo "Deployment Summary"
echo "========================================="
echo "✅ Files synced successfully"
echo "✅ Configuration updated"
echo "✅ Dependencies installed"

if [ "$SERVICE_RUNNING" = true ]; then
    echo "✅ Service restarted"
fi

echo ""
echo "📋 New Features Deployed:"
echo "   • Stop-loss failure rate monitoring (app/metrics.py)"
echo "   • API rate limiting protection (app/rate_limiter.py)"
echo "   • Backup stop-loss strategy (BACKUP_SL_ENABLED)"
echo "   • Position health check script (scripts/check_positions.py)"
echo ""
echo "📖 Documentation: ${REMOTE_DIR}/BUG_FIXES.md"
echo "📊 Check metrics: curl http://localhost:8000/metrics"
echo "🔍 Health check: python ${REMOTE_DIR}/scripts/check_positions.py"
echo ""
echo "========================================="
echo "Deployment completed at $(date)"
echo "========================================="
