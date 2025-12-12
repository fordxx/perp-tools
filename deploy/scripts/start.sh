#!/bin/bash
# PerpBot V2 Docker Start Script

set -e

echo "========================================="
echo " PerpBot V2 - Starting Docker Services"
echo "========================================="
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "Please create .env from .env.example:"
    echo "  cp .env.example .env"
    echo "  nano .env  # Edit with your credentials"
    exit 1
fi

# Check if config.yaml exists
if [ ! -f config.yaml ]; then
    echo "⚠️  Warning: config.yaml not found"
    echo "Using default configuration"
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs data deploy/prometheus/alerts

# Pull latest images
echo "🐳 Pulling Docker images..."
docker-compose pull

# Build PerpBot image
echo "🔨 Building PerpBot image..."
docker-compose build

# Start services
echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to start..."
sleep 10

# Check service status
echo ""
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "========================================="
echo " ✅ PerpBot V2 Started Successfully"
echo "========================================="
echo ""
echo "Access points:"
echo "  📊 Web Dashboard:  http://localhost:8000"
echo "  📈 Grafana:        http://localhost:3000 (admin/admin)"
echo "  🔍 Prometheus:     http://localhost:9090"
echo "  🔔 Alertmanager:   http://localhost:9093"
echo ""
echo "Useful commands:"
echo "  docker-compose logs -f perpbot     # View logs"
echo "  docker-compose stop                # Stop services"
echo "  docker-compose restart perpbot     # Restart PerpBot"
echo "  ./deploy/scripts/stop.sh           # Stop all services"
echo ""
