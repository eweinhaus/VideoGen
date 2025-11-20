#!/usr/bin/env python3
"""
Test script for Phase 1 & 2: Scene and Character Reference Variations

Tests:
- Phase 1: Multi-angle scene references (2 variations per scene)
- Phase 2: Multi-angle character references with identity preservation (2 variations per character)

Usage:
    python test_reference_variations.py

This script will:
1. Create a test ScenePlan with 2 scenes and 2 characters
2. Generate reference images with variations
3. Display image URLs for manual visual QA
4. Check for variation_index in results
"""

import asyncio
import sys
import os
from uuid import uuid4
from decimal import Decimal
from pathlib import Path

# Add project root to path
backend_path = os.path.join(os.path.dirname(__file__), 'project', 'backend')
sys.path.insert(0, backend_path)

# Set working directory to backend so .env file is found by pydantic_settings
os.chdir(backend_path)

# Verify .env file exists
env_file = Path(backend_path) / '.env'
if env_file.exists():
    print(f"✓ Found .env file at: {env_file}")
else:
    print(f"⚠️  Warning: .env file not found at {env_file}")
    print("   Make sure environment variables are set or .env file exists")

from shared.models.scene import (
    Character, CharacterFeatures, Scene, Style, ScenePlan,
    ClipScript, Transition
)
from shared.config import settings
from modules.reference_generator.process import process as reference_generator_process


def create_test_scene_plan() -> ScenePlan:
    """
    Create a test ScenePlan with 2 scenes and 2 characters.

    Returns:
        ScenePlan with well-defined scenes and characters for variation testing
    """
    job_id = uuid4()

    # Character 1: Alice (detailed features for identity preservation)
    alice = Character(
        id="alice",
        name="Alice",
        role="main character",
        features=CharacterFeatures(
            hair="shoulder-length brown curly hair with natural texture and volume, parted in the middle",
            face="olive skin tone, round face shape, defined cheekbones, no visible freckles",
            eyes="dark brown eyes, thick arched eyebrows",
            clothing="bright blue denim jacket with silver buttons and rolled sleeves, white crew-neck t-shirt underneath, dark blue jeans",
            accessories="round tortoiseshell glasses with thick frames, silver hoop earrings (1 inch diameter)",
            build="athletic build, approximately 5'6\" height, medium frame",
            age="appears mid-20s"
        )
    )

    # Character 2: Marcus (detailed features for identity preservation)
    marcus = Character(
        id="marcus",
        name="Marcus",
        role="supporting character",
        features=CharacterFeatures(
            hair="short black hair in tight coils, shaped fade on sides (1/4 inch), slightly longer on top (1 inch)",
            face="deep brown skin tone, angular face shape, high cheekbones, thin mustache and goatee",
            eyes="dark brown eyes, thick straight eyebrows, intense gaze",
            clothing="black oversized hoodie with white drawstrings, dark gray joggers, white Nike Cortez sneakers",
            accessories="small diamond stud earrings in both ears, thin gold chain necklace, black digital watch on left wrist",
            build="lean athletic build, approximately 5'10\" height, narrow shoulders",
            age="appears early 30s"
        )
    )

    # Scene 1: Cinema Bar Interior
    cinema_bar = Scene(
        id="cinema_bar",
        description="dimly lit cinema bar interior, neon signs casting colored light on polished wood surfaces, vintage movie posters on brick walls, leather bar stools, art deco fixtures",
        time_of_day="night"
    )

    # Scene 2: City Street at Dusk
    city_street = Scene(
        id="city_street",
        description="urban city street at dusk, glowing streetlights, wet pavement reflecting neon signs, tall buildings, light traffic, pedestrians walking",
        time_of_day="dusk"
    )

    # Style
    style = Style(
        color_palette=["#FF0000", "#000000", "#FFD700"],  # Red, Black, Gold
        visual_style="cinematic noir",
        mood="mysterious",
        lighting="dramatic low-key lighting with colored accent lights",
        cinematography="moody cinematic photography with high contrast"
    )

    # Minimal clip scripts (required but not used for reference generation)
    clip_scripts = [
        ClipScript(
            clip_index=0,
            start=0.0,
            end=5.0,
            visual_description="Alice enters the cinema bar",
            motion="smooth dolly in",
            camera_angle="medium shot",
            characters=["alice"],
            scenes=["cinema_bar"],
            beat_intensity="medium"
        ),
        ClipScript(
            clip_index=1,
            start=5.0,
            end=10.0,
            visual_description="Marcus walks down the city street",
            motion="tracking shot",
            camera_angle="wide shot",
            characters=["marcus"],
            scenes=["city_street"],
            beat_intensity="medium"
        )
    ]

    # Minimal transitions (required but not used)
    transitions = [
        Transition(
            from_clip=0,
            to_clip=1,
            type="cut",
            duration=0.0,
            rationale="Hard cut for contrast"
        )
    ]

    return ScenePlan(
        job_id=job_id,
        video_summary="Test video for scene and character reference variations",
        characters=[alice, marcus],
        scenes=[cinema_bar, city_street],
        style=style,
        clip_scripts=clip_scripts,
        transitions=transitions
    )


async def test_reference_variations():
    """
    Test reference image generation with variations.

    Expected Results:
    - 2 scenes × 2 variations = 4 scene images
    - 2 characters × 2 variations = 4 character images
    - Total: 8 reference images

    Visual QA:
    - Scene variations should show SAME scene from different angles
    - Character variations should show SAME person from different angles/poses
    """
    print("=" * 80)
    print("REFERENCE VARIATIONS TEST - Phases 1 & 2")
    print("=" * 80)
    print()

    # Get settings (already loaded as singleton)
    print(f"Configuration:")
    print(f"  - REFERENCE_VARIATIONS_PER_SCENE: {settings.reference_variations_per_scene}")
    print(f"  - REFERENCE_VARIATIONS_PER_CHARACTER: {settings.reference_variations_per_character}")
    print()

    # Create test scene plan
    print("Creating test ScenePlan...")
    plan = create_test_scene_plan()
    print(f"  ✓ Job ID: {plan.job_id}")
    print(f"  ✓ Scenes: {len(plan.scenes)} ({', '.join(s.id for s in plan.scenes)})")
    print(f"  ✓ Characters: {len(plan.characters)} ({', '.join(c.id for c in plan.characters)})")
    print()

    # Expected counts
    expected_scene_images = len(plan.scenes) * settings.reference_variations_per_scene
    expected_character_images = len(plan.characters) * settings.reference_variations_per_character
    expected_total = expected_scene_images + expected_character_images

    print(f"Expected Reference Images:")
    print(f"  - Scenes: {len(plan.scenes)} × {settings.reference_variations_per_scene} = {expected_scene_images} images")
    print(f"  - Characters: {len(plan.characters)} × {settings.reference_variations_per_character} = {expected_character_images} images")
    print(f"  - Total: {expected_total} images")
    print(f"  - Estimated cost: ${expected_total * 0.005:.3f}")
    print()

    # Generate references
    print("Generating reference images...")
    print("(This may take 30-60 seconds depending on concurrency)")
    print()

    try:
        # Call reference generator (returns tuple: reference_images, events)
        references, events = await reference_generator_process(
            job_id=plan.job_id,
            plan=plan,
            duration_seconds=10.0  # Short duration for testing
        )

        print("=" * 80)
        print("GENERATION COMPLETE")
        print("=" * 80)
        print()

        # Results summary
        print(f"Status: {references.status}")
        print(f"Total references: {references.total_references}")
        print(f"Scene references: {len(references.scene_references)}")
        print(f"Character references: {len(references.character_references)}")
        print(f"Generation time: {references.total_generation_time:.1f}s")
        print(f"Total cost: ${float(references.total_cost):.3f}")
        print()

        # Verify counts
        if references.total_references != expected_total:
            print(f"⚠️  WARNING: Expected {expected_total} images, got {references.total_references}")
        else:
            print(f"✅ Image count matches expectation ({expected_total})")
        print()

        # Scene references analysis
        print("=" * 80)
        print("PHASE 1: SCENE REFERENCES (Multi-Angle)")
        print("=" * 80)
        print()

        # Group by scene_id
        scenes_by_id = {}
        for ref in references.scene_references:
            scene_id = ref.scene_id
            if scene_id not in scenes_by_id:
                scenes_by_id[scene_id] = []
            scenes_by_id[scene_id].append(ref)

        for scene_id, refs in scenes_by_id.items():
            print(f"Scene: {scene_id}")
            print(f"  Variations: {len(refs)}")
            for ref in sorted(refs, key=lambda r: r.variation_index):
                print(f"    [{ref.variation_index}] {ref.image_url}")
                # Extract camera angle from prompt
                if "wide establishing" in ref.prompt_used.lower():
                    print(f"        Angle: Wide establishing shot")
                elif "medium shot" in ref.prompt_used.lower():
                    print(f"        Angle: Medium shot")
                elif "close-up" in ref.prompt_used.lower():
                    print(f"        Angle: Close-up detail")
            print()

            # Visual QA instructions
            print(f"  📋 Visual QA Checklist for {scene_id}:")
            print(f"    [ ] All variations show the SAME scene")
            print(f"    [ ] Different camera angles/perspectives")
            print(f"    [ ] Same style, lighting, color palette")
            print(f"    [ ] Recognizable as the same location")
            print()

        # Character references analysis
        print("=" * 80)
        print("PHASE 2: CHARACTER REFERENCES (Identity-Preserving)")
        print("=" * 80)
        print()

        # Group by character_id
        characters_by_id = {}
        for ref in references.character_references:
            char_id = ref.character_id
            if char_id not in characters_by_id:
                characters_by_id[char_id] = []
            characters_by_id[char_id].append(ref)

        for char_id, refs in characters_by_id.items():
            # Get character details
            char = next((c for c in plan.characters if c.id == char_id), None)
            char_name = char.name if char else char_id

            print(f"Character: {char_name} ({char_id})")
            print(f"  Variations: {len(refs)}")

            if char and char.features:
                print(f"  Expected Features:")
                print(f"    - Hair: {char.features.hair[:60]}...")
                print(f"    - Face: {char.features.face[:60]}...")
                print(f"    - Clothing: {char.features.clothing[:60]}...")

            print(f"  Generated Images:")
            for ref in sorted(refs, key=lambda r: r.variation_index):
                print(f"    [{ref.variation_index}] {ref.image_url}")
                # Extract view type from prompt
                if ref.variation_index == 0:
                    print(f"        View: Frontal portrait")
                elif "profile" in ref.prompt_used.lower():
                    print(f"        View: Profile (side angle)")
                elif "three-quarter" in ref.prompt_used.lower():
                    print(f"        View: Three-quarter")
                elif "full body" in ref.prompt_used.lower():
                    print(f"        View: Full body")
                elif "action" in ref.prompt_used.lower():
                    print(f"        View: Dynamic action")
            print()

            # Visual QA instructions
            print(f"  📋 CRITICAL Visual QA Checklist for {char_name}:")
            print(f"    [ ] All variations show the SAME PERSON")
            print(f"    [ ] Hair: Same color, length, texture, style")
            print(f"    [ ] Face: Same skin tone, face shape, features")
            print(f"    [ ] Eyes: Same color and eyebrow style")
            print(f"    [ ] Clothing: Same outfit in all variations")
            print(f"    [ ] Accessories: Same glasses/jewelry")
            print(f"    [ ] Build: Same body type and height")
            print(f"    [ ] Age: Same apparent age")
            print(f"    [ ] Only camera angle/pose changes (NOT identity)")
            print()

        # Overall success criteria
        print("=" * 80)
        print("SUCCESS CRITERIA")
        print("=" * 80)
        print()
        print("Phase 1 (Scenes): ✅ PASS if all scene variations show same scene")
        print("Phase 2 (Characters): ✅ PASS if 95%+ of character variations show same person")
        print()
        print("If character variations show different people:")
        print("  - Layer 3 (seed consistency) may be needed")
        print("  - Consider adjusting guidance_scale (currently 9.0)")
        print("  - Review prompts for identity anchoring")
        print()

        # Save results summary
        summary_file = f"reference_variations_test_{plan.job_id}.txt"
        with open(summary_file, 'w') as f:
            f.write(f"Reference Variations Test Results\n")
            f.write(f"Job ID: {plan.job_id}\n")
            f.write(f"Status: {references.status}\n")
            f.write(f"Total References: {references.total_references}\n")
            f.write(f"Generation Time: {references.total_generation_time:.1f}s\n")
            f.write(f"Total Cost: ${float(references.total_cost):.3f}\n")
            f.write(f"\n")

            f.write(f"Scene References ({len(references.scene_references)}):\n")
            for scene_id, refs in scenes_by_id.items():
                f.write(f"  {scene_id}: {len(refs)} variations\n")
                for ref in sorted(refs, key=lambda r: r.variation_index):
                    f.write(f"    [{ref.variation_index}] {ref.image_url}\n")
            f.write(f"\n")

            f.write(f"Character References ({len(references.character_references)}):\n")
            for char_id, refs in characters_by_id.items():
                char = next((c for c in plan.characters if c.id == char_id), None)
                char_name = char.name if char else char_id
                f.write(f"  {char_name} ({char_id}): {len(refs)} variations\n")
                for ref in sorted(refs, key=lambda r: r.variation_index):
                    f.write(f"    [{ref.variation_index}] {ref.image_url}\n")

        print(f"📄 Results saved to: {summary_file}")
        print()

        return True

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print()
    success = asyncio.run(test_reference_variations())
    print()

    if success:
        print("✅ Test completed successfully")
        print()
        print("Next steps:")
        print("  1. Review the image URLs above")
        print("  2. Open each image in a browser")
        print("  3. Complete the Visual QA checklists")
        print("  4. Verify scene variations show same scene from different angles")
        print("  5. CRITICAL: Verify character variations show SAME person")
        print()
        sys.exit(0)
    else:
        print("❌ Test failed")
        sys.exit(1)
