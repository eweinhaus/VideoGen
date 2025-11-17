"""
Test script for Phase 2 enhancement: Appending structured style after LLM optimization.

This verifies that:
1. Base prompts are built without comprehensive style block
2. LLM optimizes action descriptions
3. Structured style block is appended after optimization
4. Final prompts have consistent format across all clips
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.prompt_generator.process import process
from shared.models.scene import (
    Character,
    ClipScript,
    Scene,
    ScenePlan,
    Style,
)
from shared.config import settings

async def test_style_append():
    """Test that structured style is appended after LLM optimization."""

    print("=" * 60)
    print("TESTING: Structured Style Block Appending")
    print("=" * 60)

    # Mock scene plan with full style information
    style = Style(
        visual_style="Cinematic, vibrant Miami aesthetic with modern urban energy",
        mood="Energetic and reflective, balancing celebration with introspection",
        lighting="High-contrast daylight with bright highlights and deep shadows",
        cinematography="Smooth tracking shots with handheld camera work for dynamic movement",
        color_palette=["#FF6B35", "#00D9FF", "#6B3FA0"]
    )

    character = Character(
        id="char_1",
        name="Artist",
        description="Confident artist with stylish presence",
        role="main character"
    )

    scene = Scene(
        id="scene_1",
        description="Miami Beach with palm trees and skyline",
        reference_url=None
    )

    # Create 3 clips to test consistency
    clip_scripts = [
        ClipScript(
            clip_index=0,
            visual_description="Artist strolls along Miami Beach",
            motion="Walking forward with confident stride",
            camera_angle="Medium tracking shot",
            beat_intensity="medium",
            start=0.0,
            end=5.0,
            scenes={"scene_1"},
            characters={"char_1"},
            lyrics_context="Living the dream in the sunshine"
        ),
        ClipScript(
            clip_index=1,
            visual_description="Artist raises arms to the sky celebrating",
            motion="Dynamic arm movement reaching upward",
            camera_angle="Low angle looking up",
            beat_intensity="high",
            start=5.0,
            end=10.0,
            scenes={"scene_1"},
            characters={"char_1"},
            lyrics_context="Success is sweet like the ocean breeze"
        ),
        ClipScript(
            clip_index=2,
            visual_description="Artist sits contemplating the ocean",
            motion="Slow, reflective sitting movement",
            camera_angle="Wide static shot",
            beat_intensity="low",
            start=10.0,
            end=15.0,
            scenes={"scene_1"},
            characters={"char_1"},
            lyrics_context="Sometimes I wonder where it all leads"
        ),
    ]

    from uuid import uuid4
    
    plan = ScenePlan(
        job_id=uuid4(),
        video_summary="A vibrant music video set in Miami",
        style=style,
        characters=[character],
        scenes=[scene],
        clip_scripts=clip_scripts,
        transitions=[]
    )

    # Enable LLM optimization for this test
    original_use_llm = settings.prompt_generator_use_llm
    settings.prompt_generator_use_llm = True

    try:
        print("\n1. Processing with LLM optimization enabled...")
        from uuid import uuid4
        test_job_id = uuid4()
        result = await process(
            job_id=test_job_id,
            plan=plan,
            references=None,
            beat_timestamps=None
        )

        print(f"\n2. Generated {len(result.clip_prompts)} clip prompts")

        # Check each prompt for structured style elements
        print("\n3. Verifying structured style blocks in each prompt...\n")

        expected_elements = [
            "VISUAL STYLE:",
            "MOOD:",
            "LIGHTING:",
            "CINEMATOGRAPHY:",
            "COLOR PALETTE:"
        ]

        all_passed = True

        for clip_prompt in result.clip_prompts:
            print(f"--- Clip {clip_prompt.clip_index} ---")

            # Check for each expected element
            found_elements = []
            missing_elements = []

            for element in expected_elements:
                if element in clip_prompt.prompt:
                    found_elements.append(element)
                    print(f"  ✅ {element} Found")
                else:
                    missing_elements.append(element)
                    print(f"  ❌ {element} NOT FOUND")

            if missing_elements:
                all_passed = False
                print(f"\n  ⚠️  Missing {len(missing_elements)} elements")
            else:
                print(f"\n  ✅ All structured elements present")

            # Show the full prompt for debugging
            print(f"\nFull prompt:\n{clip_prompt.prompt}\n")
            print("-" * 60)

        # Final result
        print("\n" + "=" * 60)
        if all_passed:
            print("✅ SUCCESS: All clips have structured style blocks")
            print("=" * 60)
        else:
            print("❌ FAILURE: Some clips missing structured elements")
            print("=" * 60)

        return all_passed

    finally:
        # Restore original setting
        settings.prompt_generator_use_llm = original_use_llm


async def test_consistency_across_clips():
    """Test that style blocks are identical across all clips."""

    print("\n" + "=" * 60)
    print("TESTING: Style Block Consistency Across Clips")
    print("=" * 60)

    # Create scene plan with 5 clips
    style = Style(
        visual_style="Cyberpunk dystopia with neon aesthetics",
        mood="Dark and mysterious with underlying tension",
        lighting="Low-key lighting with vibrant neon accents",
        cinematography="Gritty handheld shots with dutch angles",
        color_palette=["#FF00FF", "#00FFFF", "#000000"]
    )

    clip_scripts = [
        ClipScript(
            clip_index=i,
            visual_description=f"Scene {i} description",
            motion="Dynamic movement",
            camera_angle="Medium shot",
            beat_intensity="medium",
            start=i * 5.0,
            end=(i + 1) * 5.0,
            scenes=set(),
            characters=set(),
            lyrics_context=f"Lyrics {i}"
        )
        for i in range(5)
    ]

    from uuid import uuid4
    
    plan = ScenePlan(
        job_id=uuid4(),
        video_summary="A cyberpunk dystopia music video",
        style=style,
        characters=[],
        scenes=[],
        clip_scripts=clip_scripts,
        transitions=[]
    )

    # Enable LLM
    original_use_llm = settings.prompt_generator_use_llm
    settings.prompt_generator_use_llm = True

    try:
        from uuid import uuid4
        test_job_id = uuid4()
        result = await process(
            job_id=test_job_id,
            plan=plan,
            references=None,
            beat_timestamps=None
        )

        # Extract style blocks from each prompt
        style_blocks = []
        for clip_prompt in result.clip_prompts:
            prompt = clip_prompt.prompt

            # Find the style block (starts with "VISUAL STYLE:")
            if "VISUAL STYLE:" in prompt:
                style_start = prompt.index("VISUAL STYLE:")
                style_block = prompt[style_start:]
                style_blocks.append(style_block)
            else:
                style_blocks.append(None)

        # Check if all style blocks are identical
        if None in style_blocks:
            print("❌ FAILURE: Some clips missing style blocks")
            return False

        first_style = style_blocks[0]
        all_identical = all(style == first_style for style in style_blocks)

        if all_identical:
            print("✅ SUCCESS: All style blocks are IDENTICAL across all clips")
            print(f"\nConsistent style block:\n{first_style}")
        else:
            print("❌ FAILURE: Style blocks differ across clips")
            for i, style in enumerate(style_blocks):
                print(f"\nClip {i} style block:\n{style}")

        return all_identical

    finally:
        settings.prompt_generator_use_llm = original_use_llm


async def main():
    """Run all tests."""

    print("\n" + "=" * 60)
    print("PHASE 2 STYLE APPEND TESTS")
    print("=" * 60)

    # Test 1: Verify structured elements present
    test1_passed = await test_style_append()

    # Test 2: Verify consistency across clips
    test2_passed = await test_consistency_across_clips()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Test 1 (Structured Elements): {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Test 2 (Consistency):         {'✅ PASSED' if test2_passed else '❌ FAILED'}")

    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED")
    else:
        print("\n⚠️  SOME TESTS FAILED")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
