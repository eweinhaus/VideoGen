"""
Lyrics extraction component.

Extract lyrics with word-level timestamps using OpenAI Whisper API.
Includes formatting into sentences/phrases and confidence scoring.
"""

import io
import tempfile
import re
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
        
        # 3. Parse response and extract raw words
        raw_words = []
        if hasattr(response, 'words') and response.words:
            for word in response.words:
                raw_words.append({
                    'text': word.word,
                    'timestamp': word.start,
                    'end': getattr(word, 'end', word.start + 0.5)  # Estimate end if not available
                })
        elif hasattr(response, 'text') and response.text:
            # Fallback: If word-level timestamps not available, use full text at start
            raw_words.append({
                'text': response.text,
                'timestamp': 0.0,
                'end': duration if duration > 0 else 1.0
            })
        
        # 4. Format lyrics into sentences/phrases and calculate confidence
        lyrics = _format_and_score_lyrics(raw_words, duration)
        
        # 5. Track cost after success
        from decimal import Decimal
        actual_cost = Decimal(str((duration / 60.0) * 0.006))
        await cost_tracker.track_cost(
            str(job_id),
            "audio_parser",
            "whisper",
            actual_cost
        )
        
        logger.info(
            f"Extracted {len(lyrics)} lyrics for job {job_id} "
            f"(avg confidence: {sum(l.confidence or 0.5 for l in lyrics) / len(lyrics) if lyrics else 0:.2f})"
        )
        return lyrics
        
    except BudgetExceededError:
        raise
    except Exception as e:
        logger.warning(f"Lyrics extraction failed for job {job_id}: {str(e)}, using fallback")
        # Fallback: Return empty lyrics array (instrumental tracks are valid)
        return []


def _format_and_score_lyrics(raw_words: List[dict], duration: float) -> List[Lyric]:
    """
    Format raw words into sentences/phrases and calculate confidence scores.
    
    Args:
        raw_words: List of dicts with 'text', 'timestamp', 'end'
        duration: Total audio duration in seconds
        
    Returns:
        List of Lyric objects with formatted_text and confidence
    """
    if not raw_words:
        return []
    
    # Group words into sentences/phrases
    formatted_phrases = _group_words_into_phrases(raw_words)
    
    # Calculate overall confidence metrics
    coverage = _calculate_coverage(raw_words, duration)
    word_validity = _calculate_word_validity(raw_words)
    gap_analysis = _analyze_gaps(raw_words, duration)
    
    # Overall confidence (weighted average)
    overall_confidence = (
        coverage * 0.4 +  # Coverage is most important
        word_validity * 0.3 +  # Word validity matters
        gap_analysis * 0.3  # Gap analysis indicates completeness
    )
    
    # Create Lyric objects with formatted text
    lyrics = []
    for word_data, phrase_text in zip(raw_words, formatted_phrases):
        # Individual word confidence (can be adjusted based on word characteristics)
        word_confidence = overall_confidence
        if len(word_data['text']) < 2:  # Very short words might be less reliable
            word_confidence *= 0.9
        if not word_data['text'].isalnum() and word_data['text'] not in [',', '.', '!', '?', "'", '-']:
            word_confidence *= 0.95
        
        lyrics.append(Lyric(
            text=word_data['text'],
            timestamp=word_data['timestamp'],
            confidence=round(word_confidence, 3),
            formatted_text=phrase_text
        ))
    
    return lyrics


def _group_words_into_phrases(raw_words: List[dict]) -> List[str]:
    """
    Group individual words into sentences/phrases.
    
    Detects sentence boundaries by:
    - Punctuation (., !, ?) at end of words
    - Time gaps (>1.5s between words)
    - Capitalization patterns after punctuation
    
    Args:
        raw_words: List of word dicts with 'text' and 'timestamp'
        
    Returns:
        List of formatted phrase strings (one per word, but phrases repeat for words in same phrase)
    """
    if not raw_words:
        return []
    
    phrases = []
    current_phrase = []
    
    for i, word_data in enumerate(raw_words):
        text = word_data['text'].strip()
        timestamp = word_data['timestamp']
        
        # Add word to current phrase
        current_phrase.append(text)
        
        # Check if we should finalize current phrase and start new one
        should_break = False
        
        # Break on punctuation at end of word
        if text and text[-1] in '.!?':
            should_break = True
        
        # Break on large time gaps (>1.5s) - check next word if exists
        if i < len(raw_words) - 1:
            next_timestamp = raw_words[i + 1]['timestamp']
            time_gap = next_timestamp - timestamp
            if time_gap > 1.5:
                should_break = True
        
        # Break on capitalization after punctuation (new sentence starting)
        if i < len(raw_words) - 1:
            next_text = raw_words[i + 1]['text'].strip()
            if text and text[-1] in '.!?' and next_text and next_text[0].isupper():
                should_break = True
        
        if should_break:
            # Finalize current phrase
            phrase_text = ' '.join(current_phrase)
            # Add phrase text to all words in the phrase
            for _ in range(len(current_phrase)):
                phrases.append(phrase_text)
            current_phrase = []
    
    # Handle remaining phrase
    if current_phrase:
        phrase_text = ' '.join(current_phrase)
        for _ in range(len(current_phrase)):
            phrases.append(phrase_text)
    
    return phrases


def _calculate_coverage(raw_words: List[dict], duration: float) -> float:
    """
    Calculate how well lyrics cover the audio duration.
    
    Args:
        raw_words: List of word dicts
        duration: Total audio duration
        
    Returns:
        Coverage score 0-1 (1.0 = perfect coverage)
    """
    if not raw_words or duration <= 0:
        return 0.0
    
    # Calculate total time covered by words
    # Estimate average word duration (0.3s per word is reasonable)
    avg_word_duration = 0.3
    total_words = len(raw_words)
    estimated_coverage = total_words * avg_word_duration
    
    # Coverage ratio (cap at 1.0)
    coverage_ratio = min(estimated_coverage / duration, 1.0)
    
    # For songs with lyrics, we expect at least 30% coverage
    # Scale so that 30% coverage = 0.5 confidence, 60%+ = 1.0 confidence
    if coverage_ratio < 0.3:
        return coverage_ratio / 0.6  # Scale 0-0.3 to 0-0.5
    else:
        return 0.5 + (coverage_ratio - 0.3) / 0.6 * 0.5  # Scale 0.3-1.0 to 0.5-1.0


def _calculate_word_validity(raw_words: List[dict]) -> float:
    """
    Calculate confidence based on word validity.
    
    Args:
        raw_words: List of word dicts
        
    Returns:
        Validity score 0-1
    """
    if not raw_words:
        return 0.0
    
    valid_count = 0
    total_count = len(raw_words)
    
    for word_data in raw_words:
        text = word_data['text'].strip()
        
        # Valid word criteria:
        # - Has reasonable length (1-20 chars)
        # - Contains alphanumeric characters or common punctuation
        # - Not just punctuation
        
        if 1 <= len(text) <= 20:
            # Check if it's a valid word (has letters/numbers or is punctuation)
            has_alnum = any(c.isalnum() for c in text)
            is_punctuation = text in [',', '.', '!', '?', "'", '-', ':', ';', '"']
            
            if has_alnum or is_punctuation:
                valid_count += 1
    
    return valid_count / total_count if total_count > 0 else 0.0


def _analyze_gaps(raw_words: List[dict], duration: float) -> float:
    """
    Analyze time gaps between words to assess completeness.
    
    Large gaps might indicate missing words.
    
    Args:
        raw_words: List of word dicts
        duration: Total audio duration
        
    Returns:
        Gap analysis score 0-1 (1.0 = few/small gaps, 0.0 = many/large gaps)
    """
    if len(raw_words) < 2:
        return 1.0 if raw_words else 0.0
    
    gaps = []
    for i in range(1, len(raw_words)):
        gap = raw_words[i]['timestamp'] - raw_words[i-1]['timestamp']
        if gap > 0:  # Only positive gaps
            gaps.append(gap)
    
    if not gaps:
        return 1.0
    
    # Calculate average gap
    avg_gap = sum(gaps) / len(gaps)
    
    # Count large gaps (>2s might indicate missing words)
    large_gaps = sum(1 for gap in gaps if gap > 2.0)
    large_gap_ratio = large_gaps / len(gaps)
    
    # Score: prefer smaller average gaps and fewer large gaps
    # Average gap of 0.5s = good (1.0), 2.0s = moderate (0.5), 4.0s+ = poor (0.0)
    avg_gap_score = max(0.0, 1.0 - (avg_gap - 0.5) / 3.5)
    
    # Large gap penalty
    large_gap_penalty = large_gap_ratio * 0.3
    
    return max(0.0, avg_gap_score - large_gap_penalty)


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

