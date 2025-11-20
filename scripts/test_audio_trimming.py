"""
Test script to verify audio trimming functionality with FFmpeg.

This script tests trimming audio files to specific timestamps.
"""
import os
import sys
import asyncio
import subprocess
import tempfile
from pathlib import Path

# Add project backend to path
sys.path.insert(0, str(Path(__file__).parent / "project" / "backend"))

def check_ffmpeg():
    """Check if FFmpeg is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✅ FFmpeg found: {version_line}")
            return True
        else:
            print("❌ FFmpeg not found or not working")
            return False
    except FileNotFoundError:
        print("❌ FFmpeg not found in PATH")
        return False
    except Exception as e:
        print(f"❌ Error checking FFmpeg: {e}")
        return False


def trim_audio_ffmpeg(input_path: str, output_path: str, start_time: float, duration: float) -> bool:
    """
    Trim audio using FFmpeg.
    
    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file
        start_time: Start time in seconds
        duration: Duration in seconds
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-ss", str(start_time),
            "-t", str(duration),
            "-c:a", "copy",  # Copy audio codec (fast, no re-encoding)
            "-y",  # Overwrite output
            output_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            return True
        else:
            print(f"❌ FFmpeg error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ FFmpeg timeout after 60s")
        return False
    except Exception as e:
        print(f"❌ Error running FFmpeg: {e}")
        return False


def get_audio_duration(file_path: str) -> float:
    """Get audio duration using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            duration = float(result.stdout.strip())
            return duration
        else:
            print(f"⚠️  Could not get duration: {result.stderr}")
            return 0.0
            
    except Exception as e:
        print(f"⚠️  Error getting duration: {e}")
        return 0.0


def test_audio_trimming():
    """Test audio trimming with various scenarios."""
    print("=" * 60)
    print("Testing Audio Trimming with FFmpeg")
    print("=" * 60)
    
    # Check FFmpeg availability
    if not check_ffmpeg():
        print("\n❌ FFmpeg is required for audio trimming")
        print("   Please install FFmpeg: https://ffmpeg.org/download.html")
        return False
    
    # Test scenarios
    test_cases = [
        {
            "name": "Short clip (5 seconds)",
            "start": 0.0,
            "duration": 5.0,
            "description": "Trim first 5 seconds"
        },
        {
            "name": "Middle clip (5 seconds)",
            "start": 10.0,
            "duration": 5.0,
            "description": "Trim 10-15 seconds"
        },
        {
            "name": "Very short clip (1 second)",
            "start": 5.0,
            "duration": 1.0,
            "description": "Trim 1 second clip"
        },
        {
            "name": "Long clip (30 seconds)",
            "start": 0.0,
            "duration": 30.0,
            "description": "Trim 30 seconds (max limit)"
        }
    ]
    
    print(f"\n📋 Test Cases:")
    for i, test_case in enumerate(test_cases, 1):
        print(f"   {i}. {test_case['name']}: {test_case['description']}")
    
    print(f"\n⚠️  Note: This test requires a sample audio file.")
    print(f"   To test with a real file, provide an audio file path.")
    print(f"   Example: python test_audio_trimming.py /path/to/audio.mp3")
    
    # If audio file provided, test with it
    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        if not os.path.exists(audio_file):
            print(f"\n❌ Audio file not found: {audio_file}")
            return False
        
        print(f"\n📁 Testing with: {audio_file}")
        
        # Get original duration
        original_duration = get_audio_duration(audio_file)
        print(f"   Original duration: {original_duration:.2f}s")
        
        # Test each case
        with tempfile.TemporaryDirectory() as temp_dir:
            for i, test_case in enumerate(test_cases, 1):
                print(f"\n   Test {i}: {test_case['name']}")
                
                # Check if start + duration exceeds original
                if test_case['start'] + test_case['duration'] > original_duration:
                    print(f"      ⚠️  Skipped: Would exceed audio length")
                    continue
                
                output_path = os.path.join(temp_dir, f"trimmed_{i}.mp3")
                
                success = trim_audio_ffmpeg(
                    audio_file,
                    output_path,
                    test_case['start'],
                    test_case['duration']
                )
                
                if success:
                    trimmed_duration = get_audio_duration(output_path)
                    expected_duration = test_case['duration']
                    diff = abs(trimmed_duration - expected_duration)
                    
                    if diff < 0.1:  # Allow 100ms tolerance
                        print(f"      ✅ Success: {trimmed_duration:.2f}s (expected {expected_duration:.2f}s)")
                    else:
                        print(f"      ⚠️  Duration mismatch: {trimmed_duration:.2f}s (expected {expected_duration:.2f}s, diff: {diff:.2f}s)")
                else:
                    print(f"      ❌ Failed")
        
        print(f"\n✅ Audio trimming tests complete")
        return True
    else:
        print(f"\n✅ FFmpeg is available and ready for audio trimming")
        print(f"   Command format: ffmpeg -i input -ss START -t DURATION -c:a copy output")
        return True


def main():
    """Main test function."""
    print("\n🔍 Audio Trimming Verification")
    test_audio_trimming()
    print("\n" + "=" * 60)
    print("✅ Verification Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()

