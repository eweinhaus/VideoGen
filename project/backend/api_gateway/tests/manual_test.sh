#!/bin/bash
# Manual testing script for API Gateway endpoints
# Usage: ./manual_test.sh [JWT_TOKEN]

set -e

API_URL="http://localhost:8000/api/v1"
JWT_TOKEN="${1:-YOUR_JWT_TOKEN_HERE}"

if [ "$JWT_TOKEN" = "YOUR_JWT_TOKEN_HERE" ]; then
    echo "❌ Error: Please provide JWT token as argument"
    echo "Usage: ./manual_test.sh YOUR_JWT_TOKEN"
    exit 1
fi

AUTH_HEADER="Authorization: Bearer $JWT_TOKEN"

echo "🧪 Testing API Gateway Endpoints"
echo "=================================="
echo ""

# Test 1: Health Check
echo "1. Testing Health Endpoint..."
response=$(curl -s -w "\n%{http_code}" "$API_URL/health")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
if [ "$http_code" = "200" ]; then
    echo "✅ Health check passed"
    echo "$body" | jq '.' 2>/dev/null || echo "$body"
else
    echo "❌ Health check failed (HTTP $http_code)"
    echo "$body"
fi
echo ""

# Test 2: Upload Audio (requires test file)
echo "2. Testing Upload Endpoint..."
if [ ! -f "test_audio.mp3" ]; then
    echo "⚠️  Skipping: test_audio.mp3 not found"
    echo "   Create test file: ffmpeg -f lavfi -i 'sine=frequency=440:duration=30' -acodec libmp3lame test_audio.mp3"
else
    response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/upload-audio" \
        -H "$AUTH_HEADER" \
        -F "audio_file=@test_audio.mp3" \
        -F "user_prompt=Create a cyberpunk music video with neon lights and futuristic cityscapes")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    if [ "$http_code" = "201" ]; then
        echo "✅ Upload successful"
        JOB_ID=$(echo "$body" | jq -r '.job_id' 2>/dev/null)
        echo "   Job ID: $JOB_ID"
        echo "$body" | jq '.' 2>/dev/null || echo "$body"
    else
        echo "❌ Upload failed (HTTP $http_code)"
        echo "$body"
    fi
fi
echo ""

# Test 3: Job Status (if job created)
if [ -n "$JOB_ID" ]; then
    echo "3. Testing Job Status Endpoint..."
    response=$(curl -s -w "\n%{http_code}" "$API_URL/jobs/$JOB_ID" \
        -H "$AUTH_HEADER")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    if [ "$http_code" = "200" ]; then
        echo "✅ Job status retrieved"
        echo "$body" | jq '.' 2>/dev/null || echo "$body"
    else
        echo "❌ Job status failed (HTTP $http_code)"
        echo "$body"
    fi
    echo ""
fi

# Test 4: Job List
echo "4. Testing Job List Endpoint..."
response=$(curl -s -w "\n%{http_code}" "$API_URL/jobs?limit=10&offset=0" \
    -H "$AUTH_HEADER")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
if [ "$http_code" = "200" ]; then
    echo "✅ Job list retrieved"
    echo "$body" | jq '.' 2>/dev/null || echo "$body"
else
    echo "❌ Job list failed (HTTP $http_code)"
    echo "$body"
fi
echo ""

# Test 5: SSE Stream (if job created)
if [ -n "$JOB_ID" ]; then
    echo "5. Testing SSE Stream Endpoint..."
    echo "   (This will stream events for 10 seconds, then cancel)"
    timeout 10 curl -N -H "$AUTH_HEADER" \
        "$API_URL/jobs/$JOB_ID/stream" 2>/dev/null || true
    echo ""
    echo "✅ SSE stream test completed"
    echo ""
fi

echo "✅ Manual testing complete!"
echo ""
echo "To test SSE stream manually:"
echo "  curl -N -H '$AUTH_HEADER' $API_URL/jobs/$JOB_ID/stream"

