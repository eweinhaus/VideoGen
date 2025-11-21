#!/bin/bash
# Restart worker and prepare for character reference fix testing

set -e  # Exit on error

PROJECT_ROOT="/Users/user/Desktop/Github/VideoGen"
cd "$PROJECT_ROOT"

echo "======================================"
echo "CHARACTER FIX - RESTART & TEST SETUP"
echo "======================================"
echo ""

# Step 1: Find and stop the existing worker
echo "Step 1: Stopping existing worker..."
echo ""

WORKER_PID=$(ps aux | grep '[p]ython.*api_gateway/worker.py' | awk '{print $2}')

if [ -n "$WORKER_PID" ]; then
    echo "✓ Found worker process (PID: $WORKER_PID)"
    kill $WORKER_PID
    echo "✓ Killed worker process"
    
    # Wait for the process to fully stop
    sleep 2
    
    # Verify it's stopped
    if ps -p $WORKER_PID > /dev/null 2>&1; then
        echo "⚠ Worker still running, forcing kill..."
        kill -9 $WORKER_PID
        sleep 1
    fi
    
    echo "✓ Worker stopped successfully"
else
    echo "⚠ No worker process found (may already be stopped)"
fi

echo ""

# Step 2: Verify the fix code is present
echo "Step 2: Verifying fix code is present..."
echo ""

if grep -q "SOLUTION 3 FIX: Always prioritize uploaded character" "$PROJECT_ROOT/project/backend/modules/video_generator/process.py"; then
    echo "✓ SOLUTION 3 FIX code confirmed in process.py"
else
    echo "✗ ERROR: SOLUTION 3 FIX code NOT found!"
    echo "  Please verify the code changes are saved."
    exit 1
fi

if grep -q "SOLUTION 2 CHECKPOINT" "$PROJECT_ROOT/project/backend/modules/video_generator/process.py"; then
    echo "✓ SOLUTION 2 CHECKPOINT logging confirmed in process.py"
else
    echo "⚠ WARNING: SOLUTION 2 CHECKPOINT logging not found"
fi

echo ""

# Step 3: Clear backend logs (optional, creates fresh log file)
echo "Step 3: Preparing log files..."
echo ""

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/project/backend/logs"

# Archive the old log if it exists
if [ -f "$PROJECT_ROOT/project/backend/logs/backend.log" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    mv "$PROJECT_ROOT/project/backend/logs/backend.log" "$PROJECT_ROOT/project/backend/logs/backend_${TIMESTAMP}.log"
    echo "✓ Archived old log to backend_${TIMESTAMP}.log"
fi

# Create new empty log file
touch "$PROJECT_ROOT/project/backend/logs/backend.log"
echo "✓ Created fresh backend.log file"

echo ""

# Step 4: Start the worker
echo "Step 4: Starting worker with fresh code..."
echo ""

cd "$PROJECT_ROOT/project/backend"

# Check if we should run in background or foreground
if [ "$1" == "--foreground" ]; then
    echo "Starting worker in FOREGROUND mode (Ctrl+C to stop)"
    echo "Worker output will be visible here"
    echo ""
    python3 -m api_gateway.worker
else
    # Start in background
    nohup python3 -m api_gateway.worker > "$PROJECT_ROOT/project/backend/logs/worker_output.log" 2>&1 &
    WORKER_PID=$!
    
    echo "✓ Started worker in background (PID: $WORKER_PID)"
    
    # Wait a moment and verify it's running
    sleep 2
    
    if ps -p $WORKER_PID > /dev/null 2>&1; then
        echo "✓ Worker is running successfully"
    else
        echo "✗ ERROR: Worker failed to start"
        echo "  Check logs: tail -f $PROJECT_ROOT/project/backend/logs/worker_output.log"
        exit 1
    fi
fi

echo ""
echo "======================================"
echo "SETUP COMPLETE - READY FOR TESTING"
echo "======================================"
echo ""
echo "Next Steps:"
echo "1. Go to your frontend application"
echo "2. Upload a video with a CHARACTER IMAGE"
echo "3. Wait for video generation to complete"
echo "4. Run this command to check the logs:"
echo "   ./scripts/check_character_fix_logs.sh <JOB_ID>"
echo ""
echo "Or monitor logs in real-time:"
echo "   tail -f $PROJECT_ROOT/project/backend/logs/backend.log | grep 'SOLUTION'"
echo ""
echo "Worker log location:"
echo "   $PROJECT_ROOT/project/backend/logs/backend.log"
echo ""

