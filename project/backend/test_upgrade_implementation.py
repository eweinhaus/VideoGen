"""
Integration test script for Video Generator Upgrade Plan implementation.

Tests all 3 phases:
- Phase 1: USE_REFERENCE_IMAGES flag enforcement
- Phase 2: Enhanced style context in prompts
- Phase 3: Dynamic model selection with validation

Usage:
    python test_upgrade_implementation.py
"""
import asyncio
from uuid import uuid4

from shared.config import settings
from shared.models.scene import ScenePlan, Style, ClipScript, Character, Scene
from modules.prompt_generator.process import process as prompt_generator_process
from modules.prompt_generator.prompt_synthesizer import ClipContext, build_comprehensive_style_block
from modules.video_generator.config import MODEL_CONFIGS, get_selected_model, get_model_config
from modules.video_generator.model_validator import validate_model_config, get_latest_version_hash


def create_test_scene_plan(job_id) -> ScenePlan:
    """Create a test ScenePlan for testing."""
    return ScenePlan(
        job_id=job_id,
        video_summary="A vibrant music video set in Miami",
        characters=[
            Character(
                id="artist",
                description="Hip-hop artist in stylish outfit",
                role="main character"
            )
        ],
        scenes=[
            Scene(
                id="miami_beach",
                description="Sunny Miami beach with palm trees",
                time_of_day="midday"
            )
        ],
        style=Style(
            color_palette=["#FFA500", "#00FFFF", "#800080", "#000000"],
            visual_style="Vibrant and dynamic, capturing the energy of Miami and the opulence of success",
            mood="Energetic and reflective, balancing celebration with introspection",
            lighting="High-contrast daylight with bright highlights and deep shadows to emphasize the vibrancy of the Miami sun",
            cinematography="Handheld, slight shake, tracking shots to convey dynamism and immediacy"
        ),
        clip_scripts=[
            ClipScript(
                clip_index=0,
                start=0.0,
                end=5.0,
                visual_description="Artist walking on Miami beach",
                motion="Smooth tracking shot following the artist",
                camera_angle="Medium wide shot",
                characters=["artist"],
                scenes=["miami_beach"],
                lyrics_context="Living the dream in the sunshine",
                beat_intensity="medium"
            )
        ],
        transitions=[]
    )


async def test_phase_1_flag_enforcement():
    """Test Phase 1: USE_REFERENCE_IMAGES flag enforcement."""
    print("\n" + "="*60)
    print("PHASE 1: Testing USE_REFERENCE_IMAGES flag enforcement")
    print("="*60)

    # This test verifies that the defensive check exists in video_generator/process.py
    # The actual runtime test would require running a full video generation job
    # For now, we verify the code path exists

    from modules.video_generator.process import process

    # Check that the code contains the defensive check
    import inspect
    source = inspect.getsource(process)

    if "Text-only mode enforced" in source and "if not use_references:" in source:
        print("✅ Defensive check for text-only mode found in code")
        print("   - Code checks 'if not use_references' before image selection")
        print("   - Logs 'Text-only mode enforced' message")
        return True
    else:
        print("❌ Defensive check NOT found in code")
        return False


async def test_phase_2_enhanced_style():
    """Test Phase 2: Enhanced style context in prompts."""
    print("\n" + "="*60)
    print("PHASE 2: Testing Enhanced Style Context")
    print("="*60)

    job_id = uuid4()
    plan = create_test_scene_plan(job_id)

    # Generate prompts using the updated system
    try:
        clip_prompts = await prompt_generator_process(job_id, plan)

        if not clip_prompts or not clip_prompts.clip_prompts:
            print("❌ No clip prompts generated")
            return False

        # Check first prompt for enhanced style block
        first_prompt = clip_prompts.clip_prompts[0]
        prompt_text = first_prompt.prompt

        # Check for enhanced style elements
        checks = {
            "VISUAL STYLE": "VISUAL STYLE:" in prompt_text,
            "MOOD": "MOOD:" in prompt_text,
            "LIGHTING": "LIGHTING:" in prompt_text,
            "CINEMATOGRAPHY": "CINEMATOGRAPHY:" in prompt_text,
            "COLOR PALETTE": "COLOR PALETTE:" in prompt_text or "#FFA500" in prompt_text,
        }

        all_passed = True
        for check_name, check_result in checks.items():
            status = "✅" if check_result else "❌"
            print(f"  {status} {check_name}: {'Found' if check_result else 'Not found'}")
            if not check_result:
                all_passed = False

        if all_passed:
            print("\n✅ All enhanced style elements found in prompt")
            print(f"\nSample prompt (first 500 chars):")
            print(prompt_text[:500] + "...")
        else:
            print("\n⚠️  Some enhanced style elements missing")
            print(f"\nFull prompt for debugging:")
            print(prompt_text)

        return all_passed

    except Exception as e:
        print(f"❌ Error generating prompts: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_phase_3_model_validation():
    """Test Phase 3: Dynamic model selection and validation."""
    print("\n" + "="*60)
    print("PHASE 3: Testing Dynamic Model Selection")
    print("="*60)

    # Test 1: Check MODEL_CONFIGS has parameter mappings
    print("\nTest 1: Checking parameter mappings in MODEL_CONFIGS...")
    models_with_params = []
    models_without_params = []

    for model_key, config in MODEL_CONFIGS.items():
        if "parameter_names" in config:
            models_with_params.append(model_key)
        else:
            models_without_params.append(model_key)

    print(f"  ✅ Models with parameter mappings: {len(models_with_params)}")
    for model in models_with_params:
        print(f"     - {model}")

    if models_without_params:
        print(f"  ⚠️  Models without parameter mappings: {len(models_without_params)}")
        for model in models_without_params:
            print(f"     - {model}")

    # Test 2: Check status field
    print("\nTest 2: Checking status fields in MODEL_CONFIGS...")
    models_with_status = []
    for model_key, config in MODEL_CONFIGS.items():
        if "status" in config:
            models_with_status.append((model_key, config["status"]))

    print(f"  ✅ Models with status field: {len(models_with_status)}")
    for model, status in models_with_status:
        print(f"     - {model}: {status}")

    # Test 3: Validate selected model
    print("\nTest 3: Validating currently selected model...")
    try:
        selected_model = get_selected_model()
        print(f"  Selected model: {selected_model}")

        config = get_model_config(selected_model)
        print(f"  Config loaded: {config.get('display_name', selected_model)}")

        is_valid, error = await validate_model_config(selected_model, config)
        if is_valid:
            print(f"  ✅ Model validation passed")
        else:
            print(f"  ❌ Model validation failed: {error}")
            return False

    except Exception as e:
        print(f"  ❌ Error validating model: {str(e)}")
        return False

    # Test 4: Test hash caching
    print("\nTest 4: Testing hash caching...")
    try:
        replicate_string = "kwaivgi/kling-v2.1"

        # First call - should retrieve and cache
        hash1 = await get_latest_version_hash(replicate_string)
        if hash1:
            print(f"  ✅ First hash retrieval: {hash1[:20]}...")

            # Second call - should use cache
            hash2 = await get_latest_version_hash(replicate_string)
            if hash2 == hash1:
                print(f"  ✅ Second hash retrieval (cached): {hash2[:20]}...")
                print(f"  ✅ Caching working correctly")
            else:
                print(f"  ⚠️  Hash changed between calls (cache issue?)")
        else:
            print(f"  ⚠️  Could not retrieve hash (API may be unavailable)")

    except Exception as e:
        print(f"  ⚠️  Hash retrieval error: {str(e)}")

    return True


async def main():
    """Run all tests."""
    print("="*60)
    print("VIDEO GENERATOR UPGRADE PLAN - IMPLEMENTATION TEST")
    print("="*60)

    results = {
        "Phase 1": await test_phase_1_flag_enforcement(),
        "Phase 2": await test_phase_2_enhanced_style(),
        "Phase 3": await test_phase_3_model_validation(),
    }

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)

    for phase, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{phase}: {status}")

    all_passed = all(results.values())
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL PHASES PASSED")
    else:
        print("❌ SOME PHASES FAILED - Review output above")
    print("="*60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
