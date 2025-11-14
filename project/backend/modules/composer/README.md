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


