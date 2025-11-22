#!/bin/bash
# Start the worker process for local development

cd "$(dirname "$0")/project/backend"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start the worker
echo "Starting worker process..."
python -m api_gateway.worker

