"""
Unit tests for composer process (input validation and integration).
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4
from decimal import Decimal
import importlib
import modules.composer.process as process_module
from modules.composer.process import process
from shared.models.video import Clips, Clip, VideoOutput
from shared.models.scene import Transition
from shared.errors import CompositionError


def sample_clip(clip_index: int, video_url: str = None) -> Clip:
    """Create a sample clip for testing."""
    if video_url is None:
        video_url = f"https://project.supabase.co/storage/v1/object/public/video-clips/clip{clip_index}.mp4"
    return Clip(
        clip_index=clip_index,
        video_url=video_url,
        actual_duration=5.0,
        target_duration=5.0,
        duration_diff=0.0,
        status="success",
        cost=Decimal("0.10"),
        generation_time=10.0
    )


def sample_clips(job_id, num_clips: int = 3) -> Clips:
    """Create sample clips collection."""
    clips_list = [sample_clip(i) for i in range(num_clips)]
    return Clips(
        job_id=job_id,
        clips=clips_list,
        total_clips=num_clips,
        successful_clips=num_clips,
        failed_clips=0,
        total_cost=Decimal("0.30"),
        total_generation_time=30.0
    )


class TestProcessInputValidation:
    """Tests for input validation in process function."""
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_minimum_clips_validation(self, mock_check_ffmpeg):
        """Test validation fails with less than 3 clips."""
        # Reload process module to use patched function
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=2)  # Only 2 clips
        
        with pytest.raises(CompositionError, match="Minimum 3 clips required"):
            await process(
                job_id=str(job_id),
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_missing_video_url(self, mock_check_ffmpeg):
        """Test validation fails when clip missing video_url."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        clips.clips[0].video_url = ""  # Empty video_url
        
        with pytest.raises(CompositionError, match="Clip 0 missing video_url"):
            await process(
                job_id=str(job_id),
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_invalid_clip_status(self, mock_check_ffmpeg):
        """Test validation fails when clip has invalid status."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        clips.clips[0].status = "failed"  # Invalid status
        
        with pytest.raises(CompositionError, match="Clip 0 has status 'failed'"):
            await process(
                job_id=str(job_id),
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_missing_audio_url(self, mock_check_ffmpeg):
        """Test validation fails when audio_url is missing."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        with pytest.raises(CompositionError, match="Audio URL required"):
            await process(
                job_id=str(job_id),
                clips=clips,
                audio_url="",  # Empty audio_url
                transitions=[]
            )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_invalid_job_id_format(self, mock_check_ffmpeg):
        """Test validation fails with invalid job_id format."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        with pytest.raises(ValueError):  # UUID conversion fails
            await process(
                job_id="invalid-uuid",
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_clips_sorting(self, mock_check_ffmpeg):
        """Test clips are sorted by clip_index."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        # Shuffle clips
        clips.clips = [clips.clips[2], clips.clips[0], clips.clips[1]]
        
        # Mock all dependencies to avoid actual processing
        # Reload module first, then patch publish_progress from the module object
        process_module_reloaded = sys.modules.get('modules.composer.process')
        with patch.object(process_module_reloaded, 'publish_progress', new_callable=AsyncMock) as mock_publish, \
             patch('modules.composer.downloader.download_all_clips', new_callable=AsyncMock) as mock_download, \
             patch('modules.composer.downloader.download_audio', new_callable=AsyncMock) as mock_download_audio, \
             patch('modules.composer.normalizer.normalize_clip', new_callable=AsyncMock) as mock_normalize, \
             patch('modules.composer.duration_handler.handle_clip_duration', new_callable=AsyncMock) as mock_duration, \
             patch('modules.composer.transition_applier.apply_transitions', new_callable=AsyncMock) as mock_transitions, \
             patch('modules.composer.audio_syncer.sync_audio', new_callable=AsyncMock) as mock_sync, \
             patch('modules.composer.encoder.encode_final_video', new_callable=AsyncMock) as mock_encode, \
             patch('shared.storage.StorageClient') as mock_storage, \
             patch('modules.composer.utils.get_video_duration', new_callable=AsyncMock) as mock_get_duration:
            
            from pathlib import Path
            mock_path = MagicMock(spec=Path)
            mock_path.exists.return_value = True
            mock_path.stat.return_value = MagicMock(st_size=1024 * 1024 * 10)  # 10MB
            mock_path.read_bytes.return_value = b"video_bytes"
            
            mock_download.return_value = [b"clip0", b"clip1", b"clip2"]
            mock_download_audio.return_value = b"audio"
            mock_normalize.return_value = mock_path
            mock_duration.return_value = (mock_path, False, False)
            mock_transitions.return_value = mock_path
            mock_sync.return_value = (mock_path, 0.0)
            mock_encode.return_value = mock_path
            mock_get_duration.return_value = 15.0
            
            mock_storage_instance = MagicMock()
            mock_storage_instance.upload_file = AsyncMock(return_value="https://example.com/video.mp4")
            mock_storage.return_value = mock_storage_instance
            
            # Process should succeed (validation passes)
            result = await process(
                job_id=str(job_id),
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
            
            # Verify clips were processed in order (sorted)
            assert isinstance(result, VideoOutput)
            # Verify download was called with sorted clips
            assert mock_download.called
            # Get the clips that were passed to download_all_clips
            # The function is called with sorted_clips, so we need to check the call
            call_args_list = mock_download.call_args_list
            if call_args_list:
                # Get the first call's first argument (clips list)
                clips_passed = call_args_list[0][0][0]
                assert [c.clip_index for c in clips_passed] == [0, 1, 2]  # Sorted
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=True)
    async def test_sequential_clip_indices_validation(self, mock_check_ffmpeg):
        """Test validation fails when clip indices are not sequential."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        clips.clips[1].clip_index = 5  # Non-sequential index
        
        with pytest.raises(CompositionError, match="Clip indices must be sequential"):
            await process(
                job_id=str(job_id),
                clips=clips,
                audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                transitions=[]
            )
    
    @pytest.mark.asyncio
    @patch('modules.composer.utils.check_ffmpeg_available', return_value=False)
    async def test_ffmpeg_not_available(self, mock_check_ffmpeg):
        """Test validation fails when FFmpeg is not available."""
        import importlib
        import sys
        if 'modules.composer.process' in sys.modules:
            importlib.reload(sys.modules['modules.composer.process'])
        from modules.composer.process import process
        
        job_id = uuid4()
        clips = sample_clips(job_id, num_clips=3)
        
        with pytest.raises(CompositionError, match="FFmpeg not found"):
                await process(
                    job_id=str(job_id),
                    clips=clips,
                    audio_url="https://project.supabase.co/storage/v1/object/public/audio-uploads/audio.mp3",
                    transitions=[]
                )
