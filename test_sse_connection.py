#!/usr/bin/env python3
"""
Test SSE connection for a job.

Usage:
    python test_sse_connection.py JOB_ID AUTH_TOKEN

Example:
    python test_sse_connection.py 45f5eeb6-387a-48e3-bf70-654191bd395d "eyJ..."
"""

import sys
import asyncio
import aiohttp
import json

async def test_sse_connection(job_id: str, auth_token: str, base_url: str = "http://localhost:8000"):
    """Test SSE connection for a job."""
    url = f"{base_url}/api/v1/jobs/{job_id}/stream?token={auth_token}"

    print(f"🔗 Connecting to SSE endpoint...")
    print(f"   Job ID: {job_id}")
    print(f"   URL: {url[:100]}...")
    print(f"   Press Ctrl+C to stop\n")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"❌ Connection failed with status {response.status}")
                    text = await response.text()
                    print(f"   Response: {text}")
                    return

                print(f"✅ Connected! Listening for events...\n")

                event_count = 0
                async for line in response.content:
                    line_str = line.decode('utf-8').strip()

                    if not line_str:
                        continue

                    # Parse SSE format
                    if line_str.startswith('event:'):
                        event_type = line_str[7:].strip()
                    elif line_str.startswith('data:'):
                        event_count += 1
                        data_str = line_str[6:].strip()
                        try:
                            data = json.loads(data_str)
                            print(f"[{event_count}] Event: {event_type}")
                            print(f"    Data: {json.dumps(data, indent=6)}")
                            print()

                            # Check for completion
                            if event_type == 'completed':
                                print("🎉 Job completed!")
                                if 'video_url' in data:
                                    print(f"   Video: {data['video_url']}")
                                break
                        except json.JSONDecodeError:
                            print(f"[{event_count}] Event: {event_type}")
                            print(f"    Data (raw): {data_str}")
                            print()

    except KeyboardInterrupt:
        print("\n\n⚠️  Connection closed by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")

async def check_job_status(job_id: str, auth_token: str, base_url: str = "http://localhost:8000"):
    """Check job status via REST API."""
    url = f"{base_url}/api/v1/jobs/{job_id}"
    headers = {"Authorization": f"Bearer {auth_token}"}

    print(f"\n📊 Checking job status via REST API...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    print(f"   ❌ Failed with status {response.status}")
                    return

                data = await response.json()
                print(f"   ✅ Job found!")
                print(f"      Status: {data.get('status')}")
                print(f"      Progress: {data.get('progress')}%")
                print(f"      Stage: {data.get('currentStage')}")
                print(f"      Video URL: {data.get('videoUrl', 'N/A')}")
                print(f"      Total Cost: ${data.get('totalCost', 0):.2f}")
                print()
    except Exception as e:
        print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_sse_connection.py JOB_ID AUTH_TOKEN [BASE_URL]")
        print()
        print("Example:")
        print('  python test_sse_connection.py 45f5eeb6-387a-48e3-bf70-654191bd395d "eyJ..." http://localhost:8000')
        sys.exit(1)

    job_id = sys.argv[1]
    auth_token = sys.argv[2]
    base_url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8000"

    # First check job status
    asyncio.run(check_job_status(job_id, auth_token, base_url))

    # Then test SSE connection
    asyncio.run(test_sse_connection(job_id, auth_token, base_url))
