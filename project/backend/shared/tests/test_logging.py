"""
Tests for structured logging.
"""

import json
import logging
import tempfile
from pathlib import Path
from uuid import UUID, uuid4
from shared.logging import get_logger, set_job_id, get_job_id, JSONFormatter


def test_get_logger_creates_logger():
    """Test that get_logger creates a logger instance."""
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_logger_outputs_json_format(caplog):
    """Test that logger outputs JSON format."""
    logger = get_logger("test_module")
    logger.setLevel(logging.INFO)
    
    logger.info("Test message", extra={"key": "value"})
    
    # Get the last log record
    assert len(caplog.records) > 0
    last_record = caplog.records[-1]
    
    # Format as JSON
    formatter = JSONFormatter()
    json_output = formatter.format(last_record)
    
    # Parse JSON to verify it's valid
    log_data = json.loads(json_output)
    assert log_data["level"] == "INFO"
    # Module name will be the actual test module name, not the logger name
    assert "message" in log_data
    assert log_data["message"] == "Test message"
    assert log_data["key"] == "value"


def test_logger_includes_job_id(caplog):
    """Test that logger includes job_id when set in context."""
    logger = get_logger("test_module")
    logger.setLevel(logging.INFO)
    
    job_id = uuid4()
    set_job_id(job_id)
    
    try:
        logger.info("Test message")
        
        # Get the last log record
        assert len(caplog.records) > 0
        last_record = caplog.records[-1]
        
        # Format as JSON
        formatter = JSONFormatter()
        json_output = formatter.format(last_record)
        log_data = json.loads(json_output)
        
        assert log_data["job_id"] == str(job_id)
    finally:
        set_job_id(None)


def test_logger_excludes_job_id_when_not_set(caplog):
    """Test that logger excludes job_id when not set."""
    logger = get_logger("test_module")
    logger.setLevel(logging.INFO)
    
    set_job_id(None)
    logger.info("Test message")
    
    # Get the last log record
    assert len(caplog.records) > 0
    last_record = caplog.records[-1]
    
    # Format as JSON
    formatter = JSONFormatter()
    json_output = formatter.format(last_record)
    log_data = json.loads(json_output)
    
    assert "job_id" not in log_data


def test_set_get_job_id():
    """Test that job_id can be set and retrieved."""
    job_id = uuid4()
    set_job_id(job_id)
    assert get_job_id() == job_id
    
    set_job_id(None)
    assert get_job_id() is None


def test_logger_includes_extra_fields(caplog):
    """Test that logger includes extra fields in JSON."""
    logger = get_logger("test_module")
    logger.setLevel(logging.INFO)
    
    logger.info("Test message", extra={
        "duration": 180,
        "status": "success",
        "count": 5
    })
    
    # Get the last log record
    assert len(caplog.records) > 0
    last_record = caplog.records[-1]
    
    # Format as JSON
    formatter = JSONFormatter()
    json_output = formatter.format(last_record)
    log_data = json.loads(json_output)
    
    assert log_data["duration"] == 180
    assert log_data["status"] == "success"
    assert log_data["count"] == 5


def test_logger_includes_exception(caplog):
    """Test that logger includes exception information."""
    logger = get_logger("test_module")
    logger.setLevel(logging.ERROR)
    
    try:
        raise ValueError("Test error")
    except ValueError as e:
        logger.exception("Exception occurred", exc_info=True)
    
    # Get the last log record
    assert len(caplog.records) > 0
    last_record = caplog.records[-1]
    
    # Format as JSON
    formatter = JSONFormatter()
    json_output = formatter.format(last_record)
    log_data = json.loads(json_output)
    
    assert "exception" in log_data
    assert "ValueError" in log_data["exception"]
    assert "Test error" in log_data["exception"]


def test_logger_respects_log_level(caplog):
    """Test that logger respects log level configuration."""
    logger = get_logger("test_module")
    logger.setLevel(logging.WARNING)
    
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    
    # Only WARNING and ERROR should be logged
    log_levels = [record.levelname for record in caplog.records]
    assert "DEBUG" not in log_levels
    assert "INFO" not in log_levels
    assert "WARNING" in log_levels
    assert "ERROR" in log_levels


def test_logger_handles_complex_types(caplog):
    """Test that logger handles complex types in extra fields."""
    logger = get_logger("test_module")
    logger.setLevel(logging.INFO)
    
    # Complex types should be converted to strings
    logger.info("Test message", extra={
        "list": [1, 2, 3],
        "dict": {"key": "value"},
        "uuid": uuid4()
    })
    
    # Get the last log record
    assert len(caplog.records) > 0
    last_record = caplog.records[-1]
    
    # Format as JSON
    formatter = JSONFormatter()
    json_output = formatter.format(last_record)
    log_data = json.loads(json_output)
    
    # Complex types should be strings
    assert isinstance(log_data["list"], str)
    assert isinstance(log_data["dict"], str)
    assert isinstance(log_data["uuid"], str)


def test_logger_creates_file_handler(tmp_path, monkeypatch):
    """Test that logger creates file handler with rotation."""
    from unittest.mock import patch
    from pathlib import Path
    
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    
    # Mock the log directory path
    with patch("shared.logging.Path") as mock_path_class:
        mock_path_class.return_value = log_dir
        
        # Create a new logger (not cached)
        logger_name = f"test_module_{id(tmp_path)}"
        logger = get_logger(logger_name)
        
        # Check that file handler exists
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) > 0

