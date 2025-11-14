"""
Configuration management.

Centralized environment variable management and validation.
"""

import os
from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared.errors import ConfigError


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Allow case-insensitive env var matching
        extra="ignore"
    )
    
    # Supabase configuration
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    
    # Redis configuration
    redis_url: str
    
    # API keys
    openai_api_key: str
    replicate_api_token: str
    
    # JWT configuration
    jwt_secret_key: str
    supabase_jwt_secret: str  # Supabase JWT secret for token validation
    
    # Frontend configuration
    frontend_url: str  # Frontend domain for CORS
    
    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    
    # Rate limiting
    rate_limit_fail_closed: bool = False  # Default: fail-open for MVP
    
    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, v: str) -> str:
        """Validate Supabase URL format."""
        if not v:
            raise ConfigError("SUPABASE_URL is required")
        if not v.startswith(("http://", "https://")):
            raise ConfigError("SUPABASE_URL must be a valid HTTP/HTTPS URL")
        if ".supabase.co" not in v:
            raise ConfigError("SUPABASE_URL must be a valid Supabase URL")
        return v
    
    @field_validator("supabase_service_key")
    @classmethod
    def validate_supabase_service_key(cls, v: str) -> str:
        """Validate Supabase service key format."""
        if not v:
            raise ConfigError("SUPABASE_SERVICE_KEY is required")
        if len(v) < 50:  # Basic format check
            raise ConfigError("SUPABASE_SERVICE_KEY appears to be invalid")
        return v
    
    @field_validator("supabase_anon_key")
    @classmethod
    def validate_supabase_anon_key(cls, v: str) -> str:
        """Validate Supabase anon key format."""
        if not v:
            raise ConfigError("SUPABASE_ANON_KEY is required")
        if len(v) < 50:  # Basic format check
            raise ConfigError("SUPABASE_ANON_KEY appears to be invalid")
        return v
    
    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Validate Redis URL format."""
        if not v:
            raise ConfigError("REDIS_URL is required")
        if not v.startswith(("redis://", "rediss://")):
            raise ConfigError("REDIS_URL must start with redis:// or rediss://")
        return v
    
    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_api_key(cls, v: str) -> str:
        """Validate OpenAI API key format."""
        if not v:
            raise ConfigError("OPENAI_API_KEY is required")
        if not v.startswith("sk-"):
            raise ConfigError("OPENAI_API_KEY must start with 'sk-'")
        if len(v) < 20:
            raise ConfigError("OPENAI_API_KEY appears to be invalid")
        return v
    
    @field_validator("replicate_api_token")
    @classmethod
    def validate_replicate_api_token(cls, v: str) -> str:
        """Validate Replicate API token format."""
        if not v:
            raise ConfigError("REPLICATE_API_TOKEN is required")
        if not v.startswith("r8_"):
            raise ConfigError("REPLICATE_API_TOKEN must start with 'r8_'")
        if len(v) < 20:
            raise ConfigError("REPLICATE_API_TOKEN appears to be invalid")
        return v
    
    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        """Validate JWT secret key format."""
        if not v:
            raise ConfigError("JWT_SECRET_KEY is required")
        if len(v) < 32:
            raise ConfigError("JWT_SECRET_KEY must be at least 32 characters")
        return v
    
    @field_validator("supabase_jwt_secret")
    @classmethod
    def validate_supabase_jwt_secret(cls, v: str) -> str:
        """Validate Supabase JWT secret format."""
        if not v:
            raise ConfigError("SUPABASE_JWT_SECRET is required")
        if len(v) < 32:
            raise ConfigError("SUPABASE_JWT_SECRET must be at least 32 characters")
        return v
    
    @field_validator("frontend_url")
    @classmethod
    def validate_frontend_url(cls, v: str) -> str:
        """Validate frontend URL format."""
        if not v:
            raise ConfigError("FRONTEND_URL is required")
        if not v.startswith(("http://", "https://")):
            raise ConfigError("FRONTEND_URL must be a valid HTTP/HTTPS URL")
        return v


# Singleton instance
try:
    settings = Settings()
except Exception as e:
    # Re-raise as ConfigError for consistency
    if isinstance(e, ConfigError):
        raise
    raise ConfigError(f"Failed to load configuration: {str(e)}") from e
