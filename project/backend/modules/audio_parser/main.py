"""
Main entry point for audio analysis.

FastAPI router integration and job processing entry point.
"""

import time
from uuid import UUID

from shared.models.audio import AudioAnalysis
from shared.errors import ValidationError, AudioAnalysisError
from shared.logging import get_logger, set_job_id
from shared.retry import retry_with_backoff

from modules.audio_parser.parser import parse_audio
from modules.audio_parser.cache import get_cached_analysis, store_cached_analysis
from modules.audio_parser.utils import download_audio_file, validate_audio_file, calculate_file_hash

logger = get_logger("audio_parser")


async def process_audio_analysis(job_id: UUID, audio_url: str) -> AudioAnalysis:
    """
    Main entry point called by API Gateway orchestrator.
    
    Args:
        job_id: Job ID
        audio_url: URL or path to audio file in storage
        
    Returns:
        AudioAnalysis model
        
    Raises:
        ValidationError: If inputs are invalid
        AudioAnalysisError: If processing fails
    """
    # Set job_id in context for logging
    set_job_id(job_id)
    
    start_time = time.time()
    
    try:
        # 1. Validate inputs
        logger.info(f"Starting audio analysis for job {job_id}, audio_url={audio_url}")
        
        if not job_id:
            raise ValidationError("job_id is required", job_id=job_id)
        
        if not audio_url:
            raise ValidationError("audio_url is required", job_id=job_id)
        
        # 2. Check Redis cache using audio file hash
        # First, we need to download the file to calculate hash
        # But we can optimize: if URL contains hash, use it directly
        # For now, download first to get hash
        
        logger.info(f"Downloading audio file for job {job_id}")
        audio_bytes = await download_audio_file(audio_url)
        
        # 3. Calculate MD5 hash of audio file bytes
        file_hash = calculate_file_hash(audio_bytes)
        logger.info(f"Calculated file hash: {file_hash}")
        
        # 4. Check cache
        cached_analysis = await get_cached_analysis(file_hash)
        if cached_analysis is not None:
            logger.info(f"Cache hit for job {job_id}, file_hash={file_hash}")
            # Update metadata to indicate cache hit
            cached_analysis.metadata["cache_hit"] = True
            cached_analysis.metadata["processing_time"] = time.time() - start_time
            cached_analysis.job_id = job_id  # Update job_id in case of cache hit
            return cached_analysis
        
        # 5. Validate audio file
        logger.info(f"Validating audio file for job {job_id}")
        validate_audio_file(audio_bytes, max_size_mb=10)
        
        # 6. Call parse_audio function
        logger.info(f"Processing audio analysis for job {job_id}")
        analysis = await parse_audio(audio_bytes, job_id)
        
        # 7. Store result in Redis cache (24h TTL) and database cache table
        try:
            await store_cached_analysis(file_hash, analysis, ttl=86400)
            logger.info(f"Stored analysis in cache: file_hash={file_hash}")
        except Exception as e:
            # Cache write failures should not fail the request
            logger.warning(f"Failed to store cache: {str(e)}")
        
        # 8. Return AudioAnalysis model
        processing_time = time.time() - start_time
        analysis.metadata["processing_time"] = processing_time
        
        logger.info(
            f"Audio analysis complete for job {job_id}: "
            f"duration={analysis.duration:.2f}s, processing_time={processing_time:.2f}s"
        )
        
        return analysis
        
    except ValidationError:
        raise
    except AudioAnalysisError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in audio analysis for job {job_id}: {str(e)}")
        raise AudioAnalysisError(f"Failed to process audio analysis: {str(e)}", job_id=job_id) from e


async def get_cached_analysis_by_hash(file_hash: str) -> AudioAnalysis | None:
    """
    Get cached analysis by file hash (utility function).
    
    Args:
        file_hash: MD5 hash of audio file
        
    Returns:
        AudioAnalysis if found, None otherwise
    """
    return await get_cached_analysis(file_hash)

