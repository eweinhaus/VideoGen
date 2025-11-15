#!/bin/bash

# Start the worker process for VideoGen pipeline
# This script starts the worker in the foreground with detailed logging

set -e

# Change to backend directory
cd "$(dirname "$0")/.."

echo "========================================"
echo "Starting VideoGen Worker Process"
echo "========================================"
echo ""
echo "Worker Configuration:"
echo "  - Max concurrent jobs: 3"
echo "  - Queue: videogen:queue"
echo "  - Redis: localhost:6379"
echo "  - Logs: logs/app.log"
echo ""
echo "========================================"
echo ""

# Activate virtual environment if it exists
if [ -d "../../venv/bin" ]; then
    echo "Activating virtual environment..."
    source ../../venv/bin/activate
fi

# Set Python path to include backend directory
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Start worker
echo "Starting worker..."
echo ""
python -m api_gateway.worker

