#!/bin/bash
# PerpBot V2 Docker Stop Script

set -e

echo "========================================="
echo " PerpBot V2 - Stopping Docker Services"
echo "========================================="
echo ""

# Stop services
echo "🛑 Stopping services..."
docker-compose down

echo ""
echo "✅ All services stopped"
echo ""
echo "To start again, run:"
echo "  ./deploy/scripts/start.sh"
echo ""
