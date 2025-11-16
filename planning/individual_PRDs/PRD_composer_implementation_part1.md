# Module 8: Composer - Implementation Part 1: Core Steps

**Version:** 1.0  
**Date:** November 15, 2025  
**Status:** Ready for Implementation  
**Dependencies:** PRD_composer_overview.md

**Related Documents:**
- `PRD_composer_overview.md` - Overview, architecture, inputs/outputs
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

### Step 1: Input Validation

**Location:** `process.py` (start of `process()` function)

**Purpose:** Fail fast with clear error messages before expensive operations.

**Implementation:**
```python
from shared.errors import CompositionError

# Validate minimum clips
if len(clips.clips) < 3:
    raise CompositionError("Minimum 3 clips required for composition")

# Validate all clips have video_url
for clip in clips.clips:
    if not clip.video_url:
        raise CompositionError(f"Clip {clip.clip_index} missing video_url")
    if clip.status != "success":
        raise CompositionError(f"Clip {clip.clip_index} has status '{clip.status}', expected 'success'")

# Validate audio_url
if not audio_url:
    raise CompositionError("Audio URL required for composition")

# Sort clips by clip_index (guarantee correct order)
sorted_clips = sorted(clips.clips, key=lambda c: c.clip_index)
```

**Why:** Prevents wasted time on invalid inputs, clear error messages.

---

### Step 2: Download Files (Parallel)

**Location:** `downloader.py`

**Purpose:** Download all clips and audio from Supabase Storage in parallel.

**Implementation:**
```python
import asyncio
from typing import List
from shared.storage import StorageClient
from modules.video_generator.image_handler import parse_supabase_url
from shared.errors import RetryableError
from shared.logging import get_logger

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
            return await storage.download_file(bucket, path)
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

**Implementation:**
```python
import subprocess
import tempfile
from pathlib import Path
from shared.errors import CompositionError, RetryableError
from shared.retry import retry_with_backoff
from shared.logging import get_logger

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
    
    try:
        # Run FFmpeg (wrap in executor for async)
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            logger.error(
                f"FFmpeg normalization failed for clip {clip_index}: {error_msg}",
                extra={"job_id": str(job_id), "clip_index": clip_index, "error": error_msg}
            )
            raise CompositionError(f"FFmpeg normalization failed: {error_msg}")
        
        if not output_path.exists():
            raise CompositionError(f"Normalized clip not created: {output_path}")
        
        logger.info(
            f"Normalized clip {clip_index}",
            extra={"job_id": str(job_id), "clip_index": clip_index}
        )
        
        return output_path
        
    except asyncio.TimeoutError:
        raise CompositionError(f"FFmpeg normalization timeout for clip {clip_index}")
    except Exception as e:
        if isinstance(e, CompositionError):
            raise
        raise RetryableError(f"Failed to normalize clip {clip_index}: {e}") from e
```

**Note:** Import `asyncio` at top of file.

---

### Step 4: Handle Duration Mismatches

**Location:** `duration_handler.py`

**Purpose:** Trim clips if too long, loop clips if too short.

**Implementation:**
```python
import subprocess
from pathlib import Path
from shared.errors import CompositionError
from shared.logging import get_logger

logger = get_logger("composer.duration_handler")

async def handle_clip_duration(
    clip_path: Path,
    clip: Clip,
    temp_dir: Path,
    job_id: UUID
) -> tuple[Path, bool, bool]:
    """
    Handle clip duration mismatch (trim or loop).
    
    Args:
        clip_path: Path to normalized clip
        clip: Clip object with actual/target durations
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        
    Returns:
        Tuple of (output_path, was_trimmed, was_looped)
    """
    duration_diff = clip.actual_duration - clip.target_duration
    tolerance = 0.5  # 0.5s tolerance
    
    # If duration is close enough, use as-is
    if abs(duration_diff) <= tolerance:
        logger.debug(
            f"Clip {clip.clip_index} duration OK ({clip.actual_duration:.2f}s vs {clip.target_duration:.2f}s)",
            extra={"job_id": str(job_id), "clip_index": clip.clip_index}
        )
        return clip_path, False, False
    
    output_path = temp_dir / f"clip_{clip.clip_index}_duration_fixed.mp4"
    
    # If too long: trim from end
    if duration_diff > tolerance:
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
        
        # Run FFmpeg (similar to normalize_clip)
        # ... (implementation similar to normalize_clip)
        
        return output_path, True, False
    
    # If too short: loop entire clip
    else:
        loops_needed = int(clip.target_duration / clip.actual_duration) + 1
        logger.info(
            f"Looping clip {clip.clip_index} {loops_needed}x times ({clip.actual_duration:.2f}s → {clip.target_duration:.2f}s)",
            extra={"job_id": str(job_id), "clip_index": clip.clip_index, "loops": loops_needed}
        )
        
        # Create concat file for FFmpeg
        concat_file = temp_dir / f"clip_{clip.clip_index}_concat.txt"
        with open(concat_file, "w") as f:
            for _ in range(loops_needed):
                f.write(f"file '{clip_path.absolute()}\n")
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-t", str(clip.target_duration),  # Trim to exact target
            "-c", "copy",
            "-y",
            str(output_path)
        ]
        
        # Run FFmpeg (similar to normalize_clip)
        # ... (implementation similar to normalize_clip)
        
        return output_path, False, True
```

**MVP Simplification:** Trim to exact `target_duration` (no beat alignment).

---

### Step 5: Apply Transitions (MVP: Cuts Only)

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
    
    # Run FFmpeg (similar to normalize_clip)
    # ... (implementation similar to normalize_clip)
    
    return output_path
```

**Post-MVP:** Add crossfade/fade transitions using `xfade` filter.

---

**Next:** See `PRD_composer_implementation_part2.md` for Steps 5-8 (transitions, sync, encode, upload) and main function.
