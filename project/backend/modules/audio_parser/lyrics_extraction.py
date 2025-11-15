"""
Lyrics extraction component.

Extract lyrics with word-level timestamps using OpenAI Whisper API.
"""

import io
import tempfile
from typing import List
from uuid import UUID
from openai import AsyncOpenAI
from shared.models.audio import Lyric
from shared.cost_tracking import CostTracker
from shared.errors import BudgetExceededError, RetryableError
from shared.retry import retry_with_backoff
from shared.config import settings
from shared.logging import get_logger
from api_gateway.services.budget_helpers import get_budget_limit

logger = get_logger("audio_parser")

cost_tracker = CostTracker()


async def extract_lyrics(
    audio_bytes: bytes,
    job_id: UUID,
    duration: float
) -> List[Lyric]:
    """
    Extract lyrics from audio using Whisper API.
    
    Args:
        audio_bytes: Audio file bytes
        job_id: Job ID for cost tracking
        duration: Audio duration in seconds
        
    Returns:
        List of Lyric objects with text and timestamp
    """
    try:
        # 1. Budget check before API call
        from decimal import Decimal
        estimated_cost = Decimal(str((duration / 60.0) * 0.006))
        # Get environment from settings (defaults to "development")
        environment = getattr(settings, 'environment', 'development') or 'development'
        budget_limit = get_budget_limit(environment)
        
        can_proceed = await cost_tracker.check_budget(
            str(job_id),
            estimated_cost,
            limit=budget_limit
        )
        
        if not can_proceed:
            logger.warning(f"Budget exceeded before Whisper API call for job {job_id}")
            raise BudgetExceededError(
                f"Budget exceeded before Whisper API call (estimated cost: ${estimated_cost:.4f})",
                job_id=job_id
            )
        
        # 2. Call Whisper API with retry
        response = await _call_whisper_api(audio_bytes)
        
        # 3. Parse response
        lyrics = []
        if hasattr(response, 'words') and response.words:
            for word in response.words:
                lyrics.append(Lyric(
                    text=word.word,
                    timestamp=word.start
                ))
        elif hasattr(response, 'text') and response.text:
            # Fallback: If word-level timestamps not available, use full text at start
            lyrics.append(Lyric(
                text=response.text,
                timestamp=0.0
            ))
        
        # 4. Track cost after success
        from decimal import Decimal
        actual_cost = Decimal(str((duration / 60.0) * 0.006))
        await cost_tracker.track_cost(
            str(job_id),
            "audio_parser",
            "whisper",
            actual_cost
        )
        
        logger.info(f"Extracted {len(lyrics)} lyrics for job {job_id}")
        return lyrics
        
    except BudgetExceededError:
        raise
    except Exception as e:
        logger.warning(f"Lyrics extraction failed for job {job_id}: {str(e)}, using fallback")
        # Fallback: Return empty lyrics array (instrumental tracks are valid)
        return []


@retry_with_backoff(max_attempts=3, base_delay=2)
async def _call_whisper_api(audio_bytes: bytes):
    """
    Call Whisper API with retry logic.
    
    Note: @retry_with_backoff decorator fully supports async functions.
    
    Args:
        audio_bytes: Audio file bytes
        
    Returns:
        Whisper API response
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    try:
        # Create temporary file for audio
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_file_path = tmp_file.name
        
        try:
            # Call Whisper API
            with open(tmp_file_path, 'rb') as f:
                response = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            return response
        finally:
            # Clean up temporary file
            import os
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass
                
    except Exception as e:
        error_str = str(e).lower()
        # Convert API errors to RetryableError for retry decorator
        if "rate limit" in error_str or "timeout" in error_str or "429" in error_str:
            raise RetryableError(f"Whisper API error: {str(e)}") from e
        raise

