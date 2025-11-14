#!/bin/bash
# Monitor backend logs with filtering

LOG_FILE="project/backend/logs/app.log"

echo "Monitoring backend logs..."
echo "Press Ctrl+C to stop"
echo ""

# Show recent logs first
echo "=== Recent Logs (last 20 lines) ==="
tail -20 "$LOG_FILE" | python3 -m json.tool 2>/dev/null || tail -20 "$LOG_FILE"
echo ""
echo "=== Live Logs (filtered for important events) ==="
echo ""

# Monitor with filtering
tail -f "$LOG_FILE" | while read line; do
    # Parse JSON and highlight important events
    if echo "$line" | grep -qE '"level":"(ERROR|WARNING)"'; then
        echo -e "\033[31m$line\033[0m"  # Red for errors/warnings
    elif echo "$line" | grep -qE '"message":"(Processing job|Progress updated|Job enqueued|Job completed)"'; then
        echo -e "\033[32m$line\033[0m"  # Green for job events
    elif echo "$line" | grep -qE '"message":"(SSE stream|stage_update)"'; then
        echo -e "\033[33m$line\033[0m"  # Yellow for SSE/stage updates
    else
        echo "$line"
    fi
done

