"""
Main entry point for audio analysis.

FastAPI router integration and job processing entry point.
"""

import time
from typing import Optional
from uuid import UUID

from shared.models.audio import AudioAnalysis
from shared.errors import ValidationError, AudioAnalysisError
from shared.logging import get_logger, set_job_id
from shared.retry import retry_with_backoff

from modules.audio_parser.parser import parse_audio
from modules.audio_parser.cache import get_cached_analysis, store_cached_analysis
from modules.audio_parser.utils import (
    download_audio_file,
    validate_audio_file_bytes,
    calculate_file_hash,
    extract_hash_from_url
)

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
        logger.info(f"🔍 DETAILED: Starting audio analysis for job {job_id}")
        logger.info(f"🔍 DETAILED: audio_url={audio_url}")
        logger.info(f"🔍 DETAILED: job_id type={type(job_id)}, value={job_id}")
        
        if not job_id:
            raise ValidationError("job_id is required", job_id=job_id)
        
        if not audio_url:
            raise ValidationError("audio_url is required", job_id=job_id)
        
        # 2. Try to extract hash from URL to check cache before downloading
        file_hash = extract_hash_from_url(audio_url)
        if file_hash:
            logger.info(f"Extracted hash from URL: {file_hash}")
            # Check cache first before downloading
            cached_analysis = await get_cached_analysis(file_hash)
            if cached_analysis is not None:
                logger.info(f"Cache hit for job {job_id}, file_hash={file_hash} (before download)")
                # Update metadata to indicate cache hit
                cached_analysis.metadata["cache_hit"] = True
                cached_analysis.metadata["processing_time"] = time.time() - start_time
                cached_analysis.job_id = job_id  # Update job_id in case of cache hit
                return cached_analysis
        
        # 3. Download audio file (cache miss or hash not in URL)
        logger.info(f"Downloading audio file for job {job_id}")
        audio_bytes = await download_audio_file(audio_url)
        
        # 4. Calculate MD5 hash of audio file bytes (if not already extracted from URL)
        if not file_hash:
            file_hash = calculate_file_hash(audio_bytes)
            logger.info(f"Calculated file hash: {file_hash}")
            
            # Check cache again after calculating hash (in case hash wasn't in URL)
            cached_analysis = await get_cached_analysis(file_hash)
            if cached_analysis is not None:
                logger.info(f"Cache hit for job {job_id}, file_hash={file_hash} (after download)")
                # Update metadata to indicate cache hit
                cached_analysis.metadata["cache_hit"] = True
                cached_analysis.metadata["processing_time"] = time.time() - start_time
                cached_analysis.job_id = job_id  # Update job_id in case of cache hit
                return cached_analysis
        
        # 5. Validate audio file
        logger.info(f"Validating audio file for job {job_id}")
        validate_audio_file_bytes(audio_bytes, max_size_mb=10)
        
        # 6. Call parse_audio function
        logger.info(f"🔍 DETAILED: About to call parse_audio for job {job_id}")
        logger.info(f"🔍 DETAILED: audio_bytes size={len(audio_bytes)} bytes")
        analysis = await parse_audio(audio_bytes, job_id)
        logger.info(f"🔍 DETAILED: parse_audio returned, type={type(analysis)}")
        logger.info(f"🔍 DETAILED: analysis.bpm={analysis.bpm}, analysis.duration={analysis.duration}")
        logger.info(f"🔍 DETAILED: analysis.beat_timestamps count={len(analysis.beat_timestamps)}")
        
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
        analysis.metadata["cache_hit"] = False  # Mark as cache miss since we processed
        
        logger.info(
            f"✅ DETAILED: Audio analysis complete for job {job_id}: "
            f"duration={analysis.duration:.2f}s, processing_time={processing_time:.2f}s"
        )
        logger.info(f"🔍 DETAILED: Final analysis summary:")
        logger.info(f"  - BPM: {analysis.bpm}")
        logger.info(f"  - Duration: {analysis.duration}s")
        logger.info(f"  - Beats: {len(analysis.beat_timestamps)}")
        logger.info(f"  - First 5 beats: {analysis.beat_timestamps[:5]}")
        logger.info(f"  - Last 5 beats: {analysis.beat_timestamps[-5:]}")
        logger.info(f"  - Structure segments: {len(analysis.song_structure)}")
        logger.info(f"  - Mood: {analysis.mood}")
        
        return analysis
        
    except ValidationError:
        raise
    except AudioAnalysisError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in audio analysis for job {job_id}: {str(e)}")
        raise AudioAnalysisError(f"Failed to process audio analysis: {str(e)}", job_id=job_id) from e


async def get_cached_analysis_by_hash(file_hash: str) -> Optional[AudioAnalysis]:
    """
    Get cached analysis by file hash (utility function).
    
    Args:
        file_hash: MD5 hash of audio file
        
    Returns:
        AudioAnalysis if found, None otherwise
    """
    return await get_cached_analysis(file_hash)

