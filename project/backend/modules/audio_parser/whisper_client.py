"""
OpenAI Whisper API integration with retry logic.

Extract lyrics with word-level timestamps using Whisper API.
"""

import tempfile
import os
from decimal import Decimal
from typing import List
from uuid import UUID

from openai import OpenAI
from shared.config import settings
from shared.errors import RetryableError
from shared.logging import get_logger
from shared.retry import retry_with_backoff
from shared.models.audio import Lyric
from shared.cost_tracking import cost_tracker

logger = get_logger("audio_parser")

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.openai_api_key)


def _calculate_whisper_cost(duration_seconds: float) -> Decimal:
    """
    Calculate Whisper API cost.
    
    Args:
        duration_seconds: Audio duration in seconds
        
    Returns:
        Cost in USD
    """
    # $0.006 per minute
    cost_per_minute = Decimal("0.006")
    minutes = Decimal(str(duration_seconds)) / Decimal("60.0")
    return minutes * cost_per_minute


async def _extract_lyrics_internal(audio_bytes: bytes, job_id: UUID, duration_seconds: float) -> List[Lyric]:
    """
    Internal function to extract lyrics (wrapped with retry decorator).
    """
    temp_file = None
    try:
        # 1. Prepare audio file
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        temp_file.write(audio_bytes)
        temp_file.flush()
        temp_file.close()
        
        logger.info(f"Created temporary audio file: {temp_file.name}")
        
        # 2. Call Whisper API (synchronous call wrapped in executor for async compatibility)
        import asyncio
        loop = asyncio.get_event_loop()
        
        def _call_whisper():
            with open(temp_file.name, 'rb') as audio_file:
                return openai_client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1",
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
        
        response = await loop.run_in_executor(None, _call_whisper)
        
        logger.info(f"Whisper API response received: {len(response.words) if hasattr(response, 'words') else 0} words")
        
        # 3. Process response
        lyrics = []
        if hasattr(response, 'words') and response.words:
            for word_data in response.words:
                word_text = word_data.get('word', '').strip()
                word_start = word_data.get('start', 0.0)
                
                # Filter out empty words
                if word_text:
                    lyrics.append(Lyric(
                        text=word_text,
                        timestamp=float(word_start)
                    ))
        
        logger.info(f"Extracted {len(lyrics)} lyrics from audio")
        
        # 4. Track cost
        cost = _calculate_whisper_cost(duration_seconds)
        await cost_tracker.track_cost(
            job_id=job_id,
            stage_name="audio_analysis",
            api_name="whisper",
            cost=cost
        )
        logger.info(f"Tracked Whisper API cost: ${cost} for {duration_seconds:.2f}s audio")
        
        return lyrics
        
    except Exception as e:
        logger.error(f"Whisper API call failed: {str(e)}", extra={"job_id": str(job_id)})
        raise RetryableError(f"Failed to extract lyrics: {str(e)}") from e
        
    finally:
        # 5. Cleanup: Delete temporary file
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
                logger.debug(f"Deleted temporary file: {temp_file.name}")
            except Exception as e:
                logger.warning(f"Failed to delete temporary file: {str(e)}")


@retry_with_backoff(max_attempts=3, base_delay=2)
async def extract_lyrics(audio_bytes: bytes, job_id: UUID, duration_seconds: float) -> List[Lyric]:
    """
    Extract lyrics with word-level timestamps using Whisper API.
    
    Wrapped with retry decorator for automatic retry on failures.
    Returns empty list on permanent failure after retries.
    
    Args:
        audio_bytes: Audio file bytes
        job_id: Job ID for cost tracking
        duration_seconds: Audio duration in seconds
        
    Returns:
        List of Lyric objects with timestamps (empty list on failure)
    """
    try:
        lyrics = await _extract_lyrics_internal(audio_bytes, job_id, duration_seconds)
        return lyrics
    except Exception as e:
        logger.warning(
            f"Whisper API call failed after retries: {str(e)}, returning empty lyrics",
            extra={"job_id": str(job_id)}
        )
        # Return empty lyrics on permanent failure (instrumental track or API error)
        return []

