"""
FastAPI dependencies.

Authentication, authorization, and request utilities.
"""

import hashlib
import json
from typing import Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from shared.config import settings
from shared.redis_client import RedisClient
from shared.database import DatabaseClient
from shared.logging import get_logger

logger = get_logger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)  # Don't auto-raise on missing token

# Redis client for JWT caching
redis_client = RedisClient()
db_client = DatabaseClient()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = None
) -> dict:
    """
    Validate JWT token and return current user.
    
    Supports both Bearer token (header) and query parameter authentication.
    
    Args:
        credentials: HTTP Bearer token credentials (from header)
        token: Optional token from query parameter (for SSE)
        
    Returns:
        Dictionary with user_id
        
    Raises:
        HTTPException: If token is invalid or missing
    """
    # Get token from header or query parameter
    if credentials:
        token = credentials.credentials
        logger.debug("Token from Authorization header", extra={"token_preview": token[:20] + "..." if token else None})
    elif token:
        logger.debug("Token from query parameter", extra={"token_preview": token[:20] + "..." if token else None})
    else:
        logger.warning("No token provided in header or query parameter")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check Redis cache first
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cache_key = f"jwt_valid:{token_hash}"
    
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            user_data = json.loads(cached)
            logger.debug("JWT validated from cache", extra={"user_id": user_data.get("user_id"), "email": user_data.get("email")})
            return user_data
    except Exception as e:
        logger.warning("Failed to check JWT cache", exc_info=e)
    
    # Validate JWT token
    try:
        # Log token info for debugging (first 50 chars only)
        token_preview = token[:50] + "..." if len(token) > 50 else token
        logger.debug(
            "Attempting JWT validation",
            extra={
                "token_length": len(token),
                "token_preview": token_preview,
                "jwt_secret_configured": bool(settings.supabase_jwt_secret),
                "jwt_secret_length": len(settings.supabase_jwt_secret) if settings.supabase_jwt_secret else 0
            }
        )
        
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False}  # Supabase tokens don't include audience claim
        )
        user_id = payload.get("sub")  # Supabase uses "sub" for user_id
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id"
            )
        
        # Log JWT payload keys for debugging (without sensitive values)
        logger.debug(
            "JWT payload keys",
            extra={
                "user_id": user_id,
                "payload_keys": list(payload.keys()),
                "has_email": "email" in payload
            }
        )
        
        # Extract email from JWT payload if available
        email = payload.get("email")
        user_data = {"user_id": user_id}
        if email:
            user_data["email"] = email
        else:
            # If email not in JWT, fetch from auth.users table
            try:
                user_result = await db_client.table("auth.users").select("email").eq("id", user_id).execute()
                if user_result.data and len(user_result.data) > 0:
                    email = user_result.data[0].get("email")
                    if email:
                        user_data["email"] = email
                        logger.debug("Fetched email from auth.users", extra={"user_id": user_id, "email": email})
            except Exception as e:
                logger.warning("Failed to fetch email from auth.users", exc_info=e, extra={"user_id": user_id})
        
        # Cache valid token for 5 minutes
        try:
            await redis_client.set(
                cache_key,
                json.dumps(user_data),
                ex=300  # 5 minutes TTL
            )
        except Exception as e:
            logger.warning("Failed to cache JWT", exc_info=e)
        
        logger.debug("JWT validated successfully", extra={"user_id": user_id, "email": user_data.get("email")})
        return user_data
        
    except JWTError as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(
            "JWT validation failed",
            extra={
                "error_type": error_type,
                "error_message": error_msg,
                "token_length": len(token) if token else 0,
                "jwt_secret_configured": bool(settings.supabase_jwt_secret),
                "hint": "Check that SUPABASE_JWT_SECRET matches your Supabase project's JWT secret (found in Settings > API > JWT Secret)"
            },
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {error_msg}. Please check your authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def verify_job_ownership(
    job_id: str,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Verify that the job belongs to the current user.
    
    Admin users (etweinhaus@gmail.com) can bypass ownership checks and access all jobs.
    
    Args:
        job_id: Job ID to verify
        current_user: Current user from get_current_user dependency (must include email)
        
    Returns:
        Job data dictionary
        
    Raises:
        HTTPException: If job not found or doesn't belong to user (unless admin)
    """
    try:
        # Validate UUID format before querying
        try:
            # Try to parse as UUID to validate format
            uuid_obj = UUID(job_id)
            # Use the properly formatted UUID string
            job_id_formatted = str(uuid_obj)
        except ValueError as e:
            logger.error(
                "Invalid job ID format",
                extra={
                    "job_id": job_id,
                    "job_id_length": len(job_id),
                    "error": str(e),
                    "current_user_id": current_user.get("user_id")
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid job ID format: {job_id}. Job IDs must be valid UUIDs (e.g., '123e4567-e89b-12d3-a456-426614174000')."
            )
        
        # Query job from database (using 'id' as job_id since schema uses 'id' as PK)
        result = await db_client.table("jobs").select("*").eq("id", job_id_formatted).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        job = result.data[0]
        
        # Verify ownership
        # Check if user has admin role in database
        user_email = current_user.get("email")
        user_id = current_user.get("user_id")
        
        # Query user_roles table to check if user is admin
        is_admin = False
        try:
            role_result = await db_client.table("user_roles").select("role").eq("user_id", user_id).execute()
            if role_result.data and len(role_result.data) > 0:
                is_admin = role_result.data[0].get("role") == "admin"
        except Exception as e:
            logger.warning("Failed to check admin role", exc_info=e, extra={"user_id": user_id})
        
        # Log for debugging
        logger.debug(
            "Verifying job ownership",
            extra={
                "job_id": job_id,
                "job_user_id": job.get("user_id"),
                "current_user_id": user_id,
                "current_user_email": user_email,
                "is_admin": is_admin,
                "ownership_match": job.get("user_id") == user_id
            }
        )
        
        if job.get("user_id") != user_id and not is_admin:
            logger.warning(
                "Job ownership verification failed",
                extra={
                    "job_id": job_id,
                    "job_user_id": job.get("user_id"),
                    "current_user_id": user_id,
                    "current_user_email": user_email,
                    "is_admin": is_admin
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Job does not belong to user"
            )
        
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to verify job ownership",
            exc_info=e,
            extra={
                "job_id": job_id,
                "current_user_id": current_user.get("user_id"),
                "current_user_email": current_user.get("email"),
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify job ownership: {str(e)}"
        )
