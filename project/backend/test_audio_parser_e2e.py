"""
End-to-end test script for audio parser with real audio file.
Tests the full audio parser flow with Test_audio_file.mp3
"""

import asyncio
import time
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.audio_parser.main import process_audio_analysis
from shared.models.audio import AudioAnalysis


async def test_audio_parser_with_file():
    """Test audio parser with local audio file."""
    print("=" * 80)
    print("Audio Parser End-to-End Test")
    print("=" * 80)
    
    # Path to test audio file
    audio_file_path = Path(__file__).parent / "modules" / "audio_parser" / "tests" / "Test_audio_file.mp3"
    
    if not audio_file_path.exists():
        print(f"❌ ERROR: Audio file not found at {audio_file_path}")
        return False
    
    print(f"✅ Audio file found: {audio_file_path} ({audio_file_path.stat().st_size / 1024 / 1024:.2f} MB)")
    
    # Read audio file
    with open(audio_file_path, 'rb') as f:
        audio_bytes = f.read()
    
    print(f"✅ Audio file loaded: {len(audio_bytes)} bytes")
    
    # For testing, we'll use a file:// URL or test the parser directly
    # Since we're testing locally, let's test parse_audio directly
    from modules.audio_parser.parser import parse_audio
    from modules.audio_parser.utils import calculate_file_hash
    
    job_id = uuid4()
    print(f"✅ Job ID: {job_id}")
    
    # Test parse_audio directly
    print("\n" + "-" * 80)
    print("Testing parse_audio()...")
    print("-" * 80)
    
    start_time = time.time()
    
    try:
        analysis = await parse_audio(audio_bytes, job_id)
        processing_time = time.time() - start_time
        
        print(f"✅ Analysis completed in {processing_time:.2f} seconds")
        print(f"\n📊 Results:")
        print(f"  - BPM: {analysis.bpm:.2f}")
        print(f"  - Duration: {analysis.duration:.2f} seconds")
        print(f"  - Beat timestamps: {len(analysis.beat_timestamps)} beats")
        print(f"  - Song structure: {len(analysis.song_structure)} segments")
        print(f"  - Lyrics: {len(analysis.lyrics)} words")
        print(f"  - Mood: {analysis.mood.primary} (confidence: {analysis.mood.confidence:.2f})")
        print(f"  - Clip boundaries: {len(analysis.clip_boundaries)} clips")
        
        # Validate results
        print(f"\n🔍 Validation:")
        assert isinstance(analysis, AudioAnalysis), "Result should be AudioAnalysis"
        assert 60 <= analysis.bpm <= 200, f"BPM {analysis.bpm} should be in 60-200 range"
        assert analysis.duration > 0, "Duration should be positive"
        assert len(analysis.beat_timestamps) > 0, "Should have beat timestamps"
        assert len(analysis.song_structure) > 0, "Should have song structure"
        assert len(analysis.clip_boundaries) >= 1, "Should have at least 1 clip boundary"
        assert all(4.0 <= b.duration <= 8.0 for b in analysis.clip_boundaries), "Clip durations should be 4-8s"
        print("  ✅ All validations passed")
        
        # Performance check
        print(f"\n⏱️  Performance:")
        print(f"  - Processing time: {processing_time:.2f}s")
        if analysis.duration > 0:
            print(f"  - Time per second of audio: {processing_time / analysis.duration:.2f}s")
        if processing_time < 60:
            print(f"  ✅ Performance target met (<60s for 3-min song)")
        else:
            print(f"  ⚠️  Performance target exceeded (>{60}s)")
        
        # Metadata
        print(f"\n📝 Metadata:")
        print(f"  - Cache hit: {analysis.metadata.get('cache_hit', False)}")
        print(f"  - Fallbacks used: {analysis.metadata.get('fallbacks_used', [])}")
        print(f"  - Beat detection confidence: {analysis.metadata.get('beat_detection_confidence', 'N/A')}")
        
        print("\n" + "=" * 80)
        print("✅ TEST PASSED")
        print("=" * 80)
        return True
        
    except Exception as e:
        processing_time = time.time() - start_time
        print(f"\n❌ ERROR after {processing_time:.2f} seconds:")
        print(f"  {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 80)
        print("❌ TEST FAILED")
        print("=" * 80)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_audio_parser_with_file())
    sys.exit(0 if success else 1)

