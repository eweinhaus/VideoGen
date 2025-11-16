# Module 8: Composer

**Tech Stack:** Python (FFmpeg)

## Purpose
Stitch video clips with beat-aligned transitions, sync original audio, and produce final MP4 video.

## Key Features
- Duration Handling:
  - Trim clips if too long (from end, stay on beat)
  - Loop clips if too short (frame repetition)
  - Never extend without looping
- Normalization (all clips to 30 FPS, 1080p)
- Transitions (cut 0s, crossfade 0.5s, fade 0.5s at beat boundaries)
- Audio Sync (perfect sync ±100ms tolerance)
- Output: MP4 (H.264, AAC, 5000k bitrate)

## Fallback Strategies
- Transition fails → Use simple cut
- Duration mismatch >1s → Adjust video speed ±5%
- <3 clips available → Fail job (minimum not met)
- FFmpeg errors → Retry composition once, then fail with detailed error message

---

## Deployment Requirements

### FFmpeg Installation

FFmpeg is required for video processing. The module checks for FFmpeg availability at startup and provides clear installation instructions if not found.

#### Installation Instructions

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
apt-get update
apt-get install ffmpeg
```

**Linux (CentOS/RHEL):**
```bash
yum install ffmpeg
```

**Windows:**
1. Download FFmpeg from https://ffmpeg.org/
2. Extract to a directory (e.g., `C:\ffmpeg`)
3. Add `C:\ffmpeg\bin` to your system PATH

#### Verification

Verify FFmpeg is installed and accessible:
```bash
ffmpeg -version
```

The module automatically checks for FFmpeg availability using `shutil.which("ffmpeg")` and raises a `CompositionError` with installation instructions if not found.

#### Docker/Production

For Docker deployments, add FFmpeg to your Dockerfile:
```dockerfile
RUN apt-get update && apt-get install -y ffmpeg
```

For system packages in production, ensure FFmpeg is installed in the system PATH before starting the application.

---

### Storage Buckets

The Composer module requires the following Supabase Storage buckets:

#### Required Buckets

1. **`video-clips`** (read)
   - **Purpose:** Input clips from Video Generator
   - **Access:** Read-only
   - **Format:** MP4 video files
   - **Path:** `{job_id}/clip_{index}.mp4`

2. **`video-outputs`** (write)
   - **Purpose:** Final composed videos
   - **Access:** Write-only
   - **Format:** MP4 video files (H.264/AAC, 5000k bitrate)
   - **Path:** `{job_id}/final_video.mp4`

3. **`audio-uploads`** (read)
   - **Purpose:** Original audio files
   - **Access:** Read-only
   - **Format:** MP3, WAV, M4A (FFmpeg handles multiple formats)
   - **Path:** `{job_id}/audio.mp3`

#### Bucket Configuration

Verify buckets exist and have correct permissions:

```python
# Check bucket exists
from shared.storage import StorageClient
storage = StorageClient()

# Verify buckets are accessible
buckets = await storage.list_buckets()
assert "video-clips" in buckets
assert "video-outputs" in buckets
assert "audio-uploads" in buckets
```

#### Bucket Setup (Supabase Dashboard)

1. Navigate to Storage in Supabase Dashboard
2. Create buckets if they don't exist:
   - `video-clips` (private)
   - `video-outputs` (private)
   - `audio-uploads` (private)
3. Configure bucket policies:
   - `video-clips`: Read access for service role
   - `video-outputs`: Write access for service role
   - `audio-uploads`: Read access for service role

---

### Resource Requirements

#### Memory

- **Minimum:** ~300MB
- **Recommended:** ~500MB for 6 clips
- **Peak:** ~500MB during encoding

Memory usage scales with number of clips and video duration. The module processes clips sequentially after download to minimize memory usage.

#### Disk Space

- **Temporary Files:** ~500MB for 3-minute video
- **Recommended Available:** >0.5 GB
- **Cleanup:** Automatic (temp files cleaned up after composition)

The module uses a temporary directory context manager that automatically cleans up all temporary files, even on exceptions. Disk space is checked at startup (non-blocking warning if <500MB available).

#### Network

- **Download:** ~300MB total (6 clips + 1 audio file)
- **Upload:** ~50MB final video (varies by duration)
- **Bandwidth:** Depends on Supabase Storage connection

Downloads are performed in parallel for better performance (6 clips × 2s = 12s → 2s with parallel).

#### CPU

- **FFmpeg Threading:** 4 threads (configurable via `FFMPEG_THREADS`)
- **Performance:** 20-30% faster encoding on multi-core systems

FFmpeg commands use `-threads 4` for parallel processing during normalization and encoding.

---

### Performance Targets

- **Composition Time:** <90s for 3-minute video
- **Download Time:** <5s for 6 clips (parallel)
- **Normalization Time:** <30s for 6 clips
- **Encoding Time:** <45s for 3-minute video
- **Audio Sync Drift:** <100ms tolerance

Performance metrics are logged at each step for optimization and monitoring.

---

### Error Handling

#### Error Types

1. **CompositionError** (Permanent Failures)
   - Invalid input (missing clips, invalid URLs)
   - FFmpeg errors after max retries
   - Output validation failures
   - Minimum clips not met (<3 clips)

2. **RetryableError** (Transient Failures)
   - Network errors (download failures)
   - FFmpeg timeouts (system load, disk I/O)
   - Storage upload failures (temporary service issues)

#### Retry Logic

- **FFmpeg Commands:** 2 retry attempts with exponential backoff (2s, 4s delays)
- **Network Operations:** Retried by orchestrator (exponential backoff)
- **Max Attempts:** 2 for FFmpeg, 3 for network operations

---

### Monitoring & Logging

#### Key Metrics Logged

- **Composition Time:** Total + per-step breakdown
- **File Sizes:** Clips, final video (MB)
- **Duration Stats:** Clips trimmed, looped
- **Sync Drift:** Audio-video synchronization drift (seconds)
- **Error Rates:** FFmpeg failures, download failures

#### Log Format

All logs include structured data with `job_id` for tracing:
```python
logger.info(
    "Composition complete: 45.2 MB, 60.5s",
    extra={
        "job_id": str(job_id),
        "file_size_mb": 45.2,
        "composition_time": 60.5,
        "clips_used": 6,
        "clips_trimmed": 4,
        "clips_looped": 2,
        "sync_drift": 0.05,
        "timings": {
            "download_clips": 2.1,
            "normalize_clips": 25.3,
            "handle_durations": 5.2,
            "apply_transitions": 1.5,
            "sync_audio": 2.8,
            "encode_final": 20.6,
            "upload_final": 3.0,
            "total": 60.5
        }
    }
)
```

---

### Testing

#### Unit Tests

Run unit tests:
```bash
PYTHONPATH=. pytest modules/composer/tests/ -v
```

Test coverage:
- Error handling scenarios
- Input validation
- Edge cases (empty clips, missing URLs, invalid formats)
- Output validation

#### Integration Tests

Test with real clips:
```bash
pytest modules/composer/tests/test_integration.py -v
```

#### Performance Tests

Verify performance targets:
```bash
pytest modules/composer/tests/test_performance.py -v
```

---

### Troubleshooting

#### FFmpeg Not Found

**Error:** `CompositionError: FFmpeg not found`

**Solution:**
1. Install FFmpeg (see Installation Instructions above)
2. Verify FFmpeg is in PATH: `ffmpeg -version`
3. Restart application

#### Low Disk Space

**Warning:** `Low disk space: 0.3 GB available`

**Solution:**
1. Free up disk space (>500MB recommended)
2. Clean up old temporary files
3. Check temp directory cleanup is working

#### Download Failures

**Error:** `RetryableError: Failed to download clip`

**Solution:**
1. Check Supabase Storage connectivity
2. Verify bucket permissions
3. Check network connection
4. Retry will be attempted automatically

#### FFmpeg Timeout

**Error:** `RetryableError: FFmpeg command timeout`

**Solution:**
1. Check system load (CPU, disk I/O)
2. Increase timeout if needed (default: 300s)
3. Retry will be attempted automatically

---

### Configuration

Configuration constants are defined in `modules/composer/config.py`:

- **FFmpeg Settings:**
  - `FFMPEG_THREADS = 4`
  - `FFMPEG_TIMEOUT = 300` (5 minutes)
  - `FFMPEG_PRESET = "medium"`
  - `FFMPEG_CRF = 23`

- **Output Settings:**
  - `OUTPUT_WIDTH = 1920`
  - `OUTPUT_HEIGHT = 1080`
  - `OUTPUT_FPS = 30`
  - `OUTPUT_VIDEO_BITRATE = "5000k"`
  - `OUTPUT_AUDIO_BITRATE = "192k"`

- **Duration Handling:**
  - `DURATION_TOLERANCE = 0.5` (0.5s tolerance)

---

### Next Steps

1. **Integration Testing:** Test with orchestrator and full pipeline
2. **Performance Optimization:** Monitor timings and optimize bottlenecks
3. **Post-MVP Enhancements:**
   - Beat alignment for trimming
   - Audio sync adjustment (if drift >100ms)
   - Seamless looping
   - Crossfade transitions
   - Single FFmpeg command optimization



