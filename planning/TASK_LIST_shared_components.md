# Task List: Shared Components Implementation

**Version:** 1.0  
**Date:** November 2025  
**Estimated Time:** 8-9 hours  
**Priority:** CRITICAL - Blocks all module development

---

## Overview

This task list covers the implementation of 10 shared components that form the foundation for all 8 pipeline modules. These components must be completed before any module development can begin.

---

## Task 1: Configuration Management (`config.py`)

**Estimated Time:** 30 minutes  
**Dependencies:** None  
**Blocks:** All other components

### Subtasks
1. Create `config.py` in `backend/shared/`
2. Install `python-dotenv` dependency
3. Define `Settings` class using Pydantic `BaseSettings` or similar
4. Load environment variables from `.env` file
5. Define all required environment variables:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`
   - `REDIS_URL`
   - `OPENAI_API_KEY`
   - `REPLICATE_API_TOKEN`
   - `JWT_SECRET_KEY`
   - `ENVIRONMENT` (development/staging/production)
   - `LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR)
6. Implement validation for required variables
7. Implement URL format validation (Supabase, Redis)
8. Implement basic API key format checks
9. Raise `ConfigError` for missing/invalid config
10. Export `settings` singleton instance
11. Add type hints for all settings
12. Write docstrings for Settings class

### Success Criteria
- ✅ All required env vars validated at import
- ✅ Type-safe access to all settings
- ✅ Clear error messages for missing/invalid config
- ✅ Works in all environments (dev/staging/prod)

### Testing Requirements
- Unit test: Missing required env var raises ConfigError
- Unit test: Invalid URL format raises ConfigError
- Unit test: Valid config loads successfully
- Integration test: Works with real .env file

---

## Task 2: Error Handling (`errors.py`)

**Estimated Time:** 30 minutes  
**Dependencies:** None (but needed by other components)  
**Blocks:** All other components

### Subtasks
1. Create `errors.py` in `backend/shared/`
2. Define `PipelineError` base exception class
   - Include `message`, `job_id`, `code` attributes
   - Proper `__init__` method
3. Define `ConfigError(PipelineError)` for configuration errors
4. Define `AudioAnalysisError(PipelineError)` for audio processing failures
5. Define `GenerationError(PipelineError)` for AI generation failures
6. Define `CompositionError(PipelineError)` for video composition failures
7. Define `BudgetExceededError(PipelineError)` for cost limit exceeded
8. Define `RetryableError(PipelineError)` for retryable errors
9. Define `ValidationError(PipelineError)` for input validation errors
10. Add docstrings to all exception classes
11. Export all exceptions from module

### Success Criteria
- ✅ All exceptions inherit from PipelineError
- ✅ Exceptions include job_id when available
- ✅ Retryable errors are properly marked
- ✅ Error messages are clear and actionable

### Testing Requirements
- Unit test: All exceptions inherit from PipelineError
- Unit test: Exceptions can be raised with job_id
- Unit test: Exception messages are clear

---

## Task 3: Database Client (`database.py`)

**Estimated Time:** 30 minutes  
**Dependencies:** `config.py`, `errors.py`  
**Blocks:** `cost_tracking.py`, all modules

### Subtasks
1. Create `database.py` in `backend/shared/`
2. Install `supabase` >= 2.0 dependency
3. Import settings from `config.py`
4. Create `DatabaseClient` class
5. Initialize Supabase client with service key
6. Implement connection health check method
7. Implement query helper methods (optional wrapper)
8. Implement transaction context manager (using RPC or application-level)
9. Implement connection retry logic (3 attempts, exponential backoff)
10. Add error handling for connection failures
11. Export `db` singleton instance
12. Add type hints and docstrings
13. Handle async operations correctly

### Success Criteria
- ✅ Connection pool works correctly
- ✅ Queries execute successfully
- ✅ Transactions rollback on error (or handle gracefully)
- ✅ Health check returns accurate status
- ✅ Handles connection failures gracefully

### Testing Requirements
- Unit test: Database client initializes correctly
- Integration test: Can connect to Supabase
- Integration test: Can execute queries
- Integration test: Health check works
- Error test: Handles connection failures gracefully

---

## Task 4: Redis Client (`redis_client.py`)

**Estimated Time:** 30 minutes  
**Dependencies:** `config.py`, `errors.py`  
**Blocks:** Caching in modules

### Subtasks
1. Create `redis_client.py` in `backend/shared/`
2. Install `redis` >= 5.0 dependency
3. Import settings from `config.py`
4. Create `RedisClient` class
5. Initialize async Redis client with connection pool
6. Implement `set()` method with TTL support
7. Implement `get()` method
8. Implement `delete()` method
9. Implement `set_json()` method (JSON serialization)
10. Implement `get_json()` method (JSON deserialization)
11. Implement key prefixing (`videogen:cache:{key}`)
12. Implement connection health check method
13. Add error handling for connection failures
14. Export `redis` singleton instance
15. Add type hints and docstrings
16. Ensure all operations are async-compatible

### Success Criteria
- ✅ Get/set/delete operations work
- ✅ TTL expiration works correctly
- ✅ JSON serialization handles complex objects
- ✅ Health check returns accurate status
- ✅ Handles connection failures gracefully

### Testing Requirements
- Unit test: Redis client initializes correctly
- Integration test: Can connect to Redis
- Integration test: Get/set/delete operations work
- Integration test: TTL expiration works
- Integration test: JSON serialization works
- Error test: Handles connection failures gracefully

---

## Task 5: Data Models (`models/`)

**Estimated Time:** 2 hours  
**Dependencies:** None (foundation)  
**Blocks:** All modules

### Subtasks

#### 5.1 Models Structure
1. Create `models/` directory in `backend/shared/`
2. Create `__init__.py` to export all models
3. Create `job.py` for job-related models
4. Create `audio.py` for audio analysis models
5. Create `scene.py` for scene planning models
6. Create `video.py` for video generation models

#### 5.2 Job Models (`models/job.py`)
7. Define `Job` model with all fields:
   - `id: UUID`, `user_id: UUID`
   - `status: Literal["queued", "processing", "completed", "failed"]`
   - `audio_url: str`, `user_prompt: str`
   - `current_stage: Optional[str]`
   - `progress: int = 0` (0-100)
   - `estimated_remaining: Optional[int]` (seconds)
   - `total_cost: Decimal = Decimal("0.00")`
   - `video_url: Optional[str]`
   - `error_message: Optional[str]`
   - `created_at: datetime`, `updated_at: datetime`, `completed_at: Optional[datetime]`
8. Define `JobStage` model with all fields
9. Define `JobCost` model with all fields
10. Add proper type hints and field validators
11. Add docstrings

#### 5.3 Audio Models (`models/audio.py`)
12. Define `SongStructure` model
13. Define `Lyric` model
14. Define `Mood` model
15. Define `ClipBoundary` model
16. Define `AudioAnalysis` model with all fields
17. Add proper type hints and field validators
18. Add docstrings

#### 5.4 Scene Models (`models/scene.py`)
19. Define `Character` model
20. Define `Scene` model
21. Define `Style` model
22. Define `ClipScript` model
23. Define `Transition` model
24. Define `ScenePlan` model with all fields
25. Define `ReferenceImage` model
26. Define `ReferenceImages` model
27. Add proper type hints and field validators
28. Add docstrings

#### 5.5 Video Models (`models/video.py`)
29. Define `ClipPrompt` model
30. Define `ClipPrompts` model
31. Define `Clip` model
32. Define `Clips` model
33. Define `VideoOutput` model
34. Add proper type hints and field validators
35. Add docstrings

#### 5.6 Model Exports
36. Export all models from `models/__init__.py`
37. Ensure models can be imported cleanly

### Success Criteria
- ✅ All models validate input correctly
- ✅ Models serialize/deserialize to/from JSON
- ✅ Type hints are accurate
- ✅ Models match database schema
- ✅ Models can be used in FastAPI request/response

### Testing Requirements
- Unit test: All models validate correctly
- Unit test: Models serialize to JSON
- Unit test: Models deserialize from JSON
- Unit test: Invalid data raises ValidationError
- Unit test: Optional fields work correctly
- Integration test: Models work with FastAPI

---

## Task 6: Storage Utilities (`storage.py`)

**Estimated Time:** 1 hour  
**Dependencies:** `config.py`, `errors.py`  
**Blocks:** File operations in modules

### Subtasks
1. Create `storage.py` in `backend/shared/`
2. Import Supabase client from `database.py` or create storage client
3. Create `StorageClient` class
4. Implement `upload_file()` method:
   - Accept bucket, path, file_data (bytes), content_type
   - Handle automatic content-type detection
   - Validate file size
   - Use Supabase Storage API
   - Return URL
5. Implement `download_file()` method:
   - Accept bucket, path
   - Return file data as bytes
6. Implement `get_signed_url()` method:
   - Accept bucket, path, expires_in (seconds)
   - Generate signed URL with expiration
7. Implement `delete_file()` method:
   - Accept bucket, path
   - Delete file from storage
8. Add error handling for network errors, permission errors
9. Add retry logic for transient failures
10. Ensure service key is used (bypasses RLS)
11. Export `storage` singleton instance
12. Add type hints and docstrings
13. Ensure all operations are async-compatible

### Success Criteria
- ✅ Upload/download works for all file types
- ✅ Signed URLs expire correctly
- ✅ File deletion works
- ✅ Handles errors gracefully
- ✅ Respects bucket permissions (service key access)

### Testing Requirements
- Unit test: Storage client initializes correctly
- Integration test: Can upload file to Supabase Storage
- Integration test: Can download file from Supabase Storage
- Integration test: Signed URLs work and expire
- Integration test: Can delete files
- Error test: Handles network errors gracefully
- Error test: Handles permission errors gracefully

---

## Task 7: Retry Logic (`retry.py`)

**Estimated Time:** 1 hour  
**Dependencies:** `errors.py`, `logging.py` (for logging retries)  
**Blocks:** API calls in modules

### Subtasks
1. Create `retry.py` in `backend/shared/`
2. Import `RetryableError` from `errors.py`
3. Create `retry_with_backoff` decorator function
4. Implement exponential backoff logic:
   - `delay = base_delay * (2 ** attempt_number)`
   - Default: 2s, 4s, 8s
5. Implement configurable max_attempts (default: 3)
6. Implement configurable base_delay (default: 2)
7. Implement exception filtering (only retry on RetryableError or specified exceptions)
8. Add logging for each retry attempt
9. Raise last exception if all retries fail
10. Ensure decorator works with async functions
11. Add type hints and docstrings
12. Export decorator

### Success Criteria
- ✅ Retries correct number of times
- ✅ Backoff delay increases correctly
- ✅ Only retries on specified exceptions
- ✅ Logs retry attempts
- ✅ Raises exception after max attempts

### Testing Requirements
- Unit test: Decorator retries correct number of times
- Unit test: Backoff delay increases exponentially
- Unit test: Only retries on RetryableError
- Unit test: Raises exception after max attempts
- Unit test: Works with async functions
- Integration test: Retry logic works with real API calls

---

## Task 8: Cost Tracking (`cost_tracking.py`)

**Estimated Time:** 1 hour  
**Dependencies:** `database.py`, `errors.py`  
**Blocks:** Budget enforcement in API Gateway

### Subtasks
1. Create `cost_tracking.py` in `backend/shared/`
2. Import `db` from `database.py`
3. Import `BudgetExceededError` from `errors.py`
4. Create `CostTracker` class
5. Implement `track_cost()` method:
   - Accept job_id, stage_name, api_name, cost (Decimal)
   - Insert into `job_costs` table
   - Update `jobs.total_cost` field atomically
   - Use asyncio.Lock for concurrent-safe operations
6. Implement `get_total_cost()` method:
   - Accept job_id
   - Query and return total cost
7. Implement `check_budget()` method:
   - Accept job_id, new_cost, limit
   - Return boolean (can proceed or not)
8. Implement `enforce_budget_limit()` method:
   - Accept job_id, limit
   - Check current total + any pending costs
   - Raise `BudgetExceededError` if exceeded
9. Ensure atomic database operations
10. Add asyncio.Lock for thread-safety (parallel video generation)
11. Export `cost_tracker` singleton instance
12. Add type hints and docstrings

### Success Criteria
- ✅ Costs tracked accurately
- ✅ Total cost calculated correctly
- ✅ Budget limit enforced
- ✅ Costs stored in database
- ✅ Async-safe for concurrent operations (parallel video generation)

### Testing Requirements
- Unit test: Cost tracking works correctly
- Unit test: Total cost calculated correctly
- Unit test: Budget check works
- Unit test: Budget enforcement raises BudgetExceededError
- Integration test: Costs stored in database
- Integration test: Concurrent cost tracking is safe
- Error test: Handles database errors gracefully

---

## Task 9: Logging (`logging.py`)

**Estimated Time:** 30 minutes  
**Dependencies:** `config.py`  
**Blocks:** Logging in all modules

### Subtasks
1. Create `logging.py` in `backend/shared/`
2. Import settings from `config.py`
3. Create `get_logger()` function
4. Configure structured JSON logging:
   - Use Python `logging` module
   - JSON formatter
   - Include timestamp, level, module, job_id, message
5. Configure log level from environment variable
6. Configure console output
7. Configure file output with rotation:
   - Max 100MB per file
   - Keep 5 files
8. Implement automatic job_id injection (if available in context)
9. Add type hints and docstrings
10. Export `get_logger` function

### Success Criteria
- ✅ Logs include all required fields
- ✅ Log level configurable
- ✅ JSON format is valid
- ✅ File rotation works
- ✅ Job_id automatically included

### Testing Requirements
- Unit test: Logger creates correctly
- Unit test: Log level respects config
- Unit test: JSON format is valid
- Unit test: File rotation works
- Integration test: Logs written to file
- Integration test: Logs include job_id when available

---

## Task 10: Validation Utilities (`validation.py`)

**Estimated Time:** 30 minutes  
**Dependencies:** `errors.py`  
**Blocks:** Input validation in API Gateway

### Subtasks
1. Create `validation.py` in `backend/shared/`
2. Import `ValidationError` from `errors.py`
3. Implement `validate_audio_file()` function:
   - Accept file object, max_size_mb
   - Check MIME type (MP3, WAV, FLAC)
   - Check file size
   - Raise ValidationError if invalid
4. Implement `validate_prompt()` function:
   - Accept prompt, min_length, max_length
   - Check length constraints
   - Raise ValidationError if invalid
5. Implement `validate_file_size()` function:
   - Accept file_size_bytes, max_size_bytes
   - Check size constraint
   - Raise ValidationError if invalid
6. Add clear error messages
7. Handle edge cases (empty files, invalid types)
8. Add type hints and docstrings
9. Export all validation functions

### Success Criteria
- ✅ All validation functions work correctly
- ✅ Error messages are clear and actionable
- ✅ Handles edge cases (empty files, invalid types)
- ✅ Consistent validation across modules

### Testing Requirements
- Unit test: Audio file validation works
- Unit test: Prompt validation works
- Unit test: File size validation works
- Unit test: Invalid inputs raise ValidationError
- Unit test: Edge cases handled correctly

---

## Task 11: Integration Testing

**Estimated Time:** 1 hour  
**Dependencies:** All previous tasks  
**Blocks:** Module development

### Subtasks
1. Create `tests/` directory in `backend/shared/`
2. Create `test_config.py` - Test configuration loading
3. Create `test_database.py` - Test database operations
4. Create `test_redis.py` - Test Redis operations
5. Create `test_models.py` - Test all Pydantic models
6. Create `test_storage.py` - Test storage operations
7. Create `test_retry.py` - Test retry logic
8. Create `test_cost_tracking.py` - Test cost tracking
9. Create `test_logging.py` - Test logging setup
10. Create `test_validation.py` - Test validation utilities
11. Create integration test suite that tests components together
12. Ensure 80%+ test coverage
13. Run all tests and fix any failures

### Success Criteria
- ✅ All unit tests pass
- ✅ All integration tests pass
- ✅ Test coverage >= 80%
- ✅ All components work together correctly

---

## Task 12: Documentation & Final Verification

**Estimated Time:** 30 minutes  
**Dependencies:** All previous tasks  
**Blocks:** Module development

### Subtasks
1. Review all docstrings for completeness
2. Add module-level docstrings where missing
3. Create `README.md` in `backend/shared/` with:
   - Overview of shared components
   - Usage examples for each component
   - Dependencies and setup instructions
4. Verify all components can be imported without errors
5. Verify type hints are correct (run mypy)
6. Verify all components work with real services
7. Create example usage file showing how to use all components
8. Update memory bank with completion status

### Success Criteria
- ✅ All components documented
- ✅ All components can be imported without errors
- ✅ Type hints are correct (mypy passes)
- ✅ All components work with real services
- ✅ README is complete and helpful

---

## Verification Tasks

### Automated Tests
- [ ] Run all unit tests: `pytest backend/shared/tests/`
- [ ] Run all integration tests: `pytest backend/shared/tests/integration/`
- [ ] Verify test coverage >= 80%: `pytest --cov=backend/shared --cov-report=html`
- [ ] Run type checking: `mypy backend/shared/`
- [ ] Run linting: `ruff check backend/shared/`

### Manual Verification
- [ ] Verify all components import without errors
- [ ] Verify configuration loads correctly with real .env file
- [ ] Verify database client connects to Supabase
- [ ] Verify Redis client connects to Redis
- [ ] Verify storage operations work with Supabase Storage
- [ ] Verify cost tracking stores costs correctly
- [ ] Verify logging outputs structured JSON
- [ ] Verify validation functions work correctly

### Integration Verification
- [ ] Test all components together in a simple script
- [ ] Verify error handling works end-to-end
- [ ] Verify retry logic works with real API calls
- [ ] Verify cost tracking enforces budget limit
- [ ] Verify models serialize/deserialize correctly

---

## Summary

**Total Estimated Time:** 8-9 hours  
**Total Tasks:** 12 main tasks + verification  
**Critical Path:** Tasks 1-10 must be completed in order (with dependencies respected)  
**Blocking:** All 8 pipeline modules depend on these shared components

**Priority Order:**
1. config.py (foundation)
2. errors.py (needed by others)
3. database.py (needed by cost_tracking.py)
4. redis_client.py (needed for caching)
5. models/ (defines interfaces)
6. storage.py (file operations)
7. retry.py (API retries)
8. cost_tracking.py (budget enforcement)
9. logging.py (observability)
10. validation.py (input validation)
11. Integration testing
12. Documentation & verification

---

## Notes

- All components must be async-compatible
- All components must be type-hinted (mypy compliance)
- All components must handle errors gracefully
- All components must be documented (docstrings)
- All components must be testable (dependency injection where possible)
- Follow the implementation order specified in the PRD
- Test each component as it's completed
- Update memory bank after completion

