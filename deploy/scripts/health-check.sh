#!/bin/bash
# PerpBot V2 Health Check Script

echo "========================================="
echo " PerpBot V2 - Health Check"
echo "========================================="
echo ""

# Check if services are running
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "🏥 Health Checks:"

# Check PerpBot health
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "  ✅ PerpBot:      HEALTHY"
else
    echo "  ❌ PerpBot:      DOWN"
fi

# Check Prometheus
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "  ✅ Prometheus:   HEALTHY"
else
    echo "  ❌ Prometheus:   DOWN"
fi

# Check Grafana
if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
    echo "  ✅ Grafana:      HEALTHY"
else
    echo "  ❌ Grafana:      DOWN"
fi

# Check Redis
if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo "  ✅ Redis:        HEALTHY"
else
    echo "  ❌ Redis:        DOWN"
fi

echo ""
echo "📈 Resource Usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo ""
