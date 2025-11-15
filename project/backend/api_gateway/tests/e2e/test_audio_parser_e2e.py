"""
End-to-end tests for Audio Parser via API Gateway.

These tests require:
- API Gateway running on localhost:8000
- Worker process running
- Redis available
- Supabase configured (or mocked)
"""
import pytest
import httpx
import asyncio
from uuid import uuid4


@pytest.fixture
def api_base_url():
    """API base URL for testing."""
    return "http://localhost:8000/api/v1"


@pytest.fixture
def test_token():
    """Test JWT token (mock or real)."""
    # In real tests, generate valid JWT token
    return "test_token_placeholder"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audio_upload_and_processing_e2e(api_base_url, test_token):
    """
    Test full audio upload → processing → results flow.
    
    Note: This test requires:
    - API Gateway running
    - Worker process running
    - Real or mocked Supabase/Redis
    """
    pytest.skip("Requires running services - run manually or in CI")
    
    async with httpx.AsyncClient(base_url=api_base_url, timeout=180.0) as client:
        headers = {"Authorization": f"Bearer {test_token}"}
        
        # 1. Upload audio file
        # Note: Requires actual audio file in tests/fixtures/
        audio_file_path = "tests/fixtures/test_audio.mp3"
        
        try:
            with open(audio_file_path, "rb") as f:
                files = {"audio_file": ("test.mp3", f, "audio/mpeg")}
                data = {"user_prompt": "Create a cyberpunk music video"}
                
                response = await client.post(
                    "/upload-audio",
                    headers=headers,
                    files=files,
                    data=data
                )
        except FileNotFoundError:
            pytest.skip(f"Test audio file not found: {audio_file_path}")
        
        assert response.status_code == 201, f"Upload failed: {response.text}"
        job_data = response.json()
        job_id = job_data["job_id"]
        
        # 2. Poll job status until complete
        max_wait = 120  # 2 minutes
        start_time = asyncio.get_event_loop().time()
        
        while True:
            response = await client.get(
                f"/jobs/{job_id}",
                headers=headers
            )
            assert response.status_code == 200
            
            job = response.json()
            status = job["status"]
            
            if status == "completed":
                break
            elif status == "failed":
                error_msg = job.get("error", "Unknown error")
                pytest.fail(f"Job failed: {error_msg}")
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait:
                pytest.fail(f"Job processing timeout after {elapsed}s")
            
            await asyncio.sleep(2)
        
        # 3. Verify audio_data in job
        assert "audio_data" in job, "audio_data not found in job response"
        audio_data = job["audio_data"]
        
        # Verify structure
        assert "bpm" in audio_data
        assert 60 <= audio_data["bpm"] <= 200
        
        assert "beat_timestamps" in audio_data
        assert len(audio_data["beat_timestamps"]) > 0
        
        assert "song_structure" in audio_data
        assert len(audio_data["song_structure"]) > 0
        
        assert "clip_boundaries" in audio_data
        assert len(audio_data["clip_boundaries"]) >= 1
        
        assert "mood" in audio_data
        assert audio_data["mood"]["primary"] in ['energetic', 'calm', 'dark', 'bright']
        
        assert "lyrics" in audio_data
        assert isinstance(audio_data["lyrics"], list)
        
        assert "metadata" in audio_data
        assert "processing_time" in audio_data["metadata"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audio_parser_progress_updates(api_base_url, test_token):
    """
    Test SSE progress updates during audio processing.
    
    Note: Requires SSE endpoint and EventSource support.
    """
    pytest.skip("Requires SSE implementation and running services")
    
    # This would test the SSE stream endpoint
    # GET /api/v1/jobs/{job_id}/stream
    # Verify progress events are received
    pass


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audio_parser_error_handling(api_base_url, test_token):
    """Test error handling for invalid audio files."""
    pytest.skip("Requires running services")
    
    async with httpx.AsyncClient(base_url=api_base_url, timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {test_token}"}
        
        # Upload invalid file
        files = {"audio_file": ("invalid.txt", b"not audio data", "text/plain")}
        data = {"user_prompt": "Test"}
        
        response = await client.post(
            "/upload-audio",
            headers=headers,
            files=files,
            data=data
        )
        
        # Should return 400 or 422 (validation error)
        assert response.status_code in [400, 422]
        
        error_data = response.json()
        assert "error" in error_data or "detail" in error_data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audio_parser_cache_hit(api_base_url, test_token):
    """
    Test that caching works (same file processed twice).
    
    Note: Requires running services and Redis.
    """
    pytest.skip("Requires running services and Redis")
    
    # Upload same file twice
    # First upload: cache miss, full processing
    # Second upload: cache hit, fast return
    # Verify processing_time is much shorter on second upload
    pass

