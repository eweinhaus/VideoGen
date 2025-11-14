"""
Structured logging setup for all modules.

Provides JSON-structured logging with automatic job_id injection.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from uuid import UUID

from shared.config import settings

# Context variable for job_id
job_id_context: ContextVar[Optional[UUID]] = ContextVar("job_id", default=None)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Get job_id from context if available
        job_id = job_id_context.get()
        
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        
        # Add job_id if available
        if job_id:
            log_data["job_id"] = str(job_id)
        
        # Add any extra fields from record.__dict__
        # Python's logging adds extra fields as attributes to the record
        # Standard LogRecord attributes to exclude
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName", "levelname",
            "levelno", "lineno", "module", "msecs", "message", "pathname", "process",
            "processName", "relativeCreated", "thread", "threadName", "exc_info",
            "exc_text", "stack_info", "getMessage"
        }
        
        # Add non-standard attributes (these are the extra fields)
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                # Convert complex types to strings, keep simple types as-is
                if isinstance(value, (str, int, float, bool, type(None))):
                    log_data[key] = value
                else:
                    log_data[key] = str(value)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, default=str)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Module name (e.g., "audio_parser")
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Don't add handlers if already configured
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    
    # Console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)
    
    # File handler with rotation
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=100 * 1024 * 1024,  # 100MB
        backupCount=5
    )
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    return logger


def set_job_id(job_id: Optional[UUID]) -> None:
    """
    Set job_id in context for automatic injection into logs.
    
    Args:
        job_id: Job ID to set in context
    """
    job_id_context.set(job_id)


def get_job_id() -> Optional[UUID]:
    """
    Get current job_id from context.
    
    Returns:
        Current job_id or None
    """
    return job_id_context.get()
