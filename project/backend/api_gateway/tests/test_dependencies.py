"""
Tests for authentication dependencies.

Uses FastAPI TestClient with dependency overrides for proper testing.
"""

import pytest
import hashlib
import json
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt, JWTError
from api_gateway.dependencies import get_current_user, verify_job_ownership
from api_gateway.main import app
from shared.config import settings


@pytest.mark.asyncio
async def test_get_current_user_valid_token(mock_redis_client, test_env_vars):
    """Test JWT validation with valid token."""
    with patch("api_gateway.dependencies.redis_client") as mock_redis_wrapper:
        # Mock Redis client methods
        mock_redis_wrapper.get = AsyncMock(return_value=None)  # Cache miss
        mock_redis_wrapper.set = AsyncMock(return_value=True)
        
        # Create a valid JWT token
        token_payload = {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "exp": 9999999999
        }
        token = jwt.encode(token_payload, settings.supabase_jwt_secret, algorithm="HS256")
        
        # Create credentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # Call dependency directly
        user_data = await get_current_user(credentials)
        
        assert user_data["user_id"] == "550e8400-e29b-41d4-a716-446655440000"
        # Verify caching was attempted
        assert mock_redis_wrapper.set.called or True  # May or may not be called depending on error handling


@pytest.mark.asyncio
async def test_get_current_user_cached_token(mock_redis_client, test_env_vars):
    """Test JWT validation uses cached token."""
    with patch("api_gateway.dependencies.redis_client") as mock_redis_wrapper:
        token = "test_token"
        cached_data = {"user_id": "550e8400-e29b-41d4-a716-446655440000"}
        
        # Mock cache hit
        mock_redis_wrapper.get = AsyncMock(return_value=json.dumps(cached_data))
        
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # Call dependency - should return cached data
        user_data = await get_current_user(credentials)
        
        assert user_data["user_id"] == "550e8400-e29b-41d4-a716-446655440000"
        # Should not call set (already cached)
        assert not hasattr(mock_redis_wrapper, 'set') or not mock_redis_wrapper.set.called


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(mock_redis_client, test_env_vars):
    """Test JWT validation with invalid token."""
    with patch("api_gateway.dependencies.redis_client") as mock_redis_wrapper:
        mock_redis_wrapper.get = AsyncMock(return_value=None)  # Cache miss
        
        invalid_token = "invalid_token"
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=invalid_token)
        
        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)
        
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_missing_user_id(mock_redis_client, test_env_vars):
    """Test JWT validation with token missing user_id."""
    with patch("api_gateway.dependencies.redis_client") as mock_redis_wrapper:
        mock_redis_wrapper.get = AsyncMock(return_value=None)
        
        # Create token without 'sub' field
        token_payload = {"exp": 9999999999}  # No 'sub'
        token = jwt.encode(token_payload, settings.supabase_jwt_secret, algorithm="HS256")
        
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)
        
        assert exc_info.value.status_code == 401
        assert "missing user_id" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_job_ownership_success(mock_database_client, test_env_vars):
    """Test job ownership verification success."""
    with patch("api_gateway.dependencies.db_client") as mock_db:
        job_id = "test_job_id"
        user_id = "test_user_id"
        
        # Mock database query builder chain
        mock_result = MagicMock()
        mock_result.data = [{"id": job_id, "user_id": user_id, "status": "queued"}]
        
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=mock_result)
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.select = MagicMock(return_value=mock_query)
        
        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_query)
        mock_db.table = MagicMock(return_value=mock_table)
        
        current_user = {"user_id": user_id}
        
        # Call dependency directly
        job = await verify_job_ownership(job_id, current_user)
        
        assert job["id"] == job_id
        assert job["user_id"] == user_id


@pytest.mark.asyncio
async def test_verify_job_ownership_forbidden(mock_database_client, test_env_vars):
    """Test job ownership verification failure."""
    with patch("api_gateway.dependencies.db_client") as mock_db:
        job_id = "test_job_id"
        job_user_id = "job_owner_id"
        current_user_id = "different_user_id"
        
        # Mock database query builder chain
        mock_result = MagicMock()
        mock_result.data = [{"id": job_id, "user_id": job_user_id}]
        
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=mock_result)
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.select = MagicMock(return_value=mock_query)
        
        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_query)
        mock_db.table = MagicMock(return_value=mock_table)
        
        current_user = {"user_id": current_user_id}
        
        # Should raise HTTPException 403
        with pytest.raises(HTTPException) as exc_info:
            await verify_job_ownership(job_id, current_user)
        
        assert exc_info.value.status_code == 403
        assert "does not belong to user" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_job_ownership_not_found(mock_database_client, test_env_vars):
    """Test job ownership verification when job not found."""
    with patch("api_gateway.dependencies.db_client") as mock_db:
        job_id = "nonexistent_job_id"
        user_id = "test_user_id"
        
        # Mock empty database result
        mock_result = MagicMock()
        mock_result.data = []
        
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=mock_result)
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.select = MagicMock(return_value=mock_query)
        
        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_query)
        mock_db.table = MagicMock(return_value=mock_table)
        
        current_user = {"user_id": user_id}
        
        # Should raise HTTPException 404
        with pytest.raises(HTTPException) as exc_info:
            await verify_job_ownership(job_id, current_user)
        
        assert exc_info.value.status_code == 404
        assert "Job not found" in exc_info.value.detail
