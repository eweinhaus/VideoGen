"""
FastAPI dependencies.

Authentication, authorization, and request utilities.
"""

import hashlib
import json
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from shared.config import settings
from shared.redis_client import RedisClient
from shared.database import DatabaseClient
from shared.logging import get_logger

logger = get_logger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer()

# Redis client for JWT caching
redis_client = RedisClient()
db_client = DatabaseClient()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Validate JWT token and return current user.
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        Dictionary with user_id
        
    Raises:
        HTTPException: If token is invalid or missing
    """
    token = credentials.credentials
    
    # Check Redis cache first
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cache_key = f"jwt_valid:{token_hash}"
    
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            user_data = json.loads(cached)
            logger.debug("JWT validated from cache", extra={"user_id": user_data.get("user_id")})
            return user_data
    except Exception as e:
        logger.warning("Failed to check JWT cache", exc_info=e)
    
    # Validate JWT token
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"]
        )
        user_id = payload.get("sub")  # Supabase uses "sub" for user_id
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id"
            )
        
        user_data = {"user_id": user_id}
        
        # Cache valid token for 5 minutes
        try:
            await redis_client.set(
                cache_key,
                json.dumps(user_data),
                ex=300  # 5 minutes TTL
            )
        except Exception as e:
            logger.warning("Failed to cache JWT", exc_info=e)
        
        logger.debug("JWT validated successfully", extra={"user_id": user_id})
        return user_data
        
    except JWTError as e:
        logger.warning("JWT validation failed", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def verify_job_ownership(
    job_id: str,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Verify that the job belongs to the current user.
    
    Args:
        job_id: Job ID to verify
        current_user: Current user from get_current_user dependency
        
    Returns:
        Job data dictionary
        
    Raises:
        HTTPException: If job not found or doesn't belong to user
    """
    try:
        # Query job from database (using 'id' as job_id since schema uses 'id' as PK)
        result = await db_client.table("jobs").select("*").eq("id", job_id).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        job = result.data[0]
        
        # Verify ownership
        if job.get("user_id") != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Job does not belong to user"
            )
        
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to verify job ownership", exc_info=e, extra={"job_id": job_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify job ownership"
        )
