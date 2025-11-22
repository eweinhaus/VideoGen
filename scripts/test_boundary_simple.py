"""Simplified test to understand the boundary issue"""

# From the screenshot:
# - Duration: 41.5 seconds  
# - BPM: 99.4
# - 68 beats detected
# - Clips ending at 30.3s (should go to 41.5s)

# First 20 beats from screenshot
beats = [1.21, 1.81, 2.41, 3.02, 3.60, 4.20, 4.78, 5.36, 5.94, 6.50, 
         7.15, 7.73, 8.34, 8.92, 9.52, 10.08, 10.66, 11.26, 11.87, 12.47]

# Extrapolate remaining beats (68 total) with ~0.6s interval (99.4 BPM)
beat_interval = 60.0 / 99.4  # ~0.604s
while len(beats) < 68:
    beats.append(beats[-1] + beat_interval)

print(f"Generated {len(beats)} beats")
print(f"Last beat at: {beats[-1]:.2f}s")
print(f"Total duration: 41.5s")
print(f"Gap after last beat: {41.5 - beats[-1]:.2f}s\n")

# Song structure from screenshot:
# - Intro: 0.0s - 7.1s (low energy)
# - Verse: 7.1s - 17.9s (low energy)  
# - Verse: 17.9s - 41.5s (medium energy) <- THIS IS THE PROBLEM SEGMENT

segments = [
    {"type": "intro", "start": 0.0, "end": 7.1, "energy": "low"},
    {"type": "verse", "start": 7.1, "end": 17.9, "energy": "low"},
    {"type": "verse", "start": 17.9, "end": 41.5, "energy": "medium"}
]

print("Segments:")
for i, seg in enumerate(segments):
    duration = seg['end'] - seg['start']
    beats_in_seg = [b for b in beats if seg['start'] <= b <= seg['end']]
    print(f"  {i+1}. {seg['type']}: {seg['start']}s - {seg['end']}s ({duration:.1f}s) - {len(beats_in_seg)} beats")

# Check the problem segment (segment 3)
problem_seg = segments[2]
seg_start = problem_seg['start']
seg_end = problem_seg['end']
seg_duration = seg_end - seg_start

beats_in_segment = [b for b in beats if seg_start <= b <= seg_end]
beats_relative = [b - seg_start for b in beats_in_segment]

print(f"\n📌 PROBLEM SEGMENT: {seg_start}s - {seg_end}s ({seg_duration:.1f}s)")
print(f"   Beats in segment: {len(beats_relative)}")
if beats_relative:
    print(f"   First beat: {beats_relative[0]:.2f}s (absolute: {beats_in_segment[0]:.2f}s)")
    print(f"   Last beat: {beats_relative[-1]:.2f}s (absolute: {beats_in_segment[-1]:.2f}s)")
    print(f"   Gap after last beat: {seg_duration - beats_relative[-1]:.2f}s")
else:
    print(f"   ❌ NO BEATS IN SEGMENT!")

# The issue: If the algorithm stops when it runs out of beats,
# it won't cover the full duration (seg_duration = 23.6s)

print(f"\n❓ HYPOTHESIS:")
print(f"   If boundaries stop at last beat ({beats_relative[-1] if beats_relative else 'N/A'}s relative),")
print(f"   then absolute time would be ~{seg_start + beats_relative[-1] if beats_relative else 'N/A'}s")
print(f"   This matches the observed clip end at 30.3s!")
print(f"\n   The algorithm needs to extend the last clip to cover")
print(f"   the remaining {seg_duration - beats_relative[-1]:.2f}s" if beats_relative else "N/A")

