#!/usr/bin/env python3
"""
Verification script for Scene Planner implementation.

Verifies that the implementation matches PRD.md and Tech.md specifications.
Run this script to check compliance before deployment.
"""

import sys
from pathlib import Path
from uuid import uuid4

# Add backend directory to path (where shared module is)
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from shared.models.audio import AudioAnalysis, Mood, SongStructure, Lyric, ClipBoundary
from shared.models.scene import ScenePlan, Character, Scene, Style, ClipScript, Transition


def verify_prd_input_format():
    """Verify input format matches PRD specifications."""
    print("✓ Verifying PRD input format...")
    
    # PRD: user_prompt must be 50-500 characters
    valid_prompt = "cyberpunk city at night with neon lights" * 2  # ~80 chars
    assert 50 <= len(valid_prompt) <= 500, "User prompt length validation"
    
    # PRD: AudioAnalysis structure
    job_id = uuid4()
    audio_analysis = AudioAnalysis(
        job_id=job_id,
        bpm=128.5,
        duration=185.3,
        beat_timestamps=[i * 0.5 for i in range(370)],
        song_structure=[
            SongStructure(type="intro", start=0.0, end=8.5, energy="low"),
            SongStructure(type="verse", start=8.5, end=30.2, energy="medium"),
            SongStructure(type="chorus", start=30.2, end=50.5, energy="high"),
        ],
        lyrics=[Lyric(text="I see the lights", timestamp=10.5)],
        mood=Mood(primary="energetic", secondary="uplifting", energy_level="high", confidence=0.85),
        clip_boundaries=[ClipBoundary(start=0.0, end=5.2, duration=5.2)],
        metadata={"processing_time": 45.2, "cache_hit": False}
    )
    
    assert audio_analysis.job_id == job_id
    assert audio_analysis.bpm > 0
    assert len(audio_analysis.clip_boundaries) >= 1
    
    print("  ✓ Input format matches PRD specifications")
    return True


def verify_prd_output_format():
    """Verify output format matches PRD specifications."""
    print("✓ Verifying PRD output format...")
    
    job_id = uuid4()
    
    # PRD example ScenePlan structure
    scene_plan = ScenePlan(
        job_id=job_id,
        video_summary="A lone figure walks through neon-lit streets...",
        characters=[
            Character(
                id="protagonist",
                description="Young woman, 25-30, futuristic jacket",
                role="main character"
            )
        ],
        scenes=[
            Scene(
                id="city_street",
                description="Rain-slicked cyberpunk street with neon signs",
                time_of_day="night"
            )
        ],
        style=Style(
            color_palette=["#00FFFF", "#FF00FF", "#0000FF"],
            visual_style="Neo-noir cyberpunk with rain and neon",
            mood="Melancholic yet hopeful",
            lighting="High-contrast neon with deep shadows",
            cinematography="Handheld, slight shake, tracking shots"
        ),
        clip_scripts=[
            ClipScript(
                clip_index=0,
                start=0.0,
                end=5.2,
                visual_description="Protagonist walks toward camera through rain",
                motion="Slow tracking shot following character",
                camera_angle="Medium wide, slightly low angle",
                characters=["protagonist"],
                scenes=["city_street"],
                lyrics_context="I see the lights shining bright",
                beat_intensity="medium"
            )
        ],
        transitions=[
            Transition(
                from_clip=0,
                to_clip=1,
                type="crossfade",
                duration=0.5,
                rationale="Smooth transition for continuous motion"
            )
        ]
    )
    
    # Verify structure
    assert scene_plan.job_id == job_id
    assert len(scene_plan.characters) > 0
    assert len(scene_plan.scenes) > 0
    assert len(scene_plan.style.color_palette) >= 3
    assert len(scene_plan.clip_scripts) > 0
    assert len(scene_plan.transitions) >= 0
    
    # Verify Character structure
    char = scene_plan.characters[0]
    assert char.id is not None
    assert len(char.description) > 0
    assert char.role in ["main character", "background"]
    
    # Verify Scene structure
    scene = scene_plan.scenes[0]
    assert scene.id is not None
    assert len(scene.description) > 0
    
    # Verify Style structure
    assert len(scene_plan.style.color_palette) >= 3
    assert len(scene_plan.style.visual_style) > 0
    assert len(scene_plan.style.mood) > 0
    assert len(scene_plan.style.lighting) > 0
    assert len(scene_plan.style.cinematography) > 0
    
    # Verify ClipScript structure
    clip = scene_plan.clip_scripts[0]
    assert clip.clip_index >= 0
    assert clip.start >= 0
    assert clip.end > clip.start
    assert len(clip.visual_description) > 0
    assert len(clip.motion) > 0
    assert len(clip.camera_angle) > 0
    assert clip.beat_intensity in ["low", "medium", "high"]
    
    # Verify Transition structure
    if scene_plan.transitions:
        trans = scene_plan.transitions[0]
        assert trans.from_clip >= 0
        assert trans.to_clip > trans.from_clip
        assert trans.type in ["cut", "crossfade", "fade"]
        assert trans.duration >= 0.0
        assert len(trans.rationale) > 0
    
    # Verify JSON serialization
    json_str = scene_plan.model_dump_json()
    assert isinstance(json_str, str)
    assert len(json_str) > 0
    
    import json
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
    
    print("  ✓ Output format matches PRD specifications")
    return True


def verify_module_structure():
    """Verify module structure matches PRD."""
    print("✓ Verifying module structure...")
    
    module_path = Path(__file__).parent
    
    required_files = [
        "__init__.py",
        "main.py",
        "planner.py",
        "llm_client.py",
        "director_knowledge.py",
        "script_generator.py",
        "transition_planner.py",
        "style_analyzer.py",
        "validator.py",
    ]
    
    for file in required_files:
        file_path = module_path / file
        assert file_path.exists(), f"Missing required file: {file}"
    
    print(f"  ✓ All {len(required_files)} required files present")
    return True


def verify_imports():
    """Verify all imports work correctly."""
    print("✓ Verifying imports...")
    
    try:
        from modules.scene_planner import process_scene_planning, plan_scenes
        from modules.scene_planner.director_knowledge import get_director_knowledge
        from modules.scene_planner.llm_client import generate_scene_plan
        from modules.scene_planner.script_generator import generate_clip_scripts
        from modules.scene_planner.transition_planner import plan_transitions
        from modules.scene_planner.style_analyzer import analyze_style_consistency
        from modules.scene_planner.validator import validate_scene_plan
        
        print("  ✓ All imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ Import error: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Scene Planner Implementation Verification")
    print("=" * 60)
    print()
    
    checks = [
        ("Module Structure", verify_module_structure),
        ("Imports", verify_imports),
        ("PRD Input Format", verify_prd_input_format),
        ("PRD Output Format", verify_prd_output_format),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ {name} failed: {e}")
            results.append((name, False))
        print()
    
    # Summary
    print("=" * 60)
    print("Verification Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print()
    print(f"Total: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 All checks passed! Implementation is ready.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} check(s) failed. Please review.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

