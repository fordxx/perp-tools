#!/bin/bash

# SSH Tunnel Maintenance Script
# Keeps the tunnel to the remote trading service alive

KEY_PATH="../../LightsailDefaultKey-ap-northeast-2.pem"
REMOTE_HOST="ubuntu@3.38.98.169"
LOCAL_PORT=8002
REMOTE_PORT=8000

echo "🛡️  Starting SSH Tunnel Monitor..."
echo "   Local Port: $LOCAL_PORT -> Remote Port: $REMOTE_PORT"

while true; do
    # Check if the tunnel is active by checking if the port is listening
    if ! ss -tuln | grep -q ":$LOCAL_PORT "; then
        echo "⚠️  Tunnel down. Reconnecting..."
        
        # Kill any stale ssh processes for this specific tunnel just in case
        pkill -f "ssh .* -L $LOCAL_PORT:127.0.0.1:$REMOTE_PORT"
        
        # Start the tunnel with keepalive options
        # -o ServerAliveInterval=60: Send a keepalive packet every 60 seconds
        # -o ServerAliveCountMax=3: Disconnect if 3 keepalives fail
        # -o ExitOnForwardFailure=yes: Exit if port forwarding fails (so we can retry)
        ssh -i "$KEY_PATH" \
            -o StrictHostKeyChecking=no \
            -o ServerAliveInterval=60 \
            -o ServerAliveCountMax=3 \
            -o ExitOnForwardFailure=yes \
            -f -N -L $LOCAL_PORT:127.0.0.1:$REMOTE_PORT \
            $REMOTE_HOST
            
        if [ $? -eq 0 ]; then
            echo "✅ Tunnel re-established."
        else
            echo "❌ Failed to establish tunnel. Retrying in 10s..."
            sleep 10
        fi
    fi
    
    # Check every 30 seconds
    sleep 30
done
