"""
Test audio upload via API Gateway.
"""

import requests
import json
import sys
from pathlib import Path

# Path to test audio file
audio_file_path = Path(__file__).parent / "modules" / "audio_parser" / "tests" / "Test_audio_file.mp3"

if not audio_file_path.exists():
    print(f"❌ ERROR: Audio file not found at {audio_file_path}")
    sys.exit(1)

print("=" * 80)
print("API Gateway Upload Test")
print("=" * 80)

# Test upload endpoint
url = "http://localhost:8000/api/v1/upload-audio"

# Note: This requires authentication token
# For testing, you may need to get a token first or use test credentials
print(f"\n📤 Uploading audio file: {audio_file_path.name} ({audio_file_path.stat().st_size / 1024 / 1024:.2f} MB)")

try:
    with open(audio_file_path, 'rb') as f:
        files = {
            'audio_file': (audio_file_path.name, f, 'audio/mpeg')
        }
        data = {
            'user_prompt': 'Test audio parser validation'
        }
        
        # Note: Add Authorization header if needed
        headers = {}
        # headers = {'Authorization': f'Bearer YOUR_TOKEN_HERE'}
        
        response = requests.post(url, files=files, data=data, headers=headers, timeout=300)
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Upload successful!")
            print(f"   Job ID: {result.get('job_id')}")
            print(f"   Status: {result.get('status')}")
            print(f"\n📊 Full response:")
            print(json.dumps(result, indent=2))
        elif response.status_code == 401:
            print("⚠️  Authentication required")
            print("   Please provide a valid JWT token in the Authorization header")
        else:
            print(f"❌ Upload failed: {response.status_code}")
            print(f"   Response: {response.text}")
            
except requests.exceptions.ConnectionError:
    print("❌ ERROR: Could not connect to API Gateway")
    print("   Make sure API Gateway is running on http://localhost:8000")
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}: {str(e)}")

print("\n" + "=" * 80)

