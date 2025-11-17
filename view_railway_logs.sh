#!/bin/bash
# View Railway logs for a specific job

JOB_ID="${1:-489ddeaa-557a-4eee-b7ab-4877c437e7e0}"
SERVICE="${2:-}"

echo "Viewing Railway logs for job: $JOB_ID"
echo ""

if [ -z "$SERVICE" ]; then
    echo "Usage: ./view_railway_logs.sh [JOB_ID] [SERVICE_NAME]"
    echo ""
    echo "First, select a service:"
    echo "  railway service"
    echo ""
    echo "Then view logs:"
    echo "  railway logs --tail 200 | grep '$JOB_ID'"
    echo ""
    echo "Or specify service directly:"
    echo "  railway logs --service <SERVICE_NAME> --tail 200 | grep '$JOB_ID'"
    exit 1
fi

echo "Fetching logs from service: $SERVICE"
railway logs --service "$SERVICE" --tail 500 | grep -i "$JOB_ID\|video.*generation\|clip\|video_generation" --color=always

