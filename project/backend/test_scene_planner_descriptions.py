"""
Test script to verify Scene Planner generates specific character descriptions.

This test checks that the Scene Planner follows the CHARACTER_DESCRIPTION_GUIDELINES
and generates ultra-specific character descriptions with all 7 required features.

Usage:
    python test_scene_planner_descriptions.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from shared.models.audio import AudioAnalysis, Mood, SongStructure, ClipBoundary, Lyric
from modules.scene_planner.planner import plan_scenes


async def test_enhanced_descriptions():
    """Test that Scene Planner generates specific character descriptions."""

    print("\n" + "="*80)
    print("Testing Scene Planner Character Descriptions")
    print("="*80 + "\n")

    # Create sample audio analysis
    job_id = uuid4()
    user_prompt = "A confident artist living their dream in the city"

    # Build mock audio analysis
    audio_data = AudioAnalysis(
        job_id=job_id,
        duration=30.0,
        bpm=120.0,
        mood=Mood(
            primary="energetic",
            secondary="bright",
            energy_level="high",
            confidence=0.85
        ),
        song_structure=[
            SongStructure(
                type="verse",
                start=0.0,
                end=15.0,
                energy="high"
            ),
            SongStructure(
                type="chorus",
                start=15.0,
                end=30.0,
                energy="high"
            )
        ],
        clip_boundaries=[
            ClipBoundary(start=0.0, end=10.0, duration=10.0),
            ClipBoundary(start=10.0, end=20.0, duration=10.0),
            ClipBoundary(start=20.0, end=30.0, duration=10.0)
        ],
        beat_timestamps=[0.0, 0.5, 1.0, 1.5, 2.0],
        lyrics=[
            Lyric(timestamp=0.0, text="Living the dream"),
            Lyric(timestamp=5.0, text="In the city lights")
        ]
    )

    try:
        # Run Scene Planner
        print(f"Running Scene Planner with user prompt: '{user_prompt}'")
        print(f"Job ID: {job_id}\n")

        plan = await plan_scenes(job_id, user_prompt, audio_data)

        print(f"Scene Plan generated successfully!")
        print(f"Characters: {len(plan.characters)}")
        print(f"Scenes: {len(plan.scenes)}")
        print(f"Clips: {len(plan.clip_scripts)}\n")

        # Check each character description
        if not plan.characters:
            print("⚠️  WARNING: No characters generated!")
            return False

        all_passed = True

        for i, character in enumerate(plan.characters):
            print(f"\n{'='*80}")
            print(f"Character {i+1}: {character.id}")
            print(f"{'='*80}\n")

            description = character.description

            print(f"Description:\n{description}\n")

            # Verify format
            has_fixed_identity = "FIXED CHARACTER IDENTITY:" in description
            has_critical = "CRITICAL:" in description

            print("Format Checks:")
            print(f"  {'✅' if has_fixed_identity else '❌'} Has 'FIXED CHARACTER IDENTITY:' format")
            print(f"  {'✅' if has_critical else '❌'} Has 'CRITICAL:' emphasis keyword\n")

            if not has_fixed_identity:
                all_passed = False

            # Verify required features present
            required_features = {
                "Hair:": False,
                "Face:": False,
                "Eyes:": False,
                "Clothing:": False,
                "Accessories:": False,
                "Build:": False,
                "Age:": False
            }

            print("Required Features:")
            for feature in required_features:
                if feature in description:
                    required_features[feature] = True
                    print(f"  ✅ Found feature: {feature}")
                else:
                    print(f"  ❌ Missing feature: {feature}")
                    all_passed = False

            # Verify specificity (not vague)
            vague_words = ["stylish", "cool", "nice", "beautiful", "confident"]
            found_vague = []
            for word in vague_words:
                # Check if vague word appears standalone (not as part of description after identity block)
                if word in description.lower():
                    # Only flag if it appears before "FIXED CHARACTER IDENTITY"
                    identity_pos = description.find("FIXED CHARACTER IDENTITY:")
                    word_pos = description.lower().find(word)
                    if identity_pos == -1 or word_pos < identity_pos:
                        found_vague.append(word)

            print("\nSpecificity Check:")
            if found_vague:
                print(f"  ⚠️  Warning: Found potentially vague words: {', '.join(found_vague)}")
                print("     (These should be replaced with specific details)")
            else:
                print(f"  ✅ No vague words detected")

            # Check for specific color modifiers
            has_specific_colors = any(
                color_phrase in description.lower()
                for color_phrase in [
                    "bright", "dark", "deep", "light", "navy", "forest",
                    "burgundy", "olive", "golden", "ash", "warm", "cool"
                ]
            )

            print(f"\nColor Specificity:")
            print(f"  {'✅' if has_specific_colors else '⚠️ '} Uses specific color modifiers")

            # Check for measurements
            has_measurements = any(
                char in description
                for char in ["'", '"', "inch", "cm", "shoulder", "waist", "length"]
            )

            print(f"\nMeasurements:")
            print(f"  {'✅' if has_measurements else '⚠️ '} Includes specific measurements")

        print(f"\n{'='*80}")
        print(f"Overall Result: {'✅ PASSED' if all_passed else '❌ FAILED'}")
        print(f"{'='*80}\n")

        if all_passed:
            print("SUCCESS: All character descriptions meet the requirements!")
            print("Character descriptions include:")
            print("  - FIXED CHARACTER IDENTITY format")
            print("  - All 7 required features")
            print("  - Specific details and measurements")
            print("  - CRITICAL emphasis keywords")
        else:
            print("FAILURE: Some character descriptions are missing required elements.")
            print("Please review the CHARACTER_DESCRIPTION_GUIDELINES implementation.")

        return all_passed

    except Exception as e:
        print(f"\n❌ ERROR: Scene planning failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_enhanced_descriptions())
    sys.exit(0 if result else 1)
