"""
Test script for Phase 3 features.

Tests:
1. Model selection from VIDEO_MODEL env var
2. Beat alignment logic
3. Reference variation generation
"""

import os
import sys

def test_model_selection():
    """Test that model selection works from VIDEO_MODEL env var."""
    print("\n=== Test 1: Model Selection ===")

    from modules.video_generator.config import get_selected_model, get_model_config, MODEL_CONFIGS

    # Test default model
    model = get_selected_model()
    print(f"  Selected model: {model}")
    assert model in MODEL_CONFIGS, f"Model {model} not in MODEL_CONFIGS"

    # Test model config retrieval
    config = get_model_config(model)
    print(f"  Model type: {config['type']}")
    print(f"  Supports: {config['resolutions']}")
    print(f"  Estimated cost (5s): ${config['estimated_cost_5s']}")

    # Test invalid model fallback
    os.environ["VIDEO_MODEL"] = "invalid_model"
    from importlib import reload
    import modules.video_generator.config as vg_config
    reload(vg_config)
    fallback_model = vg_config.get_selected_model()
    print(f"  Invalid model fallback: {fallback_model}")
    assert fallback_model == "kling_v21", "Should fallback to kling_v21"

    # Reset env
    if "VIDEO_MODEL" in os.environ:
        del os.environ["VIDEO_MODEL"]

    print("  PASS: Model selection works")


def test_beat_alignment():
    """Test beat alignment logic."""
    print("\n=== Test 2: Beat Alignment ===")

    from modules.prompt_generator.process import extract_clip_beats

    # Test beat extraction
    all_beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    clip_start = 1.0
    clip_end = 3.0

    beat_metadata = extract_clip_beats(clip_start, clip_end, all_beats)

    print(f"  All beats: {all_beats}")
    print(f"  Clip range: {clip_start}s - {clip_end}s")
    print(f"  Beats in clip: {beat_metadata['beat_timestamps_in_clip']}")
    print(f"  Beat count: {beat_metadata['beat_count']}")
    print(f"  Primary beat: {beat_metadata['primary_beat_time']}")

    # Verify beats are normalized to clip-relative time
    assert len(beat_metadata['beat_timestamps_in_clip']) > 0, "Should have beats in range"
    assert all(0 <= b <= (clip_end - clip_start) for b in beat_metadata['beat_timestamps_in_clip']), \
        "Beats should be clip-relative (0-based)"

    # Test empty beats
    empty_metadata = extract_clip_beats(0, 5, [])
    assert empty_metadata['beat_count'] == 0, "Empty beats should return 0 count"
    assert empty_metadata['primary_beat_time'] is None, "Empty beats should have no primary"

    print("  PASS: Beat alignment works")


def test_reference_variations():
    """Test reference variation prompt generation."""
    print("\n=== Test 3: Reference Variations ===")

    from modules.reference_generator.prompts import get_variation_suffix, synthesize_prompt
    from shared.models.scene import Style

    # Test variation suffixes
    var0 = get_variation_suffix(0)
    var1 = get_variation_suffix(1)
    var2 = get_variation_suffix(2)

    print(f"  Variation 0: {var0}")
    print(f"  Variation 1: {var1}")
    print(f"  Variation 2: {var2}")

    assert var0 != var1, "Variations should be different"
    assert var1 != var2, "Variations should be different"

    # Test prompt synthesis with variations
    style = Style(
        visual_style="cinematic",
        color_palette=["#FF5733", "#C70039"],
        mood="dramatic",
        lighting="moody",
        cinematography="wide-angle"
    )

    description = "A young warrior with flowing hair"

    prompt_base = synthesize_prompt(description, style, "character", variation_index=0)
    prompt_var1 = synthesize_prompt(description, style, "character", variation_index=1)

    print(f"  Base prompt length: {len(prompt_base)}")
    print(f"  Var1 prompt length: {len(prompt_var1)}")

    # Variation prompts should be different for characters
    assert prompt_base != prompt_var1, "Character variations should produce different prompts"
    assert var1 in prompt_var1, "Variation suffix should be in prompt"

    # Scene prompts should ignore variation_index
    scene_base = synthesize_prompt("Forest clearing", style, "scene", variation_index=0)
    scene_var = synthesize_prompt("Forest clearing", style, "scene", variation_index=1)
    assert scene_base == scene_var, "Scene prompts should ignore variation_index"

    print("  PASS: Reference variations work")


def test_reference_rotation():
    """Test reference rotation through variations."""
    print("\n=== Test 4: Reference Rotation ===")

    from modules.prompt_generator.reference_mapper import ReferenceIndex, map_clip_references
    from shared.models.scene import ClipScript

    # Create mock reference index with variations
    char_urls = {
        "char1": "url1_var0",
        "char1_var1": "url1_var1",
        "char1_var2": "url1_var2",
    }

    index = ReferenceIndex(
        scene_urls={},
        character_urls=char_urls,
        status="success"
    )

    # Create mock clip
    clip = ClipScript(
        clip_index=0,
        start=0.0,
        end=5.0,
        visual_description="Test",
        motion="slow",
        camera_angle="medium",
        characters=["char1"],
        scenes=[],
        beat_intensity="medium"
    )

    # Test rotation: clip 0 should use var0, clip 1 should use var1, etc.
    mapping0 = map_clip_references(clip, index, clip_index=0)
    mapping1 = map_clip_references(clip, index, clip_index=1)
    mapping2 = map_clip_references(clip, index, clip_index=2)
    mapping3 = map_clip_references(clip, index, clip_index=3)  # Should wrap around

    print(f"  Clip 0 uses: {mapping0.character_reference_urls}")
    print(f"  Clip 1 uses: {mapping1.character_reference_urls}")
    print(f"  Clip 2 uses: {mapping2.character_reference_urls}")
    print(f"  Clip 3 uses: {mapping3.character_reference_urls}")

    assert mapping0.character_reference_urls != mapping1.character_reference_urls, "Should rotate"
    assert mapping1.character_reference_urls != mapping2.character_reference_urls, "Should rotate"
    assert mapping0.character_reference_urls == mapping3.character_reference_urls, "Should wrap around"

    print("  PASS: Reference rotation works")


if __name__ == "__main__":
    print("=" * 60)
    print("PHASE 3 FEATURE TESTS")
    print("=" * 60)

    try:
        test_model_selection()
        test_beat_alignment()
        test_reference_variations()
        test_reference_rotation()

        print("\n" + "=" * 60)
        print("ALL PHASE 3 FEATURES TESTED SUCCESSFULLY")
        print("=" * 60)
        sys.exit(0)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
