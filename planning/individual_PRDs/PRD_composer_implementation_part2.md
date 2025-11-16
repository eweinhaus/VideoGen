# Module 8: Composer - Implementation Part 2: Advanced Steps

**Version:** 1.0  
**Date:** November 15, 2025  
**Status:** Ready for Implementation  
**Dependencies:** PRD_composer_overview.md, PRD_composer_implementation_part1.md

**Related Documents:**
- `PRD_composer_operations.md` - Error handling, optimizations, edge cases

---

## Implementation Overview

This document covers Steps 5-8 of the Composer implementation: transitions, audio sync, final encoding, upload, plus the main process function, configuration, and utilities.

---

## Step 5: Apply Transitions (MVP: Cuts Only)

**Location:** `transition_applier.py`

**Purpose:** Apply transitions between clips (MVP: simple cuts).

**Implementation:**
```python
from pathlib import Path
from typing import List
from shared.errors import CompositionError
from shared.logging import get_logger

logger = get_logger("composer.transition_applier")

async def apply_transitions(
    clip_paths: List[Path],
    transitions: List[Transition],
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """
    Apply transitions between clips (MVP: cuts only).
    
    Args:
        clip_paths: List of normalized clip paths (in order)
        transitions: List of transition definitions
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to concatenated video with transitions
    """
    # MVP: Simple concatenation (cuts only)
    # Create concat file for FFmpeg
    concat_file = temp_dir / "clips_concat.txt"
    with open(concat_file, "w") as f:
        for clip_path in clip_paths:
            f.write(f"file '{clip_path.absolute()}\n")
    
    output_path = temp_dir / "clips_concatenated.mp4"
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",  # Stream copy (fast, no re-encoding)
        "-y",
        str(output_path)
    ]
    
    logger.info(
        f"Concatenating {len(clip_paths)} clips with cuts",
        extra={"job_id": str(job_id), "clip_count": len(clip_paths)}
    )
    
    # Run FFmpeg (wrap in executor for async)
    process = await asyncio.create_subprocess_exec(
        *ffmpeg_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
    
    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
        raise CompositionError(f"FFmpeg concatenation failed: {error_msg}")
    
    return output_path
```

**Post-MVP:** Add crossfade/fade transitions using `xfade` filter.

---

## Step 6: Sync Audio

**Location:** `audio_syncer.py`

**Purpose:** Sync original audio with video.

**Required Imports:**
```python
import asyncio
from pathlib import Path
from uuid import UUID
from shared.errors import CompositionError
from shared.logging import get_logger
from .utils import run_ffmpeg_command, get_video_duration, get_audio_duration

logger = get_logger("composer.audio_syncer")

async def sync_audio(
    video_path: Path,
    audio_bytes: bytes,
    temp_dir: Path,
    job_id: UUID
) -> tuple[Path, float]:
    """
    Sync audio with video.
    
    Args:
        video_path: Path to video file (without audio)
        audio_bytes: Original audio file bytes
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Tuple of (output_path, sync_drift)
    """
    # Write audio to temp file
    # Note: Audio format is assumed to be MP3, but FFmpeg handles other formats (WAV, M4A, etc.)
    audio_path = temp_dir / "audio.mp3"
    audio_path.write_bytes(audio_bytes)
    
    output_path = temp_dir / "video_with_audio.mp4"
    
    # FFmpeg command: combine video + audio, use -shortest to match durations
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",  # Copy video (no re-encoding)
        "-c:a", "aac",   # Encode audio to AAC
        "-b:a", "192k",  # Audio bitrate
        "-shortest",     # Match to shortest stream (handles duration mismatch)
        "-y",
        str(output_path)
    ]
    
    logger.info("Syncing audio with video", extra={"job_id": str(job_id)})
    
    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
    
    if not output_path.exists():
        raise CompositionError(f"Video with audio not created: {output_path}")
    
    # Measure sync drift (use ffprobe to get durations)
    video_duration = await get_video_duration(output_path)
    audio_duration = await get_audio_duration(audio_path)
    sync_drift = abs(video_duration - audio_duration)
    
    logger.info(
        f"Audio synced (drift: {sync_drift:.3f}s)",
        extra={"job_id": str(job_id), "sync_drift": sync_drift}
    )
    
    return output_path, sync_drift
```

**MVP Simplification:** Use `-shortest` flag, report drift (don't adjust).

---

## Step 7: Encode Final Video

**Location:** `encoder.py`

**Purpose:** Encode final MP4 with H.264/AAC at 5000k bitrate.

**Required Imports:**
```python
from pathlib import Path
from uuid import UUID
from shared.errors import CompositionError
from shared.logging import get_logger
from .utils import run_ffmpeg_command

logger = get_logger("composer.encoder")

async def encode_final_video(
    video_path: Path,
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """
    Encode final video with H.264/AAC at 5000k bitrate.
    
    Args:
        video_path: Path to video with audio
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to final encoded video
    """
    output_path = temp_dir / "final_video.mp4"
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-threads", "4",
        "-i", str(video_path),
        "-c:v", "libx264",      # H.264 codec
        "-c:a", "aac",          # AAC codec
        "-b:v", "5000k",        # Video bitrate
        "-b:a", "192k",         # Audio bitrate
        "-preset", "medium",    # Encoding preset
        "-movflags", "+faststart",  # Web optimization
        "-y",
        str(output_path)
    ]
    
    logger.info("Encoding final video", extra={"job_id": str(job_id)})
    
    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
    
    # Validate output
    if not output_path.exists():
        raise CompositionError("Final video not created")
    
    output_size = output_path.stat().st_size
    if output_size < 1024:  # Less than 1KB is suspicious
        raise CompositionError(f"Final video too small: {output_size} bytes")
    
    # Validate video properties (optional but recommended)
    from .utils import get_video_duration
    video_duration = await get_video_duration(output_path)
    if video_duration <= 0:
        raise CompositionError(f"Invalid video duration: {video_duration}s")
    
    logger.info(
        f"Final video encoded ({output_size / 1024 / 1024:.2f} MB)",
        extra={"job_id": str(job_id), "size_mb": output_size / 1024 / 1024}
    )
    
    return output_path
```

---

## Step 8: Upload Final Video

**Location:** `process.py` (end of `process()` function)

**Purpose:** Upload final video to Supabase Storage.

**Implementation:**
```python
from shared.storage import StorageClient
from pathlib import Path
from .config import VIDEO_OUTPUTS_BUCKET

storage = StorageClient()

# Read final video
final_video_bytes = final_video_path.read_bytes()

# Upload to Supabase Storage
storage_path = f"{job_id}/final_video.mp4"
video_url = await storage.upload_file(
    bucket=VIDEO_OUTPUTS_BUCKET,
    path=storage_path,
    file_data=final_video_bytes,
    content_type="video/mp4"
)

logger.info(
    f"Uploaded final video to {video_url}",
    extra={"job_id": str(job_id), "url": video_url}
)
```

---

## Main Process Function

**Location:** `process.py`

**Required Imports:**
```python
import asyncio
import time
import tempfile
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
from typing import List, Optional
from decimal import Decimal
from shared.errors import CompositionError, RetryableError
from shared.logging import get_logger
from shared.storage import StorageClient
from shared.models.video import VideoOutput, Clips, Clip
from shared.models.scene import Transition
from api_gateway.services.sse_manager import publish_event
from .config import VIDEO_OUTPUTS_BUCKET
from .downloader import download_all_clips, download_audio
from .normalizer import normalize_clip
from .duration_handler import handle_clip_duration
from .transition_applier import apply_transitions
from .audio_syncer import sync_audio
from .encoder import encode_final_video
from .utils import get_video_duration, check_ffmpeg_available

logger = get_logger("composer.process")
```

**Temp Directory Context Manager:**
```python
@asynccontextmanager
async def temp_directory(prefix: str):
    """Context manager for temporary directory with automatic cleanup."""
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
```

**Implementation Flow:**
1. Check FFmpeg availability (Step 1)
2. Validate inputs (minimum 3 clips, all have video_url, audio_url present, sequential indices)
3. Sort clips by clip_index
4. Create temp directory (context manager)
5. Publish progress: "Downloading clips..."
6. Download clips and audio (parallel)
7. Publish progress: "Normalizing clips..."
8. Normalize all clips to 1080p, 30fps
9. Publish progress: "Handling duration mismatches..."
10. Handle duration mismatches (trim/loop)
11. Publish progress: "Applying transitions..."
12. Apply transitions (concatenate with cuts)
13. Publish progress: "Syncing audio..."
14. Sync audio with video
15. Publish progress: "Encoding final video..."
16. Encode final video (H.264/AAC, 5000k bitrate)
17. Publish progress: "Uploading final video..."
18. Upload to Supabase Storage
19. Calculate metrics and return VideoOutput
20. Cleanup temp directory (automatic via context manager)

**Progress Publishing Helper:**
```python
async def publish_progress(job_id: UUID, message: str):
    """Publish progress event via SSE."""
    await publish_event(job_id, "message", {
        "text": message,
        "stage": "composer"
    })
```

**Main Function Structure:**
```python
async def process(
    job_id: str,  # Note: Orchestrator passes string, convert to UUID internally
    clips: Clips,
    audio_url: str,
    transitions: List[Transition],
    beat_timestamps: Optional[List[float]] = None
) -> VideoOutput:
    """
    Main composition function.
    
    Note: job_id is accepted as string (from orchestrator) but converted to UUID internally.
    """
    # Convert job_id to UUID for internal use
    job_id_uuid = UUID(job_id) if isinstance(job_id, str) else job_id
    start_time = time.time()
    
    # Step 1: Validation (includes FFmpeg check)
    if not check_ffmpeg_available():
        raise CompositionError(
            "FFmpeg not found. Please install FFmpeg:\n"
            "  macOS: brew install ffmpeg\n"
            "  Linux: apt-get install ffmpeg or yum install ffmpeg\n"
            "  Windows: Download from https://ffmpeg.org/"
        )
    
    if len(clips.clips) < 3:
        raise CompositionError("Minimum 3 clips required for composition")
    
    for clip in clips.clips:
        if not clip.video_url:
            raise CompositionError(f"Clip {clip.clip_index} missing video_url")
        if clip.status != "success":
            raise CompositionError(f"Clip {clip.clip_index} has status '{clip.status}', expected 'success'")
    
    if not audio_url:
        raise CompositionError("Audio URL required for composition")
    
    sorted_clips = sorted(clips.clips, key=lambda c: c.clip_index)
    
    # Validate sequential indices
    for i, clip in enumerate(sorted_clips):
        if clip.clip_index != i:
            raise CompositionError(
                f"Clip indices must be sequential starting from 0. "
                f"Found index {clip.clip_index} at position {i}"
            )
    
    # Step 2-8: Processing with temp directory context manager
    async with temp_directory(f"composer_{job_id_uuid}_") as temp_dir:
        # Step 2: Download
        await publish_progress(job_id_uuid, f"Downloading clips ({len(sorted_clips)} clips)...")
        clip_bytes_list = await download_all_clips(sorted_clips, job_id_uuid)
        audio_bytes = await download_audio(audio_url, job_id_uuid)
        
        # Step 3: Normalize
        await publish_progress(job_id_uuid, "Normalizing clips to 1080p, 30fps...")
        normalized_paths = []
        for clip_bytes, clip in zip(clip_bytes_list, sorted_clips):
            normalized_path = await normalize_clip(clip_bytes, clip.clip_index, temp_dir, job_id_uuid)
            normalized_paths.append(normalized_path)
        
        # Step 4: Handle durations
        await publish_progress(job_id_uuid, "Handling duration mismatches...")
        duration_handled_paths = []
        clips_trimmed = 0
        clips_looped = 0
        for normalized_path, clip in zip(normalized_paths, sorted_clips):
            result = await handle_clip_duration(normalized_path, clip, temp_dir, job_id_uuid)
            duration_handled_paths.append(result.path)
            if result.was_trimmed:
                clips_trimmed += 1
            if result.was_looped:
                clips_looped += 1
        
        # Step 5: Apply transitions
        await publish_progress(job_id_uuid, "Applying transitions...")
        concatenated_path = await apply_transitions(duration_handled_paths, transitions, temp_dir, job_id_uuid)
        
        # Step 6: Sync audio
        await publish_progress(job_id_uuid, "Syncing audio with video...")
        video_with_audio_path, sync_drift = await sync_audio(concatenated_path, audio_bytes, temp_dir, job_id_uuid)
        
        # Step 7: Encode
        await publish_progress(job_id_uuid, "Encoding final video...")
        final_video_path = await encode_final_video(video_with_audio_path, temp_dir, job_id_uuid)
        
        # Step 8: Upload
        await publish_progress(job_id_uuid, "Uploading final video...")
        storage = StorageClient()
        final_video_bytes = final_video_path.read_bytes()
        storage_path = f"{job_id_uuid}/final_video.mp4"
        video_url = await storage.upload_file(
            bucket=VIDEO_OUTPUTS_BUCKET,
            path=storage_path,
            file_data=final_video_bytes,
            content_type="video/mp4"
        )
        
        logger.info(
            f"Uploaded final video to {video_url}",
            extra={"job_id": str(job_id_uuid), "url": video_url}
        )
        
        # Calculate metrics before temp directory cleanup
        composition_time = time.time() - start_time
        final_video_duration = await get_video_duration(final_video_path)
        file_size_mb = final_video_path.stat().st_size / 1024 / 1024
        
        # Get audio duration from original audio if available (or calculate from clips)
        # For MVP, use sum of target durations as approximation
        audio_duration = sum(clip.target_duration for clip in sorted_clips)
    
    video_output = VideoOutput(
        job_id=job_id_uuid,
        video_url=video_url,
        duration=final_video_duration,
        audio_duration=audio_duration,
        sync_drift=sync_drift,
        clips_used=len(sorted_clips),
        clips_trimmed=clips_trimmed,
        clips_looped=clips_looped,
        transitions_applied=len(sorted_clips) - 1,  # N clips = N-1 transitions
        file_size_mb=file_size_mb,
        composition_time=composition_time,
        cost=Decimal("0.00"),  # No API calls, compute only
        status="success"
    )
    
    logger.info(
        f"Composition complete: {file_size_mb:.2f} MB, {composition_time:.2f}s",
        extra={
            "job_id": str(job_id_uuid),
            "file_size_mb": file_size_mb,
            "composition_time": composition_time,
            "clips_used": len(sorted_clips),
            "sync_drift": sync_drift
        }
    )
    
    return video_output
```

**Error Handling:**
- Temp directory cleanup is automatic via context manager (even on exceptions)
- Raise `CompositionError` for validation failures (permanent, don't retry)
- Raise `RetryableError` for transient failures (network, FFmpeg timeouts - will retry)
- All errors are logged with job_id for tracing
- Orchestrator handles error propagation and SSE events

**Exception Flow:**
```python
try:
    # ... composition steps ...
except CompositionError as e:
    # Permanent failure - log and re-raise
    logger.error(f"Composition failed: {e}", extra={"job_id": str(job_id_uuid)})
    raise
except RetryableError as e:
    # Transient failure - log and re-raise (orchestrator will retry)
    logger.warning(f"Composition retryable error: {e}", extra={"job_id": str(job_id_uuid)})
    raise
except Exception as e:
    # Unexpected error - wrap in CompositionError
    logger.error(f"Unexpected composition error: {e}", exc_info=True, extra={"job_id": str(job_id_uuid)})
    raise CompositionError(f"Unexpected error during composition: {e}") from e
```

---

## Configuration

**Location:** `config.py`

```python
# Storage bucket names
VIDEO_CLIPS_BUCKET = "video-clips"
VIDEO_OUTPUTS_BUCKET = "video-outputs"
AUDIO_UPLOADS_BUCKET = "audio-uploads"

# FFmpeg settings
FFMPEG_THREADS = 4
FFMPEG_TIMEOUT = 300  # 5 minutes
FFMPEG_PRESET = "medium"  # Balance speed/quality
FFMPEG_CRF = 23  # High quality

# Video output settings
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
OUTPUT_FPS = 30
OUTPUT_VIDEO_BITRATE = "5000k"
OUTPUT_AUDIO_BITRATE = "192k"
OUTPUT_VIDEO_CODEC = "libx264"
OUTPUT_AUDIO_CODEC = "aac"

# Duration handling
DURATION_TOLERANCE = 0.5  # 0.5s tolerance for duration matching
```

---

## Utility Functions

**Location:** `utils.py`

**Required Imports:**
```python
import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List
from uuid import UUID
from shared.errors import CompositionError, RetryableError
from shared.retry import retry_with_backoff
from shared.logging import get_logger

logger = get_logger("composer.utils")
```

**Implementation:**
```python
def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is installed and available."""
    return shutil.which("ffmpeg") is not None

@retry_with_backoff(max_attempts=2, base_delay=2)
async def run_ffmpeg_command(
    cmd: List[str],
    job_id: UUID,
    timeout: int = 300
) -> None:
    """
    Run FFmpeg command with retry logic.
    
    Args:
        cmd: FFmpeg command as list
        job_id: Job ID for logging
        timeout: Timeout in seconds
        
    Raises:
        CompositionError: If command fails after retries
        RetryableError: If transient failure (will retry)
    """
    logger.info(
        f"Running FFmpeg command: {' '.join(cmd)}",
        extra={"job_id": str(job_id), "command": cmd}
    )
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            logger.error(
                f"FFmpeg command failed: {error_msg}",
                extra={"job_id": str(job_id), "error": error_msg, "command": cmd}
            )
            # All FFmpeg errors are retryable (system load, disk I/O, etc.)
            raise RetryableError(f"FFmpeg command failed: {error_msg}")
        
    except asyncio.TimeoutError:
        raise RetryableError(f"FFmpeg command timeout after {timeout}s")
    except RetryableError:
        raise  # Re-raise for retry logic
    except Exception as e:
        raise CompositionError(f"FFmpeg command failed: {e}") from e

async def get_video_duration(video_path: Path) -> float:
    """
    Get video duration using ffprobe. Reuse pattern from video_generator.
    
    Returns duration in seconds, falls back to 5.0 if fails.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        duration = float(result.stdout.strip())
        return duration
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError, asyncio.TimeoutError) as e:
        logger.warning(f"Failed to get video duration: {e}, using estimate")
        return 5.0  # Default estimate

async def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration using ffprobe (same as get_video_duration)."""
    return await get_video_duration(audio_path)
```

---

**Next:** Review `PRD_composer_operations.md` for error handling, optimizations, and edge cases.

