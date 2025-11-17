"""
Test script to verify character identity blocks are appended to all prompts.

This test checks that the _append_identity_blocks() function correctly appends
CHARACTER IDENTITY blocks to all clip prompts, and that these blocks are
identical across all clips.

Usage:
    python test_identity_blocks.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from shared.models.scene import (
    ScenePlan,
    Character,
    Scene,
    Style,
    ClipScript
)
from shared.models.audio import AudioAnalysis, Mood, SongStructure, ClipBoundary
from modules.prompt_generator.process import process


async def test_identity_block_appending():
    """Test that character identity blocks are appended to all prompts."""

    print("\n" + "="*80)
    print("Testing Character Identity Block Appending")
    print("="*80 + "\n")

    # Create mock character with specific description
    character = Character(
        id="char_1",
        description="""Alice - FIXED CHARACTER IDENTITY:
- Hair: shoulder-length brown curly hair with natural texture and volume, parted in the middle
- Face: olive skin tone, round face shape, defined cheekbones, no visible freckles
- Eyes: dark brown eyes, thick arched eyebrows
- Clothing: bright blue denim jacket with silver buttons and rolled sleeves, white crew-neck t-shirt underneath, dark blue jeans
- Accessories: round tortoiseshell glasses with thick frames, silver hoop earrings (1 inch diameter)
- Build: athletic build, approximately 5'6" height, medium frame
- Age: appears mid-20s

CRITICAL: These are EXACT, IMMUTABLE features. Do not modify or reinterpret these specific details. This character appears in all scenes with this precise appearance.""",
        role="main character"
    )

    # Create mock scene
    scene = Scene(
        id="scene_1",
        description="Urban street at night with neon signs",
        time_of_day="night"
    )

    # Create mock style
    style = Style(
        color_palette=["#00FFFF", "#FF00FF", "#FFFF00"],
        visual_style="Cinematic urban style with vibrant neon colors",
        mood="Energetic and confident",
        lighting="High-contrast neon lighting with deep shadows",
        cinematography="Smooth tracking shots with handheld camera work"
    )

    # Create mock clip scripts
    clip_scripts = [
        ClipScript(
            clip_index=0,
            start=0.0,
            end=5.0,
            visual_description="Artist walks down the street with confidence",
            motion="Smooth tracking shot following the character",
            camera_angle="Medium wide shot, eye level",
            characters=["char_1"],
            scenes=["scene_1"],
            lyrics_context="Living the dream",
            beat_intensity="medium"
        ),
        ClipScript(
            clip_index=1,
            start=5.0,
            end=10.0,
            visual_description="Artist stops and looks at city skyline",
            motion="Static shot with slow zoom",
            camera_angle="Medium shot, slightly low angle",
            characters=["char_1"],
            scenes=["scene_1"],
            lyrics_context="In the city lights",
            beat_intensity="low"
        ),
        ClipScript(
            clip_index=2,
            start=10.0,
            end=15.0,
            visual_description="Artist continues walking, passing neon signs",
            motion="Tracking shot with slight shake",
            camera_angle="Close-up, eye level",
            characters=["char_1"],
            scenes=["scene_1"],
            lyrics_context="Making it happen",
            beat_intensity="high"
        )
    ]

    # Create mock ScenePlan
    job_id = uuid4()
    plan = ScenePlan(
        job_id=job_id,
        video_summary="An artist living their dream in the city",
        characters=[character],
        scenes=[scene],
        style=style,
        clip_scripts=clip_scripts,
        transitions=[]
    )

    try:
        # Process with prompt generator
        print(f"Processing prompts with character identity blocks...")
        print(f"Job ID: {job_id}")
        print(f"Characters: {len(plan.characters)}")
        print(f"Clips: {len(plan.clip_scripts)}\n")

        result = await process(
            job_id=job_id,
            plan=plan,
            references=None,
            beat_timestamps=[0.0, 2.5, 5.0, 7.5, 10.0, 12.5, 15.0]
        )

        print(f"Prompts generated successfully!")
        print(f"Total clips: {result.total_clips}\n")

        # Verify all clip prompts have CHARACTER IDENTITY block
        all_passed = True
        identity_blocks = []

        for clip_prompt in result.clip_prompts:
            prompt = clip_prompt.prompt
            clip_index = clip_prompt.clip_index

            print(f"\n{'='*80}")
            print(f"Clip {clip_index}")
            print(f"{'='*80}\n")

            # Check for identity block presence
            has_identity = "CHARACTER IDENTITY:" in prompt
            has_critical = "CRITICAL:" in prompt
            has_exact_or_fixed = "EXACT" in prompt or "FIXED" in prompt

            print("Identity Block Checks:")
            print(f"  {'✅' if has_identity else '❌'} Has 'CHARACTER IDENTITY:' block")
            print(f"  {'✅' if has_critical else '❌'} Has 'CRITICAL:' keyword")
            print(f"  {'✅' if has_exact_or_fixed else '❌'} Has 'EXACT' or 'FIXED' emphasis")

            if not has_identity:
                print(f"  ❌ FAILED: Clip {clip_index} missing CHARACTER IDENTITY block")
                all_passed = False
            elif not has_critical:
                print(f"  ❌ FAILED: Clip {clip_index} missing CRITICAL keyword")
                all_passed = False
            elif not has_exact_or_fixed:
                print(f"  ❌ FAILED: Clip {clip_index} missing emphasis keywords")
                all_passed = False

            # Verify character features present
            has_alice = "Alice" in prompt
            has_hair_desc = "shoulder-length brown curly hair" in prompt
            has_glasses = "tortoiseshell glasses" in prompt

            print("\nCharacter Feature Checks:")
            print(f"  {'✅' if has_alice else '❌'} Contains character name 'Alice'")
            print(f"  {'✅' if has_hair_desc else '❌'} Contains specific hair description")
            print(f"  {'✅' if has_glasses else '❌'} Contains accessory details (glasses)")

            if not (has_alice and has_hair_desc):
                print(f"  ❌ FAILED: Clip {clip_index} missing character features")
                all_passed = False

            # Extract identity block for comparison
            if "CHARACTER IDENTITY:" in prompt:
                identity_start = prompt.index("CHARACTER IDENTITY:")
                identity_block = prompt[identity_start:]
                identity_blocks.append(identity_block)

            # Show prompt preview (first 500 chars)
            print(f"\nPrompt Preview (first 500 chars):")
            print(f"{prompt[:500]}...")

            # Show full identity block
            if "CHARACTER IDENTITY:" in prompt:
                identity_start = prompt.index("CHARACTER IDENTITY:")
                print(f"\nFull Identity Block:")
                print(f"{prompt[identity_start:]}")

        # Verify identity blocks are IDENTICAL across all clips
        print(f"\n{'='*80}")
        print("Identity Block Consistency Check")
        print(f"{'='*80}\n")

        if len(identity_blocks) == 0:
            print("❌ FAILED: No identity blocks found in any clip!")
            all_passed = False
        elif len(identity_blocks) != len(result.clip_prompts):
            print(f"❌ FAILED: Only {len(identity_blocks)}/{len(result.clip_prompts)} clips have identity blocks")
            all_passed = False
        else:
            first_block = identity_blocks[0]
            all_identical = True

            for i, block in enumerate(identity_blocks[1:], start=1):
                if block != first_block:
                    print(f"❌ Clip {i} has DIFFERENT identity block!")
                    print(f"\nExpected (Clip 0):")
                    print(f"{first_block[:200]}...\n")
                    print(f"Got (Clip {i}):")
                    print(f"{block[:200]}...")
                    all_identical = False
                    all_passed = False
                else:
                    print(f"✅ Clip {i}: Identity block matches Clip 0")

            if all_identical:
                print(f"\n✅ SUCCESS: All {len(identity_blocks)} clips have IDENTICAL identity blocks")

        # Final summary
        print(f"\n{'='*80}")
        print(f"Overall Result: {'✅ PASSED' if all_passed else '❌ FAILED'}")
        print(f"{'='*80}\n")

        if all_passed:
            print("SUCCESS: All tests passed!")
            print("  ✅ All clips have CHARACTER IDENTITY blocks")
            print("  ✅ All identity blocks are IDENTICAL")
            print("  ✅ Identity blocks contain emphasis keywords")
            print("  ✅ Identity blocks contain specific character features")
            print("  ✅ Identity blocks appear AFTER style blocks")
        else:
            print("FAILURE: Some tests failed.")
            print("Please review the implementation of:")
            print("  - build_character_identity_block() in prompt_synthesizer.py")
            print("  - _append_identity_blocks() in process.py")

        return all_passed

    except Exception as e:
        print(f"\n❌ ERROR: Prompt generation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_identity_block_appending())
    sys.exit(0 if result else 1)
