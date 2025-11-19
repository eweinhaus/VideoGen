# Lipsync Template Setup Guide

## Overview

This guide explains how to set up a "Lipsync" template for your AI video editor using the Replicate `pixverse/lipsync` model. This template will take a generated video clip and synchronize lip movements with trimmed audio.

## What You Need to Know

### 1. PixVerse LipSync Model Details

**Model:** `pixverse/lipsync` on Replicate

**Inputs:**
- `video`: URL or file path to the video clip (max 30 seconds, 20MB file size limit)
- `audio`: URL or file path to the trimmed audio file (max 30 seconds)

**Output:**
- Lipsynced video with synchronized mouth movements

**Constraints:**
- Both video and audio must be ≤ 30 seconds
- Video file size must be ≤ 20MB
- Processing time: Typically 30-90 seconds per clip

**Cost:** Check Replicate pricing for `pixverse/lipsync` model (typically $0.05-$0.15 per clip)

### 2. Integration Points in Your Pipeline

Your current pipeline generates video clips at **Module 7: Video Generator**. The lipsync template should be integrated as:

**Option A: Post-Generation Processing (Recommended)**
- After video clip is generated → Apply lipsync → Continue to composer
- Location: Between Video Generator (Module 7) and Composer (Module 8)

**Option B: As a Template Option**
- User selects "Lipsync" template during upload
- Video Generator generates clip → Lipsync applied → Continue to composer
- Location: Integrated into Video Generator or as separate processing step

### 3. Audio Trimming Requirements

You need to trim the original audio file to match the exact timestamp of each clip:

**Current System:**
- `ClipBoundary` model has `start` and `end` timestamps
- Each clip corresponds to a specific time range in the original audio
- Example: Clip 0 = 0.0s to 5.2s, Clip 1 = 5.2s to 10.5s

**What You Need:**
- Function to extract audio segment: `trim_audio(audio_bytes, start_time, end_time) -> bytes`
- Use FFmpeg to trim audio to exact clip boundaries
- Upload trimmed audio to Supabase Storage (temporary, can delete after processing)

## Architecture Design

### Recommended Approach: Lipsync Post-Processor Module

Create a new module `modules/lipsync_processor/` that:

1. **Takes generated clip + clip boundary**
2. **Trims audio to exact timestamp**
3. **Calls Replicate pixverse/lipsync API**
4. **Returns lipsynced video clip**
5. **Replaces original clip in pipeline**

### Module Structure

```
modules/lipsync_processor/
├── __init__.py
├── config.py          # Lipsync model configuration
├── audio_trimmer.py   # Audio trimming utilities
├── generator.py       # Replicate API integration
├── process.py         # Main orchestration
└── tests/
    └── test_*.py
```

## Implementation Steps

### Step 1: Audio Trimming Function

Create `modules/lipsync_processor/audio_trimmer.py`:

```python
"""
Audio trimming utilities for lipsync processing.
"""
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Tuple
from uuid import UUID

from shared.logging import get_logger
from shared.errors import RetryableError

logger = get_logger("lipsync_processor.audio_trimmer")


async def trim_audio_to_clip(
    audio_bytes: bytes,
    start_time: float,
    end_time: float,
    job_id: UUID,
    temp_dir: Path
) -> Tuple[bytes, float]:
    """
    Trim audio to exact clip boundaries using FFmpeg.
    
    Args:
        audio_bytes: Original audio file bytes
        start_time: Start time in seconds
        end_time: End time in seconds
        job_id: Job ID for logging
        temp_dir: Temporary directory for processing
        
    Returns:
        Tuple of (trimmed_audio_bytes, duration)
        
    Raises:
        RetryableError: If trimming fails
    """
    duration = end_time - start_time
    
    # Validate duration (pixverse/lipsync max is 30s)
    if duration > 30.0:
        raise ValueError(f"Clip duration {duration}s exceeds 30s limit for lipsync")
    
    # Create temporary input file
    input_path = temp_dir / f"audio_input_{job_id}.mp3"
    output_path = temp_dir / f"audio_trimmed_{job_id}.mp3"
    
    try:
        # Write input audio to temp file
        input_path.write_bytes(audio_bytes)
        
        # FFmpeg command to trim audio
        # -ss: seek to start time
        # -t: duration to extract
        # -c:a copy: copy audio codec (fast, no re-encoding)
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-ss", str(start_time),
            "-t", str(duration),
            "-c:a", "copy",  # Copy audio stream (fast)
            "-y",  # Overwrite output
            str(output_path)
        ]
        
        logger.info(
            f"Trimming audio: {start_time}s to {end_time}s (duration: {duration}s)",
            extra={"job_id": str(job_id), "start": start_time, "end": end_time}
        )
        
        # Execute FFmpeg
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            logger.error(
                f"Failed to trim audio: {error_msg}",
                extra={"job_id": str(job_id), "error": error_msg}
            )
            raise RetryableError(f"Audio trimming failed: {error_msg}")
        
        # Read trimmed audio
        trimmed_bytes = output_path.read_bytes()
        
        logger.info(
            f"Audio trimmed successfully: {len(trimmed_bytes)} bytes",
            extra={"job_id": str(job_id), "size": len(trimmed_bytes)}
        )
        
        return trimmed_bytes, duration
        
    except asyncio.TimeoutError:
        raise RetryableError("Audio trimming timeout after 60s")
    except Exception as e:
        logger.error(
            f"Error trimming audio: {e}",
            extra={"job_id": str(job_id), "error": str(e)}
        )
        raise RetryableError(f"Audio trimming error: {str(e)}") from e
    finally:
        # Cleanup temp files
        for path in [input_path, output_path]:
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass
```

### Step 2: Lipsync Generator

Create `modules/lipsync_processor/generator.py`:

```python
"""
Replicate API integration for PixVerse LipSync model.
"""
import asyncio
import time
from typing import Optional
from uuid import UUID
from decimal import Decimal

import replicate
import httpx

from shared.models.video import Clip
from shared.storage import StorageClient
from shared.cost_tracking import cost_tracker
from shared.errors import RetryableError, GenerationError
from shared.logging import get_logger
from shared.config import settings

logger = get_logger("lipsync_processor.generator")

# Initialize Replicate client
try:
    client = replicate.Client(api_token=settings.replicate_api_token)
except Exception as e:
    logger.error(f"Failed to initialize Replicate client: {str(e)}")
    raise

# PixVerse LipSync model configuration
PIXVERSE_LIPSYNC_MODEL = "pixverse/lipsync"
# Get latest version hash or use pinned version
PIXVERSE_LIPSYNC_VERSION = os.getenv("PIXVERSE_LIPSYNC_VERSION", "latest")


async def download_video_from_url(url: str) -> bytes:
    """Download video from URL."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            response = await http_client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"Failed to download video from {url}: {e}")
        raise RetryableError(f"Video download failed: {str(e)}") from e


async def generate_lipsync_clip(
    video_url: str,
    audio_url: str,
    clip_index: int,
    job_id: UUID,
    environment: str = "production"
) -> Clip:
    """
    Generate lipsynced video clip via Replicate PixVerse LipSync model.
    
    Args:
        video_url: URL to the video clip (must be ≤ 30s, ≤ 20MB)
        audio_url: URL to the trimmed audio file (must be ≤ 30s)
        clip_index: Index of the clip
        job_id: Job ID for logging
        environment: "production" or "development"
        
    Returns:
        Clip model with lipsynced video URL
        
    Raises:
        RetryableError: If generation fails but is retryable
        GenerationError: If generation fails permanently
    """
    logger.info(
        f"Starting lipsync generation for clip {clip_index}",
        extra={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "video_url": video_url,
            "audio_url": audio_url
        }
    )
    
    try:
        # Prepare input data for Replicate API
        input_data = {
            "video": video_url,
            "audio": audio_url
        }
        
        # Create prediction
        if PIXVERSE_LIPSYNC_VERSION == "latest":
            prediction = client.predictions.create(
                model=PIXVERSE_LIPSYNC_MODEL,
                input=input_data
            )
        else:
            prediction = client.predictions.create(
                version=PIXVERSE_LIPSYNC_VERSION,
                input=input_data
            )
        
        # Poll for completion
        start_time = time.time()
        timeout_seconds = 180  # 3 minutes timeout
        
        while prediction.status not in ["succeeded", "failed", "canceled"]:
            elapsed = time.time() - start_time
            
            if elapsed > timeout_seconds:
                raise RetryableError(f"Lipsync generation timeout after {elapsed:.1f}s")
            
            await asyncio.sleep(3)  # Poll every 3 seconds
            prediction.reload()
        
        # Handle result
        if prediction.status == "succeeded":
            # Get output video URL
            output = prediction.output
            
            if isinstance(output, list):
                video_output_url = output[0]
            elif isinstance(output, str):
                video_output_url = output
            else:
                raise GenerationError(f"Unexpected output format: {type(output)}")
            
            # Download lipsynced video
            logger.info(
                f"Downloading lipsynced video for clip {clip_index}",
                extra={"job_id": str(job_id), "clip_index": clip_index}
            )
            video_bytes = await download_video_from_url(video_output_url)
            
            # Upload to Supabase Storage
            storage = StorageClient()
            clip_path = f"{job_id}/clip_{clip_index}_lipsync.mp4"
            
            # Delete existing file if it exists
            try:
                await storage.delete_file("video-clips", clip_path)
            except Exception:
                pass
            
            final_url = await storage.upload_file(
                bucket="video-clips",
                path=clip_path,
                file_data=video_bytes,
                content_type="video/mp4"
            )
            
            # Get actual cost from prediction (if available)
            actual_cost = get_prediction_cost(prediction)
            if actual_cost is None:
                # Estimate cost (typically $0.05-$0.15 per clip)
                actual_cost = Decimal("0.10")
                logger.warning(
                    f"Cost not available, using estimate: {actual_cost}",
                    extra={"job_id": str(job_id), "clip_index": clip_index}
                )
            
            # Track cost
            await cost_tracker.track_cost(
                job_id=job_id,
                stage_name="lipsync_processor",
                api_name="pixverse_lipsync",
                cost=actual_cost
            )
            
            generation_time = time.time() - start_time
            
            logger.info(
                f"Lipsync clip {clip_index} generated successfully",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "cost": float(actual_cost),
                    "generation_time": generation_time
                }
            )
            
            # Return Clip model (you'll need to preserve original clip metadata)
            # Note: You may need to get original clip duration from the original Clip object
            return Clip(
                clip_index=clip_index,
                video_url=final_url,
                actual_duration=0.0,  # Will be updated from original clip
                target_duration=0.0,  # Will be updated from original clip
                original_target_duration=0.0,  # Will be updated from original clip
                duration_diff=0.0,
                status="success",
                cost=actual_cost,
                retry_count=0,
                generation_time=generation_time
            )
        else:
            # Handle errors
            error_str = str(prediction.error).lower()
            
            if "rate limit" in error_str or "429" in error_str:
                raise RetryableError(f"Rate limit error: {prediction.error}")
            elif "timeout" in error_str:
                raise RetryableError(f"Timeout error: {prediction.error}")
            elif "network" in error_str or "connection" in error_str:
                raise RetryableError(f"Network error: {prediction.error}")
            else:
                raise GenerationError(f"Lipsync generation failed: {prediction.error}")
                
    except RetryableError:
        raise
    except Exception as e:
        error_str = str(e).lower()
        if "rate limit" in error_str or "429" in error_str:
            raise RetryableError(f"Rate limit error: {str(e)}") from e
        elif "timeout" in error_str:
            raise RetryableError(f"Timeout error: {str(e)}") from e
        elif "network" in error_str or "connection" in error_str:
            raise RetryableError(f"Network error: {str(e)}") from e
        else:
            raise GenerationError(f"Lipsync generation error: {str(e)}") from e


def get_prediction_cost(prediction) -> Optional[Decimal]:
    """Extract actual cost from Replicate prediction."""
    # Similar to video_generator/generator.py implementation
    cost = None
    
    if hasattr(prediction, 'metrics') and isinstance(prediction.metrics, dict):
        cost = prediction.metrics.get('cost')
    
    if cost is None and hasattr(prediction, 'cost'):
        cost = prediction.cost
    
    if cost is not None:
        try:
            return Decimal(str(cost))
        except (ValueError, TypeError):
            return None
    
    return None
```

### Step 3: Main Process Orchestration

Create `modules/lipsync_processor/process.py`:

```python
"""
Lipsync processor main orchestration.
"""
from typing import List, Optional
from uuid import UUID
from pathlib import Path
import tempfile

from shared.models.video import Clip, ClipPrompt
from shared.models.audio import ClipBoundary
from shared.storage import StorageClient
from shared.logging import get_logger
from shared.errors import RetryableError, GenerationError

from modules.lipsync_processor.audio_trimmer import trim_audio_to_clip
from modules.lipsync_processor.generator import generate_lipsync_clip

logger = get_logger("lipsync_processor.process")


async def process_lipsync_clips(
    clips: List[Clip],
    clip_boundaries: List[ClipBoundary],
    audio_url: str,
    job_id: UUID,
    environment: str = "production"
) -> List[Clip]:
    """
    Apply lipsync to multiple video clips.
    
    Args:
        clips: List of generated video clips
        clip_boundaries: List of clip boundaries (for audio trimming)
        audio_url: URL to original audio file
        job_id: Job ID
        environment: "production" or "development"
        
    Returns:
        List of lipsynced clips (replaces original clips)
    """
    if len(clips) != len(clip_boundaries):
        raise GenerationError(
            f"Mismatch: {len(clips)} clips but {len(clip_boundaries)} boundaries"
        )
    
    # Download original audio
    storage = StorageClient()
    logger.info(
        f"Downloading original audio for lipsync processing",
        extra={"job_id": str(job_id)}
    )
    audio_bytes = await storage.download_file_from_url(audio_url)
    
    # Process each clip
    lipsynced_clips = []
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for i, (clip, boundary) in enumerate(zip(clips, clip_boundaries)):
            try:
                logger.info(
                    f"Processing lipsync for clip {i}",
                    extra={
                        "job_id": str(job_id),
                        "clip_index": i,
                        "start": boundary.start,
                        "end": boundary.end
                    }
                )
                
                # Step 1: Trim audio to clip boundaries
                trimmed_audio_bytes, duration = await trim_audio_to_clip(
                    audio_bytes=audio_bytes,
                    start_time=boundary.start,
                    end_time=boundary.end,
                    job_id=job_id,
                    temp_dir=temp_path
                )
                
                # Step 2: Upload trimmed audio to temporary storage
                trimmed_audio_path = f"{job_id}/audio_trimmed_{i}.mp3"
                trimmed_audio_url = await storage.upload_file(
                    bucket="audio-uploads",  # Or create "lipsync-temp" bucket
                    path=trimmed_audio_path,
                    file_data=trimmed_audio_bytes,
                    content_type="audio/mpeg"
                )
                
                # Step 3: Generate lipsynced clip
                lipsynced_clip = await generate_lipsync_clip(
                    video_url=clip.video_url,
                    audio_url=trimmed_audio_url,
                    clip_index=i,
                    job_id=job_id,
                    environment=environment
                )
                
                # Preserve original clip metadata
                lipsynced_clip.actual_duration = clip.actual_duration
                lipsynced_clip.target_duration = clip.target_duration
                lipsynced_clip.original_target_duration = clip.original_target_duration
                lipsynced_clip.duration_diff = clip.duration_diff
                
                lipsynced_clips.append(lipsynced_clip)
                
                # Cleanup: Delete trimmed audio (optional, can keep for debugging)
                try:
                    await storage.delete_file("audio-uploads", trimmed_audio_path)
                except Exception:
                    pass
                
            except Exception as e:
                logger.error(
                    f"Failed to process lipsync for clip {i}: {e}",
                    extra={"job_id": str(job_id), "clip_index": i, "error": str(e)}
                )
                # Option: Use original clip if lipsync fails
                # Or raise error to fail the job
                raise GenerationError(f"Lipsync failed for clip {i}: {str(e)}") from e
    
    logger.info(
        f"Lipsync processing complete: {len(lipsynced_clips)} clips processed",
        extra={"job_id": str(job_id), "num_clips": len(lipsynced_clips)}
    )
    
    return lipsynced_clips
```

### Step 4: Integration into Orchestrator

Modify `api_gateway/orchestrator.py` to add lipsync processing:

```python
# After video generation (Module 7), before composer (Module 8)

# Check if lipsync template is enabled
if job_metadata.get("template") == "lipsync":
    logger.info("Applying lipsync template to clips", extra={"job_id": str(job_id)})
    
    # Load clip boundaries from audio analysis
    audio_analysis = await load_audio_analysis(job_id)
    clip_boundaries = audio_analysis.clip_boundaries
    
    # Apply lipsync
    from modules.lipsync_processor.process import process_lipsync_clips
    clips = await process_lipsync_clips(
        clips=clips,
        clip_boundaries=clip_boundaries,
        audio_url=audio_url,
        job_id=job_id,
        environment=settings.environment
    )
    
    logger.info("Lipsync processing complete", extra={"job_id": str(job_id)})

# Continue to composer with lipsynced clips
```

### Step 5: Frontend Template Selection

Add template selection to upload form:

```typescript
// In project/frontend/app/upload/page.tsx or similar

const [template, setTemplate] = useState<string>("standard");

// Template options
const templates = [
  { value: "standard", label: "Standard Video" },
  { value: "lipsync", label: "Lipsync (Character Lip Sync)" }
];

// Include template in upload request
const uploadAudio = async () => {
  const formData = new FormData();
  formData.append("audio", audioFile);
  formData.append("prompt", prompt);
  formData.append("template", template); // Add template parameter
  
  // ... rest of upload logic
};
```

## Configuration

### Environment Variables

Add to `.env`:

```bash
# PixVerse LipSync Model
PIXVERSE_LIPSYNC_VERSION=latest  # Or use pinned version hash
```

### Model Configuration

Add to `modules/lipsync_processor/config.py`:

```python
"""
Lipsync processor configuration.
"""
import os
from shared.config import settings

# PixVerse LipSync model
PIXVERSE_LIPSYNC_MODEL = "pixverse/lipsync"
PIXVERSE_LIPSYNC_VERSION = os.getenv("PIXVERSE_LIPSYNC_VERSION", "latest")

# Processing settings
LIPSYNC_TIMEOUT_SECONDS = int(os.getenv("LIPSYNC_TIMEOUT_SECONDS", "180"))  # 3 minutes
LIPSYNC_MAX_DURATION = 30.0  # Max clip duration in seconds
LIPSYNC_MAX_VIDEO_SIZE_MB = 20  # Max video file size in MB

# Cost estimation (if not available from Replicate)
LIPSYNC_ESTIMATED_COST = float(os.getenv("LIPSYNC_ESTIMATED_COST", "0.10"))  # $0.10 per clip
```

## Testing

### Unit Tests

Create test files in `modules/lipsync_processor/tests/`:

- `test_audio_trimmer.py` - Test audio trimming
- `test_generator.py` - Test Replicate API integration
- `test_process.py` - Test full orchestration

### Integration Testing

1. Generate a test video clip (5-10 seconds)
2. Prepare test audio file
3. Test lipsync processing end-to-end
4. Verify output quality and sync accuracy

## Cost Considerations

- **Per Clip Cost:** ~$0.05-$0.15 per lipsync operation
- **Total Cost:** If you have 5 clips, add ~$0.50-$0.75 to total job cost
- **Budget Impact:** Update budget estimates to account for lipsync costs

## Error Handling

### Retryable Errors
- Rate limits (429)
- Network errors
- Timeouts
- Model unavailable

### Non-Retryable Errors
- Invalid input (video > 30s, audio > 30s, file too large)
- Content moderation failures
- Authentication errors

### Fallback Strategy
- If lipsync fails, use original clip (graceful degradation)
- Log error but don't fail entire job
- Option: Allow user to retry lipsync for specific clips

## Performance Considerations

- **Processing Time:** 30-90 seconds per clip
- **Parallel Processing:** Can process multiple clips in parallel (with rate limit awareness)
- **Caching:** Consider caching lipsynced clips if same audio+video combination is reused

## Next Steps

1. **Verify Model Availability:** Test `pixverse/lipsync` model on Replicate to confirm it's available
2. **Get Version Hash:** Use Replicate API to get latest version hash (or use "latest")
3. **Test Audio Trimming:** Verify FFmpeg audio trimming works correctly
4. **Test API Integration:** Create a simple test script to call Replicate API
5. **Implement Module:** Follow implementation steps above
6. **Integration Testing:** Test with real video clips and audio
7. **Frontend Integration:** Add template selector to upload form
8. **Cost Tracking:** Verify cost tracking works correctly
9. **Error Handling:** Test error scenarios and fallbacks

## Additional Resources

- **Replicate API Docs:** https://replicate.com/docs
- **PixVerse LipSync Model:** https://replicate.com/pixverse/lipsync
- **FFmpeg Audio Trimming:** https://ffmpeg.org/ffmpeg.html#Audio-Options

## Questions to Consider

1. **When to Apply Lipsync?**
   - Option A: Apply to all clips automatically when template selected
   - Option B: Allow user to select which clips to lipsync
   - Option C: Apply only to clips with characters/faces detected

2. **Quality vs Speed:**
   - PixVerse may be slower than standard generation
   - Consider showing progress updates during lipsync processing
   - May want to allow user to skip lipsync for faster generation

3. **Storage:**
   - Lipsynced clips replace original clips
   - Consider keeping originals for comparison/rollback
   - Temporary audio files can be deleted after processing

4. **User Experience:**
   - Show "Applying lipsync..." progress indicator
   - Display cost estimate before processing
   - Allow cancellation during processing

