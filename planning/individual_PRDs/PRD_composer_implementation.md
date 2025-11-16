# Module 8: Composer - Implementation Part 1: Core Steps

**Version:** 1.0  
**Date:** November 15, 2025  
**Status:** Ready for Implementation  
**Dependencies:** PRD_composer_overview.md

**Related Documents:**
- `PRD_composer_implementation_part2.md` - Steps 5-8, main function, configuration
- `PRD_composer_operations.md` - Error handling, optimizations, edge cases

---

## Implementation Overview

This document covers Steps 1-4 of the Composer implementation: input validation, file downloads, clip normalization, and duration handling.

---

## Module Structure

```
modules/composer/
├── __init__.py          # Module exports
├── process.py           # Main entry point (process function)
├── config.py           # Configuration constants
├── utils.py            # Utility functions (URL parsing, duration extraction)
├── downloader.py      # File download logic
├── normalizer.py       # Clip normalization (upscale, FPS)
├── duration_handler.py # Duration handling (trim, loop)
├── transition_applier.py # Transition application
├── audio_syncer.py    # Audio synchronization
├── encoder.py          # Final video encoding
└── tests/              # Test suite
    ├── test_process.py
    ├── test_downloader.py
    ├── test_normalizer.py
    └── ...
```

---

## Core Implementation Steps

### Step 1: Input Validation & FFmpeg Check

**Location:** `process.py` (start of `process()` function)

**Purpose:** Fail fast with clear error messages before expensive operations.

**Required Imports:**
```python
from uuid import UUID
from typing import List, Optional
from pathlib import Path
from shared.errors import CompositionError
from shared.models.video import Clips, Clip
from .utils import check_ffmpeg_available
```

**Implementation:**
```python
# Check FFmpeg availability first (critical dependency)
if not check_ffmpeg_available():
    raise CompositionError(
        "FFmpeg not found. Please install FFmpeg:\n"
        "  macOS: brew install ffmpeg\n"
        "  Linux: apt-get install ffmpeg or yum install ffmpeg\n"
        "  Windows: Download from https://ffmpeg.org/"
    )

# Validate minimum clips
if len(clips.clips) < 3:
    raise CompositionError("Minimum 3 clips required for composition")

# Validate all clips have video_url and are successful
for clip in clips.clips:
    if not clip.video_url:
        raise CompositionError(f"Clip {clip.clip_index} missing video_url")
    if clip.status != "success":
        raise CompositionError(f"Clip {clip.clip_index} has status '{clip.status}', expected 'success'")

# Validate audio_url
if not audio_url:
    raise CompositionError("Audio URL required for composition")

# Sort clips by clip_index and validate sequential indices
sorted_clips = sorted(clips.clips, key=lambda c: c.clip_index)

# Validate clip indices are sequential (0, 1, 2, ...)
for i, clip in enumerate(sorted_clips):
    if clip.clip_index != i:
        raise CompositionError(
            f"Clip indices must be sequential starting from 0. "
            f"Found index {clip.clip_index} at position {i}"
        )
```

**Why:** Prevents wasted time on invalid inputs, clear error messages, ensures FFmpeg is available before starting.

---

### Step 2: Download Files (Parallel)

**Location:** `downloader.py`

**Purpose:** Download all clips and audio from Supabase Storage in parallel.

**Required Imports:**
```python
import asyncio
from typing import List
from uuid import UUID
from shared.storage import StorageClient
from modules.video_generator.image_handler import parse_supabase_url
from shared.errors import RetryableError
from shared.logging import get_logger
```

**Implementation:**
```python
logger = get_logger("composer.downloader")

async def download_all_clips(clips: List[Clip], job_id: UUID) -> List[bytes]:
    """
    Download all clips in parallel from Supabase Storage.
    
    Args:
        clips: List of Clip objects (already sorted by clip_index)
        job_id: Job ID for logging
        
    Returns:
        List of clip file bytes (in order)
        
    Raises:
        RetryableError: If download fails
    """
    storage = StorageClient()
    
    async def download_clip(clip: Clip) -> bytes:
        """Download single clip."""
        try:
            bucket, path = parse_supabase_url(clip.video_url)
            logger.info(
                f"Downloading clip {clip.clip_index} from {bucket}/{path}",
                extra={"job_id": str(job_id), "clip_index": clip.clip_index}
            )
            clip_bytes = await storage.download_file(bucket, path)
            
            # Validate file size (minimum 1KB, reasonable maximum 200MB)
            if len(clip_bytes) < 1024:
                raise RetryableError(f"Clip {clip.clip_index} file too small: {len(clip_bytes)} bytes")
            if len(clip_bytes) > 200 * 1024 * 1024:  # 200MB
                logger.warning(
                    f"Clip {clip.clip_index} is large: {len(clip_bytes) / 1024 / 1024:.2f} MB",
                    extra={"job_id": str(job_id), "clip_index": clip.clip_index, "size_mb": len(clip_bytes) / 1024 / 1024}
                )
            
            return clip_bytes
        except Exception as e:
            logger.error(
                f"Failed to download clip {clip.clip_index}: {e}",
                extra={"job_id": str(job_id), "clip_index": clip.clip_index, "error": str(e)}
            )
            raise RetryableError(f"Failed to download clip {clip.clip_index}: {e}") from e
    
    # Download all clips in parallel
    tasks = [download_clip(clip) for clip in clips]
    clip_bytes_list = await asyncio.gather(*tasks)
    
    logger.info(
        f"Downloaded {len(clip_bytes_list)} clips",
        extra={"job_id": str(job_id), "count": len(clip_bytes_list)}
    )
    
    return clip_bytes_list

async def download_audio(audio_url: str, job_id: UUID) -> bytes:
    """
    Download audio file from Supabase Storage.
    
    Args:
        audio_url: Audio file URL
        job_id: Job ID for logging
        
    Returns:
        Audio file bytes
        
    Raises:
        RetryableError: If download fails
    """
    storage = StorageClient()
    
    try:
        bucket, path = parse_supabase_url(audio_url)
        logger.info(
            f"Downloading audio from {bucket}/{path}",
            extra={"job_id": str(job_id)}
        )
        return await storage.download_file(bucket, path)
    except Exception as e:
        logger.error(
            f"Failed to download audio: {e}",
            extra={"job_id": str(job_id), "error": str(e)}
        )
        raise RetryableError(f"Failed to download audio: {e}") from e
```

**Performance:** 6 clips × 2s = 12s → 2s (10s savings with parallel)

---

### Step 3: Normalize Clips

**Location:** `normalizer.py`

**Purpose:** Upscale all clips to 1080p and normalize to 30 FPS.

**Required Imports:**
```python
import asyncio
from pathlib import Path
from uuid import UUID
from shared.errors import CompositionError, RetryableError
from shared.retry import retry_with_backoff
from shared.logging import get_logger
from shared.models.video import Clip
from .utils import run_ffmpeg_command
```

**Implementation:**
```python
logger = get_logger("composer.normalizer")

@retry_with_backoff(max_attempts=2, base_delay=2)
async def normalize_clip(
    clip_bytes: bytes,
    clip_index: int,
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """
    Normalize clip to 1080p, 30 FPS.
    
    Args:
        clip_bytes: Original clip file bytes
        clip_index: Clip index for naming
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to normalized clip file
        
    Raises:
        CompositionError: If normalization fails
    """
    # Write input clip to temp file
    input_path = temp_dir / f"clip_{clip_index}_input.mp4"
    output_path = temp_dir / f"clip_{clip_index}_normalized.mp4"
    
    input_path.write_bytes(clip_bytes)
    
    # FFmpeg command: upscale to 1080p, normalize to 30 FPS
    ffmpeg_cmd = [
        "ffmpeg",
        "-threads", "4",  # Use 4 threads for faster processing
        "-i", str(input_path),
        "-vf", "scale=1920:1080:flags=lanczos,fps=30",  # Upscale + FPS
        "-c:v", "libx264",
        "-preset", "medium",  # Balance speed/quality
        "-crf", "23",  # High quality
        "-y",  # Overwrite output
        str(output_path)
    ]
    
    logger.info(
        f"Normalizing clip {clip_index}",
        extra={"job_id": str(job_id), "clip_index": clip_index, "command": " ".join(ffmpeg_cmd)}
    )
    
    # Use shared FFmpeg utility function
    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
    
    # Validate output
    if not output_path.exists():
        raise CompositionError(f"Normalized clip not created: {output_path}")
    
    output_size = output_path.stat().st_size
    if output_size < 1024:  # Less than 1KB is suspicious
        raise CompositionError(f"Normalized clip too small: {output_size} bytes")
    
    logger.info(
        f"Normalized clip {clip_index} ({output_size / 1024 / 1024:.2f} MB)",
        extra={"job_id": str(job_id), "clip_index": clip_index, "size_mb": output_size / 1024 / 1024}
    )
    
    return output_path
```

**Note:** Import `asyncio` at top of file.

---

### Step 4: Handle Duration Mismatches

**Location:** `duration_handler.py`

**Purpose:** Trim clips if too long, loop clips if too short.

**Required Imports:**
```python
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from shared.errors import CompositionError
from shared.logging import get_logger
from shared.models.video import Clip
from .utils import run_ffmpeg_command

logger = get_logger("composer.duration_handler")

@dataclass
class DurationHandledClip:
    """Result of duration handling operation."""
    path: Path
    was_trimmed: bool
    was_looped: bool
```

**Implementation:**
```python
async def trim_clip(
    clip_path: Path,
    clip: Clip,
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """Trim clip to target duration."""
    output_path = temp_dir / f"clip_{clip.clip_index}_trimmed.mp4"
    
    logger.info(
        f"Trimming clip {clip.clip_index} from {clip.actual_duration:.2f}s to {clip.target_duration:.2f}s",
        extra={"job_id": str(job_id), "clip_index": clip.clip_index}
    )
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", str(clip_path),
        "-t", str(clip.target_duration),  # Trim to target duration
        "-c", "copy",  # Stream copy (fast, no re-encoding)
        "-y",
        str(output_path)
    ]
    
    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
    
    if not output_path.exists():
        raise CompositionError(f"Trimmed clip not created: {output_path}")
    
    return output_path

async def loop_clip(
    clip_path: Path,
    clip: Clip,
    temp_dir: Path,
    job_id: UUID
) -> Path:
    """Loop clip to reach target duration."""
    output_path = temp_dir / f"clip_{clip.clip_index}_looped.mp4"
    
    loops_needed = int(clip.target_duration / clip.actual_duration) + 1
    logger.info(
        f"Looping clip {clip.clip_index} {loops_needed}x times ({clip.actual_duration:.2f}s → {clip.target_duration:.2f}s)",
        extra={"job_id": str(job_id), "clip_index": clip.clip_index, "loops": loops_needed}
    )
    
    # Create concat file for FFmpeg
    concat_file = temp_dir / f"clip_{clip.clip_index}_concat.txt"
    with open(concat_file, "w") as f:
        for _ in range(loops_needed):
            # Use absolute path and escape single quotes for FFmpeg
            abs_path = clip_path.absolute()
            f.write(f"file '{abs_path}'\n")
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",  # Allow absolute paths
        "-i", str(concat_file),
        "-t", str(clip.target_duration),  # Trim to exact target
        "-c", "copy",
        "-y",
        str(output_path)
    ]
    
    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
    
    if not output_path.exists():
        raise CompositionError(f"Looped clip not created: {output_path}")
    
    return output_path

async def handle_clip_duration(
    clip_path: Path,
    clip: Clip,
    temp_dir: Path,
    job_id: UUID
) -> DurationHandledClip:
    """
    Handle clip duration mismatch (trim or loop).
    
    Args:
        clip_path: Path to normalized clip
        clip: Clip object with actual/target durations
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        DurationHandledClip with path and flags
    """
    from .config import DURATION_TOLERANCE
    
    duration_diff = clip.actual_duration - clip.target_duration
    
    # If duration is close enough, use as-is
    if abs(duration_diff) <= DURATION_TOLERANCE:
        logger.debug(
            f"Clip {clip.clip_index} duration OK ({clip.actual_duration:.2f}s vs {clip.target_duration:.2f}s)",
            extra={"job_id": str(job_id), "clip_index": clip.clip_index}
        )
        return DurationHandledClip(clip_path, False, False)
    
    # If too long: trim from end
    if duration_diff > DURATION_TOLERANCE:
        output_path = await trim_clip(clip_path, clip, temp_dir, job_id)
        return DurationHandledClip(output_path, True, False)
    
    # If too short: loop entire clip
    else:
        output_path = await loop_clip(clip_path, clip, temp_dir, job_id)
        return DurationHandledClip(output_path, False, True)
```

**MVP Simplification:** Trim to exact `target_duration` (no beat alignment).

---

### Step 5: Apply Transitions (MVP: Cuts Only)

**Location:** `transition_applier.py`

**Purpose:** Apply transitions between clips (MVP: simple cuts).

**Required Imports:**
```python
from pathlib import Path
from typing import List
from uuid import UUID
from shared.errors import CompositionError
from shared.logging import get_logger
from shared.models.scene import Transition
from .utils import run_ffmpeg_command

logger = get_logger("composer.transition_applier")
```

**Implementation:**
```python
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
        transitions: List of transition definitions (ignored in MVP, validated for post-MVP)
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Path to concatenated video with transitions
    """
    # MVP: Simple concatenation (cuts only)
    # Note: transitions parameter is validated but not used in MVP
    # Clips are concatenated in order regardless of transition types
    
    # Create concat file for FFmpeg
    concat_file = temp_dir / "clips_concat.txt"
    with open(concat_file, "w") as f:
        for clip_path in clip_paths:
            # Use absolute path and escape single quotes for FFmpeg
            abs_path = clip_path.absolute()
            f.write(f"file '{abs_path}'\n")
    
    output_path = temp_dir / "clips_concatenated.mp4"
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",  # Allow absolute paths
        "-i", str(concat_file),
        "-c", "copy",  # Stream copy (fast, no re-encoding)
        "-y",
        str(output_path)
    ]
    
    logger.info(
        f"Concatenating {len(clip_paths)} clips with cuts (MVP: transitions ignored)",
        extra={"job_id": str(job_id), "clip_count": len(clip_paths), "transitions_count": len(transitions)}
    )
    
    await run_ffmpeg_command(ffmpeg_cmd, job_id=job_id, timeout=300)
    
    if not output_path.exists():
        raise CompositionError(f"Concatenated video not created: {output_path}")
    
    return output_path
```

**Post-MVP:** Add crossfade/fade transitions using `xfade` filter.

---

**Next:** See `PRD_composer_implementation_part2.md` for Steps 5-8 (transitions, sync, encode, upload) and main function.
