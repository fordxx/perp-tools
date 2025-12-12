#!/bin/bash
# PerpBot V2 Log Viewer Script

SERVICE=${1:-perpbot}

echo "📜 Viewing logs for: $SERVICE"
echo "Press Ctrl+C to exit"
echo ""

docker-compose logs -f --tail=100 $SERVICE
