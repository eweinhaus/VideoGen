"""
Diagnostic script to debug prompt generation issues.

Helps identify:
1. Why LLM optimization is not being used
2. Why character identities are duplicated
3. Why object identities are missing
"""

import asyncio
import sys
import os

# Add project/backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'project', 'backend')
sys.path.insert(0, backend_path)
os.chdir(backend_path)

from shared.config import settings


async def diagnose_prompt_issues():
    print("=" * 80)
    print("PROMPT GENERATION DIAGNOSTICS")
    print("=" * 80)
    print()

    # Check 1: LLM Optimization Setting
    print("1️⃣  LLM OPTIMIZATION CHECK")
    print("-" * 80)
    use_llm = settings.prompt_generator_use_llm
    print(f"PROMPT_GENERATOR_USE_LLM: {use_llm}")

    if not use_llm:
        print("❌ LLM optimization is DISABLED")
        print("   → Prompts will use deterministic templates")
        print("   → To enable: Set PROMPT_GENERATOR_USE_LLM=true in .env")
    else:
        print("✅ LLM optimization is ENABLED")
        print("   → Prompts will be optimized by GPT-4o")
    print()

    # Check 2: Reference Settings
    print("2️⃣  REFERENCE VARIATION SETTINGS")
    print("-" * 80)
    print(f"REFERENCE_VARIATIONS_PER_SCENE: {settings.reference_variations_per_scene}")
    print(f"REFERENCE_VARIATIONS_PER_CHARACTER: {settings.reference_variations_per_character}")
    print(f"REFERENCE_VARIATIONS_PER_OBJECT: {settings.reference_variations_per_object}")
    print()

    # Check 3: Model Settings
    print("3️⃣  MODEL SETTINGS")
    print("-" * 80)
    print(f"USE_REFERENCE_IMAGES: {settings.use_reference_images}")

    # Check environment variables directly
    import os
    print("\nEnvironment Variables:")
    print(f"  REFERENCE_MODEL_SCENES: {os.getenv('REFERENCE_MODEL_SCENES', 'not set')}")
    print(f"  REFERENCE_MODEL_CHARACTERS: {os.getenv('REFERENCE_MODEL_CHARACTERS', 'not set')}")
    print(f"  REFERENCE_MODEL_OBJECTS: {os.getenv('REFERENCE_MODEL_OBJECTS', 'not set')}")
    print()

    # Check 4: Character/Object Identity Block Logic
    print("4️⃣  IDENTITY BLOCK LOGIC CHECK")
    print("-" * 80)

    # Import and inspect the functions
    from modules.prompt_generator.prompt_synthesizer import (
        build_character_identity_block,
        build_object_identity_block,
        ClipContext
    )

    print("✅ build_character_identity_block imported successfully")
    print("✅ build_object_identity_block imported successfully")
    print()

    # Check 5: Test with Mock Data
    print("5️⃣  MOCK DATA TEST")
    print("-" * 80)

    from shared.models.scene import Character, CharacterFeatures, Object, ObjectFeatures

    # Create test character
    test_char = Character(
        id="test_char",
        name="TestPerson",
        role="main character",
        features=CharacterFeatures(
            hair="brown hair",
            face="round face",
            eyes="blue eyes",
            clothing="casual shirt",
            accessories="watch",
            build="average build",
            age="30s"
        ),
        description="TestPerson - old description format"
    )

    # Create test object
    test_obj = Object(
        id="test_guitar",
        name="Test Guitar",
        features=ObjectFeatures(
            object_type="acoustic guitar",
            color="brown",
            material="wood",
            distinctive_features="worn finish",
            size="standard",
            condition="used"
        ),
        importance="primary"
    )

    # Create minimal ClipContext
    from dataclasses import field
    test_context = ClipContext(
        clip_index=0,
        visual_description="test scene",
        motion="static",
        camera_angle="wide",
        style_keywords=["test"],
        color_palette=["#FFFFFF"],
        mood="neutral",
        lighting="natural",
        cinematography="standard",
        scene_reference_url=None,
        character_reference_urls=[],
        beat_intensity="medium",
        duration=3.0,
        scene_ids=[],
        character_ids=["test_char"],
        scene_descriptions=[],
        character_descriptions=["TestPerson - old description"],
        primary_scene_id=None,
        characters=[test_char],  # Structured Character object
        object_ids=["test_guitar"],
        object_descriptions=["Test Guitar"],
        objects=[test_obj],  # Structured Object object
        object_reference_urls=[]
    )

    # Test character identity block
    print("Testing character identity block...")
    char_block = build_character_identity_block(test_context)
    if char_block:
        print("✅ Character identity block generated:")
        print(f"   Length: {len(char_block)} characters")
        print(f"   Contains 'CHARACTER IDENTITIES:': {'CHARACTER IDENTITIES:' in char_block}")
        print(f"   Contains 'CRITICAL:': {'CRITICAL:' in char_block}")
        print()
        print("   Preview (first 300 chars):")
        print(f"   {char_block[:300]}...")
    else:
        print("❌ Character identity block is EMPTY")
    print()

    # Test object identity block
    print("Testing object identity block...")
    obj_block = build_object_identity_block(test_context)
    if obj_block:
        print("✅ Object identity block generated:")
        print(f"   Length: {len(obj_block)} characters")
        print(f"   Contains 'OBJECT IDENTITIES:': {'OBJECT IDENTITIES:' in obj_block}")
        print(f"   Contains 'CRITICAL:': {'CRITICAL:' in obj_block}")
        print(f"   Contains 'Object Type:': {'Object Type:' in obj_block}")
        print()
        print("   Preview (first 300 chars):")
        print(f"   {obj_block[:300]}...")
    else:
        print("❌ Object identity block is EMPTY")
    print()

    # Summary
    print("=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)
    print()

    issues = []
    recommendations = []

    if not use_llm:
        issues.append("LLM optimization is disabled")
        recommendations.append("Set PROMPT_GENERATOR_USE_LLM=true in .env to enable GPT-4o optimization")

    if not char_block:
        issues.append("Character identity block generation failed")
        recommendations.append("Check that Character objects have valid features")

    if not obj_block:
        issues.append("Object identity block generation failed")
        recommendations.append("Check that Object objects have valid features")

    if issues:
        print("⚠️  ISSUES FOUND:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        print()

        print("💡 RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
    else:
        print("✅ All checks passed!")
        print("   - LLM optimization is enabled")
        print("   - Character identity blocks working")
        print("   - Object identity blocks working")

    print()
    print("=" * 80)
    print("To fix character duplication:")
    print("  → Character descriptions should NOT appear in main prompt body")
    print("  → They should ONLY appear in CHARACTER IDENTITIES block at the end")
    print("  → This has been fixed in prompt_synthesizer.py")
    print()
    print("To see object identities in prompts:")
    print("  → Objects must be assigned to the clip in ClipScript.objects")
    print("  → Check that your test scenario includes objects in the clip")
    print("  → Run test_object_references.py to see objects in action")
    print("=" * 80)


if __name__ == "__main__":
    print("\n🔍 Starting diagnostics...\n")
    asyncio.run(diagnose_prompt_issues())
    print("\n✨ Diagnostics complete!\n")
