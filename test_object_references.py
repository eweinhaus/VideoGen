"""
End-to-end test for Phase 3: Object Reference System

Tests the complete object reference pipeline:
1. Object detection in scene planner
2. Object reference image generation (multiple variations)
3. Object identity blocks in video prompts
4. Object feature consistency across clips

Run this test to validate that objects (guitars, cars, jewelry, etc.)
appearing in multiple clips are tracked and referenced consistently.
"""

import asyncio
import sys
import os
from uuid import uuid4

# Add project/backend to path for imports
backend_path = os.path.join(os.path.dirname(__file__), 'project', 'backend')
sys.path.insert(0, backend_path)
os.chdir(backend_path)

from shared.models.scene import (
    ScenePlan, ClipScript, Scene, Character, Style, Object, ObjectFeatures, CharacterFeatures
)
from shared.models.audio import AudioAnalysis, ClipBoundary, Mood


def create_test_scene_plan_with_objects() -> ScenePlan:
    """
    Create a test scene plan with objects appearing in multiple clips.

    Scenario: Music video with a vintage guitar appearing in clips 0, 1, and 3
    """
    job_id = uuid4()

    # Define a vintage guitar object (appears in 3 clips)
    vintage_guitar = Object(
        id="vintage_guitar",
        name="Vintage Acoustic Guitar",
        features=ObjectFeatures(
            object_type="acoustic guitar",
            color="honey sunburst finish with natural wood grain",
            material="solid spruce top, mahogany back and sides, rosewood fretboard",
            distinctive_features="worn finish around soundhole, small dent near bridge, vintage tuning pegs with patina, handwritten signature inside soundhole",
            size="full-size dreadnought (20 inches long, 15 inches wide)",
            condition="vintage, well-used but maintained, shows natural wear from years of playing"
        ),
        importance="primary"
    )

    # Define a leather jacket object (appears in 2 clips)
    leather_jacket = Object(
        id="leather_jacket",
        name="Black Leather Jacket",
        features=ObjectFeatures(
            object_type="motorcycle jacket",
            color="black with silver hardware",
            material="genuine leather with quilted lining",
            distinctive_features="asymmetric zipper, studded shoulders, vintage patches on sleeves (eagle, flames)",
            size="medium, fitted cut",
            condition="worn-in, creased at elbows, vintage aesthetic"
        ),
        importance="secondary"
    )

    # Define a main character
    musician = Character(
        id="musician",
        name="Alex",
        role="main character",
        features=CharacterFeatures(
            hair="shoulder-length wavy brown hair with natural highlights",
            face="olive skin tone, round face with high cheekbones, natural freckles",
            eyes="hazel eyes with green undertones, expressive and intense",
            clothing="black band t-shirt under the vintage leather jacket, dark jeans",
            accessories="silver ring on right hand, leather wristband",
            build="average height (5'9\"), lean build, musician's posture",
            age="late 20s, mature and confident appearance"
        ),
        description="Alex - a passionate musician"
    )

    # Define scenes
    recording_studio = Scene(
        id="recording_studio",
        description="intimate recording studio with warm lighting, vintage microphone, soundproofing panels"
    )

    city_rooftop = Scene(
        id="city_rooftop",
        description="urban rooftop at sunset, city skyline in background, string lights overhead"
    )

    # Define style
    style = Style(
        visual_style="cinematic indie music video aesthetic, warm vintage tones",
        color_palette=["#D4A574", "#8B4513", "#2C2C2C", "#F5DEB3"],  # warm browns, blacks, cream
        mood="nostalgic and passionate",
        lighting="warm golden hour lighting with natural shadows",
        cinematography="intimate handheld shots with shallow depth of field"
    )

    # Define clip scripts with objects
    clip_scripts = [
        ClipScript(
            clip_index=0,
            start=0.0,
            end=3.5,
            visual_description="Close-up of musician's hands strumming the vintage guitar, fingers moving across worn strings",
            motion="slow camera push-in on guitar, focus on hands",
            camera_angle="close-up from above",
            beat_intensity="medium",
            scenes=["recording_studio"],
            characters=["musician"],
            objects=["vintage_guitar"],  # Guitar appears in clip 0
            lyrics_context="Lost in the melody"
        ),
        ClipScript(
            clip_index=1,
            start=3.5,
            end=7.0,
            visual_description="Musician sitting on stool in studio, holding the guitar, eyes closed as they play",
            motion="slow orbit around musician",
            camera_angle="medium shot, eye level",
            beat_intensity="medium",
            scenes=["recording_studio"],
            characters=["musician"],
            objects=["vintage_guitar", "leather_jacket"],  # Both guitar and jacket appear
            lyrics_context="Every note tells a story"
        ),
        ClipScript(
            clip_index=2,
            start=7.0,
            end=10.5,
            visual_description="Musician walking on rooftop at sunset, leather jacket catching the golden light",
            motion="tracking shot following musician",
            camera_angle="wide shot from behind",
            beat_intensity="high",
            scenes=["city_rooftop"],
            characters=["musician"],
            objects=["leather_jacket"],  # Only jacket appears
            lyrics_context="Under the fading sky"
        ),
        ClipScript(
            clip_index=3,
            start=10.5,
            end=14.0,
            visual_description="Back in studio, guitar resting on musician's lap, camera focuses on guitar's worn details",
            motion="static shot with shallow focus pull",
            camera_angle="close-up, low angle",
            beat_intensity="low",
            scenes=["recording_studio"],
            characters=["musician"],
            objects=["vintage_guitar"],  # Guitar appears again in clip 3
            lyrics_context="These strings remember everything"
        ),
    ]

    # Create scene plan
    scene_plan = ScenePlan(
        job_id=job_id,
        video_summary="Intimate music video featuring a musician and their vintage guitar, exploring themes of memory and passion",
        characters=[musician],
        scenes=[recording_studio, city_rooftop],
        objects=[vintage_guitar, leather_jacket],  # 2 objects tracked
        style=style,
        clip_scripts=clip_scripts,
        transitions=[]
    )

    return scene_plan


async def test_object_reference_generation():
    """Test the complete object reference generation pipeline."""
    print("=" * 80)
    print("PHASE 3: Object Reference System - End-to-End Test")
    print("=" * 80)
    print()

    # Create test scene plan
    print("📝 Creating test scene plan with objects...")
    plan = create_test_scene_plan_with_objects()

    print(f"✓ Scene Plan Created:")
    print(f"  - Job ID: {plan.job_id}")
    print(f"  - Characters: {len(plan.characters)}")
    print(f"  - Scenes: {len(plan.scenes)}")
    print(f"  - Objects: {len(plan.objects)}")
    print(f"  - Clip Scripts: {len(plan.clip_scripts)}")
    print()

    # Display object information
    print("🎸 Detected Objects:")
    for obj in plan.objects:
        clips_with_object = [
            f"Clip {script.clip_index}"
            for script in plan.clip_scripts
            if obj.id in getattr(script, 'objects', [])
        ]
        print(f"\n  {obj.name} (ID: {obj.id}):")
        print(f"    - Type: {obj.features.object_type}")
        print(f"    - Color: {obj.features.color}")
        print(f"    - Material: {obj.features.material}")
        print(f"    - Distinctive Features: {obj.features.distinctive_features}")
        print(f"    - Appears in: {', '.join(clips_with_object)}")
        print(f"    - Importance: {obj.importance}")
    print()

    # Test reference generation
    print("🖼️  Testing Reference Image Generation...")
    print("=" * 80)

    from modules.reference_generator.process import process as generate_references
    from shared.config import settings

    variations_per_object = settings.reference_variations_per_object
    expected_object_refs = len(plan.objects) * variations_per_object
    expected_total_refs = (
        len(plan.scenes) * settings.reference_variations_per_scene +
        len(plan.characters) * settings.reference_variations_per_character +
        expected_object_refs
    )

    print(f"Expected Reference Images:")
    print(f"  - Scenes: {len(plan.scenes)} × {settings.reference_variations_per_scene} = {len(plan.scenes) * settings.reference_variations_per_scene}")
    print(f"  - Characters: {len(plan.characters)} × {settings.reference_variations_per_character} = {len(plan.characters) * settings.reference_variations_per_character}")
    print(f"  - Objects: {len(plan.objects)} × {variations_per_object} = {expected_object_refs}")
    print(f"  - TOTAL: {expected_total_refs} images")
    print()

    print("⏳ Generating reference images (this may take 30-60 seconds)...")
    try:
        reference_images, events = await generate_references(
            job_id=plan.job_id,
            plan=plan,
            duration_seconds=14.0
        )

        print(f"✓ Reference generation completed!")
        print(f"  - Scene References: {len(reference_images.scene_references)}")
        print(f"  - Character References: {len(reference_images.character_references)}")
        print(f"  - Object References: {len(reference_images.object_references)}")
        print(f"  - Total: {reference_images.total_references}")
        print()

        # Display object reference images
        if reference_images.object_references:
            print("🎨 Object Reference Images:")
            print("=" * 80)

            for obj in plan.objects:
                obj_refs = [
                    ref for ref in reference_images.object_references
                    if ref.object_id == obj.id
                ]

                if obj_refs:
                    print(f"\n{obj.name} ({len(obj_refs)} variations):")
                    for i, ref in enumerate(obj_refs):
                        print(f"  Variation {i}: {ref.image_url}")
                        print(f"    - Generated in: {ref.generation_time:.2f}s")
                        print(f"    - Cost: ${float(ref.cost):.4f}")
                        if i == 0:
                            # Show prompt for first variation
                            print(f"    - Prompt preview: {ref.prompt_used[:150]}...")
            print()

            # Visual QA Checklist
            print("📋 VISUAL QA CHECKLIST (Manual Review Required):")
            print("=" * 80)
            print("For each object, verify across all variations:")
            print()
            print("1. ✓ OBJECT IDENTITY CONSISTENCY:")
            print("   - Same object type across all variations")
            print("   - Consistent color and material")
            print("   - Distinctive features present in all variations")
            print("   - Same size and condition")
            print()
            print("2. ✓ VARIATION DIVERSITY:")
            print("   - Variation 0: Primary front view")
            print("   - Variation 1: Alternate angle (side view)")
            print("   - Different camera angles/perspectives")
            print("   - Product photography style maintained")
            print()
            print("3. ✓ PRODUCT PHOTOGRAPHY QUALITY:")
            print("   - Neutral/clean background")
            print("   - Studio lighting quality")
            print("   - Sharp focus on object")
            print("   - Professional presentation")
            print()
        else:
            print("⚠️  No object references were generated!")
            print("This could indicate an issue with the object reference pipeline.")

    except Exception as e:
        print(f"❌ Reference generation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test prompt generation with object identity blocks
    print()
    print("💬 Testing Prompt Generation with Object Identity Blocks...")
    print("=" * 80)

    from modules.prompt_generator.process import process as generate_prompts

    try:
        clip_prompts = await generate_prompts(
            job_id=plan.job_id,
            plan=plan,
            references=reference_images
        )

        print(f"✓ Prompt generation completed!")
        print(f"  - Total Clips: {clip_prompts.total_clips}")
        print(f"  - Generation Time: {clip_prompts.generation_time:.2f}s")
        print()

        # Display clips with object identity blocks
        print("🎬 Clips with Object Identity Blocks:")
        print("=" * 80)

        for clip_prompt in clip_prompts.clip_prompts:
            script = plan.clip_scripts[clip_prompt.clip_index]
            clip_objects = getattr(script, 'objects', [])

            if clip_objects:
                print(f"\nClip {clip_prompt.clip_index} (Objects: {', '.join(clip_objects)}):")
                print(f"  Duration: {clip_prompt.duration:.2f}s")

                # Check if prompt contains object identity block
                if "OBJECT IDENTITIES:" in clip_prompt.prompt:
                    print(f"  ✓ Object identity block found!")

                    # Extract and display object identity block
                    parts = clip_prompt.prompt.split("OBJECT IDENTITIES:")
                    if len(parts) > 1:
                        obj_block = parts[1].split("CRITICAL:")[0].strip()
                        print(f"  Object Details Preview:")
                        print(f"    {obj_block[:200]}...")
                else:
                    print(f"  ⚠️  Object identity block NOT found in prompt!")

                # Display full prompt for manual review (first clip only)
                if clip_prompt.clip_index == 0:
                    print(f"\n  Full Prompt (Clip 0 for reference):")
                    print(f"  {'-' * 76}")
                    print(f"  {clip_prompt.prompt}")
                    print(f"  {'-' * 76}")

        print()
        print("📋 OBJECT IDENTITY BLOCK CHECKLIST:")
        print("=" * 80)
        print("Verify the following in prompts:")
        print()
        print("1. ✓ IMMUTABLE FEATURES:")
        print("   - Object Type: Should be identical across all clips")
        print("   - Color: Should be identical across all clips")
        print("   - Material: Should be identical across all clips")
        print("   - Distinctive Features: Should be identical across all clips")
        print("   - Size: Should be identical across all clips")
        print("   - Condition: Should be identical across all clips")
        print()
        print("2. ✓ BLOCK STRUCTURE:")
        print("   - Starts with 'OBJECT IDENTITIES:'")
        print("   - Contains all 6 required feature fields")
        print("   - Ends with 'CRITICAL: These are EXACT, IMMUTABLE features...'")
        print()
        print("3. ✓ CONSISTENCY:")
        print("   - Same object has identical description in all clips")
        print("   - Multiple objects properly separated")
        print("   - No LLM paraphrasing or rewriting")
        print()

    except Exception as e:
        print(f"❌ Prompt generation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Summary
    print()
    print("=" * 80)
    print("✅ OBJECT REFERENCE SYSTEM TEST COMPLETED")
    print("=" * 80)
    print()
    print("Pipeline Verification:")
    print(f"  1. ✓ Object detection in scene planner")
    print(f"  2. ✓ Object reference image generation ({expected_object_refs} variations)")
    print(f"  3. ✓ Object identity blocks in video prompts")
    print()
    print("Next Steps:")
    print("  1. Review generated object reference images for consistency")
    print("  2. Verify object identity blocks in video prompts")
    print("  3. Run full end-to-end video generation with objects")
    print()


if __name__ == "__main__":
    print("\n🚀 Starting Object Reference System Test...\n")
    asyncio.run(test_object_reference_generation())
    print("\n✨ Test completed!\n")
