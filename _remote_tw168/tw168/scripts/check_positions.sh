#!/bin/bash
# Position health check wrapper script for cron scheduling
#
# Usage:
#   ./check_positions.sh [--alert-webhook URL]
#
# Cron example (check every hour):
#   0 * * * * /path/to/check_positions.sh --alert-webhook https://your-webhook-url >> /var/log/position_health.log 2>&1

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment if exists
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
elif [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Run health check
cd "$PROJECT_DIR"
python3 "$SCRIPT_DIR/check_positions.py" "$@"
