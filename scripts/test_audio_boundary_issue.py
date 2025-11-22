"""Test script to reproduce the audio boundary issue"""
import sys
sys.path.insert(0, '/Users/mylessjs/Desktop/VideoGen/project/backend')

from modules.audio_parser.boundaries import generate_boundaries_with_breakpoints, validate_boundaries
from shared.models.audio import Breakpoint

# Simulating your audio:
# - Duration: 41.5 seconds
# - 68 beats detected
# - Clips ending at 30.3s (should go to 41.5s)

# From screenshot: First 20 beats
beats = [1.21, 1.81, 2.41, 3.02, 3.60, 4.20, 4.78, 5.36, 5.94, 6.50, 
         7.15, 7.73, 8.34, 8.92, 9.52, 10.08, 10.66, 11.26, 11.87, 12.47]

# Extrapolate remaining beats (68 total) with ~0.6s interval (99.4 BPM)
beat_interval = 60.0 / 99.4  # ~0.604s
while len(beats) < 68:
    beats.append(beats[-1] + beat_interval)

print(f"Generated {len(beats)} beats")
print(f"Last beat at: {beats[-1]:.2f}s")
print(f"Total duration: 41.5s")
print(f"Gap: {41.5 - beats[-1]:.2f}s")

# Test with last segment (17.9s - 41.5s = 23.6s segment)
segment_start = 17.9
segment_end = 41.5
segment_duration = segment_end - segment_start

# Get beats within segment
segment_beats_absolute = [b for b in beats if segment_start <= b <= segment_end]
segment_beats_relative = [b - segment_start for b in segment_beats_absolute]

print(f"\nSegment: {segment_start}s - {segment_end}s ({segment_duration:.1f}s)")
print(f"Beats in segment: {len(segment_beats_relative)}")
if segment_beats_relative:
    print(f"First beat in segment: {segment_beats_relative[0]:.2f}s")
    print(f"Last beat in segment: {segment_beats_relative[-1]:.2f}s")

# Generate boundaries
boundaries = generate_boundaries_with_breakpoints(
    beat_timestamps=segment_beats_relative,
    bpm=99.4,
    total_duration=segment_duration,
    breakpoints=[],  # No breakpoints for simplicity
    max_clips=None,
    segment_type="verse",
    beat_intensity="medium"
)

print(f"\nGenerated {len(boundaries)} boundaries:")
for i, boundary in enumerate(boundaries):
    # Convert back to absolute time
    abs_start = boundary.start + segment_start
    abs_end = boundary.end + segment_start
    print(f"  Clip {i+1}: {abs_start:.1f}s - {abs_end:.1f}s (duration: {boundary.duration:.1f}s)")

if boundaries:
    last_end_relative = boundaries[-1].end
    last_end_absolute = last_end_relative + segment_start
    print(f"\nLast boundary ends at: {last_end_absolute:.1f}s (should be {segment_end:.1f}s)")
    gap = segment_end - last_end_absolute
    if gap > 0.1:
        print(f"❌ GAP DETECTED: {gap:.1f}s of audio not covered!")
    else:
        print(f"✅ Full coverage achieved")
    
    # Validate
    is_valid, errors = validate_boundaries(boundaries, segment_duration)
    if not is_valid:
        print(f"\n❌ Validation errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print(f"\n✅ All boundaries valid")

