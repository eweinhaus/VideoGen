"""
FastAPI application entry point.

Main application setup with CORS, middleware, and route registration.
"""

import uuid
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from shared.config import settings
from shared.logging import get_logger
from shared.errors import (
    ValidationError,
    BudgetExceededError,
    RateLimitError,
    RetryableError,
    PipelineError
)

logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="VideoGen API Gateway",
    description="Central orchestration layer for video generation pipeline",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
    max_age=3600
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request ID to each request."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Log request
    logger.info(
        "Request started",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path
        }
    )
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=400,
        content={
            "error": str(exc),
            "code": "VALIDATION_ERROR",
            "retryable": False,
            "request_id": getattr(request.state, "request_id", None)
        }
    )


@app.exception_handler(BudgetExceededError)
async def budget_error_handler(request: Request, exc: BudgetExceededError):
    """Handle budget exceeded errors."""
    return JSONResponse(
        status_code=402,
        content={
            "error": str(exc),
            "code": "BUDGET_EXCEEDED",
            "retryable": False,
            "request_id": getattr(request.state, "request_id", None)
        }
    )


@app.exception_handler(RateLimitError)
async def rate_limit_error_handler(request: Request, exc: RateLimitError):
    """Handle rate limit errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": str(exc),
            "code": "RATE_LIMIT_EXCEEDED",
            "retryable": True,
            "request_id": getattr(request.state, "request_id", None)
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 3600))}
    )


@app.exception_handler(RetryableError)
async def retryable_error_handler(request: Request, exc: RetryableError):
    """Handle retryable errors."""
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "code": "RETRYABLE_ERROR",
            "retryable": True,
            "request_id": getattr(request.state, "request_id", None)
        }
    )


@app.exception_handler(PipelineError)
async def pipeline_error_handler(request: Request, exc: PipelineError):
    """Handle pipeline errors."""
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "code": "MODULE_FAILURE",
            "retryable": False,
            "request_id": getattr(request.state, "request_id", None)
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={"request_id": getattr(request.state, "request_id", None)}
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
            "retryable": False,
            "request_id": getattr(request.state, "request_id", None)
        }
    )


# Register routes
from api_gateway.routes import upload, health, jobs, download, stream

app.include_router(upload.router, prefix="/api/v1", tags=["upload"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
app.include_router(download.router, prefix="/api/v1", tags=["download"])
app.include_router(stream.router, prefix="/api/v1", tags=["stream"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "VideoGen API Gateway", "version": "1.0.0"}

