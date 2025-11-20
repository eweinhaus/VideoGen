"""
Video padding for composer module.

Pads video with frozen last frame and fade-out when video is shorter than audio.
"""
from pathlib import Path
from uuid import UUID

from shared.errors import CompositionError
from shared.logging import get_logger
from .utils import run_ffmpeg_command, get_video_duration, get_audio_duration
from .config import OUTPUT_FPS, FFMPEG_PRESET

logger = get_logger("composer.video_padder")


async def pad_video_to_audio(
    video_path: Path,
    audio_bytes: bytes,
    temp_dir: Path,
    job_id: UUID,
    target_width: int,
    target_height: int
) -> Path:
    """
    Pad video with frozen last frame + fade-out if video is shorter than audio.
    
    Args:
        video_path: Path to video file
        audio_bytes: Original audio file bytes
        temp_dir: Temporary directory for output
        job_id: Job ID for logging
        target_width: Target output width in pixels
        target_height: Target output height in pixels
        
    Returns:
        Path to padded video file (or original if no padding needed)
    """
    # Write audio to temp file to get duration
    audio_path = temp_dir / "audio_for_padding.mp3"
    audio_path.write_bytes(audio_bytes)
    
    # Get durations
    video_duration = await get_video_duration(video_path)
    audio_duration = await get_audio_duration(audio_path)
    
    duration_diff = audio_duration - video_duration
    
    # If video is already long enough or difference is negligible (<0.1s), return as-is
    if duration_diff <= 0.1:
        logger.debug(
            f"Video duration ({video_duration:.2f}s) matches or exceeds audio ({audio_duration:.2f}s), no padding needed",
            extra={"job_id": str(job_id)}
        )
        return video_path
    
    logger.info(
        f"Padding video: {video_duration:.2f}s → {audio_duration:.2f}s (gap: {duration_diff:.2f}s)",
        extra={"job_id": str(job_id), "video_duration": video_duration, "audio_duration": audio_duration, "gap": duration_diff}
    )
    
    output_path = temp_dir / "video_padded.mp4"
    
    # Extract last frame and create frozen video with fade-out
    # Strategy: Freeze last frame for the gap duration, fade to black over last 2 seconds
    fade_duration = min(2.0, duration_diff)  # Fade for up to 2 seconds, or full gap if gap < 2s
    fade_start = duration_diff - fade_duration  # Start fade at this point
    
    try:
        # Step 1: Extract last frame as image
        # Seek to near the end (0.1s before end) and extract 1 frame
        last_frame_path = temp_dir / "last_frame.png"
        seek_time = max(0.0, video_duration - 0.1)  # Seek to 0.1s before end
        extract_cmd = [
            "ffmpeg",
            "-ss", str(seek_time),  # Seek to near end
            "-i", str(video_path),
            "-frames:v", "1",  # Extract only 1 frame (will be last or near last)
            "-q:v", "2",  # High quality
            "-y",
            str(last_frame_path)
        ]
        
        await run_ffmpeg_command(extract_cmd, job_id=job_id, timeout=60)
        
        if not last_frame_path.exists():
            raise CompositionError(f"Failed to extract last frame: {last_frame_path}")
        
        # Step 2: Create frozen video from last frame with fade-out
        padding_path = temp_dir / "padding.mp4"
        padding_cmd = [
            "ffmpeg",
            "-loop", "1",  # Loop the image
            "-i", str(last_frame_path),
            "-vf", f"scale={target_width}:{target_height},fps={OUTPUT_FPS},fade=t=out:st={fade_start}:d={fade_duration}",
            "-t", str(duration_diff),
            "-c:v", "libx264",
            "-preset", FFMPEG_PRESET,
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-y",
            str(padding_path)
        ]
        
        await run_ffmpeg_command(padding_cmd, job_id=job_id, timeout=300)
        
        if not padding_path.exists():
            raise CompositionError(f"Padding video not created: {padding_path}")
        
        # Step 3: Concatenate original video + padding
        concat_file = temp_dir / "concat_with_padding.txt"
        with open(concat_file, "w") as f:
            f.write(f"file '{video_path.absolute()}'\n")
            f.write(f"file '{padding_path.absolute()}'\n")
        
        concat_cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",  # Stream copy (fast, no re-encoding)
            "-y",
            str(output_path)
        ]
        
        await run_ffmpeg_command(concat_cmd, job_id=job_id, timeout=300)
        
        if not output_path.exists():
            raise CompositionError(f"Padded video not created: {output_path}")
        
        # Verify final duration
        final_duration = await get_video_duration(output_path)
        logger.info(
            f"Video padded successfully: {final_duration:.2f}s (target: {audio_duration:.2f}s)",
            extra={"job_id": str(job_id), "final_duration": final_duration, "target_duration": audio_duration}
        )
        
        return output_path
        
    except Exception as e:
        if isinstance(e, CompositionError):
            raise
        raise CompositionError(f"Failed to pad video: {e}") from e

