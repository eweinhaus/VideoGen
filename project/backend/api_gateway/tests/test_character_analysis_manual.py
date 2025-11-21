"""
Manual test script for character analysis feature.

Run this script to test the character analysis flow end-to-end.
Requires:
- Backend server running on localhost:8000
- Redis running
- Supabase configured
- Valid JWT token

Usage:
    python -m api_gateway.tests.test_character_analysis_manual
"""

import asyncio
import httpx
import json
import pytest
from uuid import UUID


@pytest.mark.skip(reason="Manual test - requires running backend server and valid JWT token")
async def test_character_analysis_flow():
    """Test the complete character analysis flow.
    
    This is a manual test that requires:
    - Backend server running on localhost:8000
    - Valid JWT token
    - Redis and Supabase configured
    
    To run: Set JWT token and ensure server is running, then remove @pytest.mark.skip
    """
    base_url = "http://localhost:8000"
    
    # You'll need to set a valid JWT token here
    token = "YOUR_JWT_TOKEN_HERE"
    if token == "YOUR_JWT_TOKEN_HERE":
        pytest.skip("JWT token not set")
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("🧪 Testing Character Analysis Flow")
        print("=" * 50)
        
        # 1. Start analysis
        print("\n1️⃣ Starting character analysis...")
        response = await client.post(
            f"{base_url}/api/v1/upload/character/analyze",
            json={
                "image_url": "https://example.com/test-character.jpg",
                "analysis_version": "v1"
            },
            headers=headers
        )
        
        if response.status_code != 202:
            print(f"❌ Failed to start analysis: {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        data = response.json()
        job_id = data["job_id"]
        print(f"✅ Analysis job created: {job_id}")
        
        # 2. Poll for results
        print("\n2️⃣ Polling for analysis results...")
        max_attempts = 30
        for attempt in range(max_attempts):
            await asyncio.sleep(2)
            
            response = await client.get(
                f"{base_url}/api/v1/upload/character/analyze/{job_id}",
                headers=headers
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to get analysis: {response.status_code}")
                print(f"Response: {response.text}")
                return False
            
            data = response.json()
            status = data.get("status")
            
            if status == "completed":
                print("✅ Analysis completed!")
                print(f"\n📊 Analysis Results:")
                print(json.dumps(data, indent=2))
                return True
            elif status == "failed":
                print(f"❌ Analysis failed: {data.get('error', 'Unknown error')}")
                return False
            else:
                print(f"⏳ Status: {status} (attempt {attempt + 1}/{max_attempts})")
        
        print("❌ Analysis timed out")
        return False


if __name__ == "__main__":
    print("⚠️  Note: Set a valid JWT token in the script before running")
    print("⚠️  Also ensure backend server is running on localhost:8000\n")
    
    result = asyncio.run(test_character_analysis_flow())
    exit(0 if result else 1)

