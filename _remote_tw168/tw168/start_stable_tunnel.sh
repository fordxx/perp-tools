#!/bin/bash

# Kill any existing tunnel on port 8002 to avoid conflicts
pkill -f "ssh -i .* -L 8002:localhost:8000"

echo "Starting stable SSH tunnel manager..."

while true; do
    echo "[$(date)] Connecting SSH tunnel..."
    # -o ServerAliveInterval=60: Send keepalive every 60s
    # -o ServerAliveCountMax=3: Disconnect if 3 keepalives fail (3 mins timeout)
    # -o ExitOnForwardFailure=yes: Exit if port binding fails so we can retry
    ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem \
        -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=60 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        -N -L 8002:localhost:8000 \
        ubuntu@3.38.98.169
    
    EXIT_CODE=$?
    echo "[$(date)] SSH tunnel exited with code $EXIT_CODE. Restarting in 5 seconds..."
    sleep 5
done
