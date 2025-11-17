"""
Test script to verify character identity block formatting.

Tests all 3 phases of the character consistency fixes:
- Phase 1: Structured features formatting
- Phase 2: Multiple characters with proper separation
- Phase 3: No nested "FIXED CHARACTER IDENTITY" blocks
"""

from shared.models.scene import Character, CharacterFeatures
from modules.prompt_generator.prompt_synthesizer import (
    ClipContext,
    _build_identity_from_characters
)


def test_single_character_formatting():
    """Test formatting of a single character (Phase 1 & 3)."""
    print("\n=== Test 1: Single Character Formatting ===")

    # Create character with structured features
    char = Character(
        id="protagonist",
        name="John",
        role="main character",
        features=CharacterFeatures(
            hair="short chestnut brown hair with slight wave, styled neatly",
            face="tan skin tone, square face shape, strong jawline, faint stubble",
            eyes="hazel eyes, thick straight eyebrows",
            clothing="plaid red and white shirt, blue jeans, brown leather boots",
            accessories="silver wristwatch, brown leather belt",
            build="athletic build, approximately 5'11\" height, broad shoulders",
            age="appears mid-20s"
        )
    )

    # Build identity block
    identity_block = _build_identity_from_characters([char])

    print("Identity Block Output:")
    print(identity_block)
    print("\n" + "="*70)

    # Verify no nesting
    assert "FIXED CHARACTER IDENTITY" not in identity_block, "FAILED: Nested 'FIXED CHARACTER IDENTITY' found!"
    assert "CHARACTER IDENTITIES:" in identity_block, "FAILED: Missing 'CHARACTER IDENTITIES:' header"
    assert "Hair:" in identity_block, "FAILED: Missing 'Hair:' field"
    assert "CRITICAL:" in identity_block, "FAILED: Missing 'CRITICAL:' statement"

    print("✓ PASSED: Single character formatting correct")
    print("✓ PASSED: No nested blocks")
    print("✓ PASSED: All features present")


def test_multiple_character_formatting():
    """Test formatting of multiple characters with proper separation (Phase 3)."""
    print("\n=== Test 2: Multiple Character Formatting ===")

    # Create two main characters
    char1 = Character(
        id="protagonist",
        name="John",
        role="main character",
        features=CharacterFeatures(
            hair="short chestnut brown hair with slight wave, styled neatly",
            face="tan skin tone, square face shape, strong jawline, faint stubble",
            eyes="hazel eyes, thick straight eyebrows",
            clothing="plaid red and white shirt, blue jeans, brown leather boots",
            accessories="silver wristwatch, brown leather belt",
            build="athletic build, approximately 5'11\" height, broad shoulders",
            age="appears mid-20s"
        )
    )

    char2 = Character(
        id="love_interest",
        name="Sarah",
        role="love interest",
        features=CharacterFeatures(
            hair="shoulder-length honey blonde hair with soft waves, middle part",
            face="fair skin tone, heart-shaped face, high cheekbones",
            eyes="blue eyes, thin arched eyebrows",
            clothing="floral printed white dress, brown ankle boots",
            accessories="gold hoop earrings, thin gold bracelet",
            build="slim build, approximately 5'6\" height, petite frame",
            age="appears mid-20s"
        )
    )

    # Build identity block
    identity_block = _build_identity_from_characters([char1, char2])

    print("Identity Block Output:")
    print(identity_block)
    print("\n" + "="*70)

    # Verify proper separation
    assert "John (main character):" in identity_block, "FAILED: Missing John's label with role"
    assert "Sarah (love interest):" in identity_block, "FAILED: Missing Sarah's label with role"
    assert identity_block.count("Hair:") == 2, "FAILED: Should have 2 'Hair:' fields (one per character)"
    assert identity_block.count("CRITICAL:") == 1, "FAILED: Should have exactly 1 'CRITICAL:' statement"
    assert "ALL 2 characters" in identity_block, "FAILED: Should mention '2 characters' in CRITICAL statement"

    # Verify no bleeding/concatenation - check that John's clothing line contains expected content
    assert "Clothing: plaid red and white shirt" in identity_block, "FAILED: John's clothing missing or cut off"
    assert "Clothing: floral printed white dress" in identity_block, "FAILED: Sarah's clothing missing or cut off"

    print("✓ PASSED: Multiple characters properly separated")
    print("✓ PASSED: Each character has complete features")
    print("✓ PASSED: No bleeding between characters")


def test_background_character_formatting():
    """Test formatting with background characters (Phase 2)."""
    print("\n=== Test 3: Background Character Formatting ===")

    # Create main character and background character
    char1 = Character(
        id="protagonist",
        name="John",
        role="main character",
        features=CharacterFeatures(
            hair="short chestnut brown hair with slight wave",
            face="tan skin tone, square face shape, strong jawline",
            eyes="hazel eyes, thick straight eyebrows",
            clothing="plaid red and white shirt, blue jeans",
            accessories="silver wristwatch",
            build="athletic build, approximately 5'11\" height",
            age="appears mid-20s"
        )
    )

    bartender = Character(
        id="bartender",
        name="Bartender",
        role="background",
        features=CharacterFeatures(
            hair="short gray hair with receding hairline",
            face="fair skin tone, weathered features, full gray beard",
            eyes="blue eyes, bushy gray eyebrows",
            clothing="white button-up shirt, black vest, black slacks",
            accessories="None",
            build="stocky build, approximately 5'10\" height",
            age="appears late 50s"
        )
    )

    # Build identity block
    identity_block = _build_identity_from_characters([char1, bartender])

    print("Identity Block Output:")
    print(identity_block)
    print("\n" + "="*70)

    # Verify both characters present
    assert "John (main character):" in identity_block, "FAILED: Missing John"
    assert "Bartender (background):" in identity_block, "FAILED: Missing Bartender"
    assert identity_block.count("Hair:") == 2, "FAILED: Should have 2 'Hair:' fields"

    print("✓ PASSED: Background characters included")
    print("✓ PASSED: Role labels correct")


def test_no_nesting_regression():
    """Regression test: ensure no nested 'FIXED CHARACTER IDENTITY' blocks."""
    print("\n=== Test 4: No Nesting Regression Test ===")

    # Create character (simulating old pre-formatted description scenario)
    char = Character(
        id="char_1",
        name="Alice",
        role="protagonist",
        features=CharacterFeatures(
            hair="short brown hair",
            face="medium brown skin tone",
            eyes="dark brown eyes",
            clothing="dark gray hoodie, blue jeans",
            accessories="None",
            build="athletic build, approximately 5'9\" height",
            age="appears late 20s"
        )
    )

    # Build identity block
    identity_block = _build_identity_from_characters([char])

    # Count occurrences of problematic patterns
    nested_count = identity_block.count("FIXED CHARACTER IDENTITY")
    identities_count = identity_block.count("CHARACTER IDENTITIES:")
    critical_count = identity_block.count("CRITICAL:")

    print(f"Occurrences of 'FIXED CHARACTER IDENTITY': {nested_count}")
    print(f"Occurrences of 'CHARACTER IDENTITIES:': {identities_count}")
    print(f"Occurrences of 'CRITICAL:': {critical_count}")
    print("\n" + "="*70)

    assert nested_count == 0, f"FAILED: Found {nested_count} instances of 'FIXED CHARACTER IDENTITY' (should be 0)"
    assert identities_count == 1, f"FAILED: Found {identities_count} instances of 'CHARACTER IDENTITIES:' (should be 1)"
    assert critical_count == 1, f"FAILED: Found {critical_count} instances of 'CRITICAL:' (should be 1)"

    print("✓ PASSED: No 'FIXED CHARACTER IDENTITY' nesting")
    print("✓ PASSED: Exactly 1 'CHARACTER IDENTITIES:' header")
    print("✓ PASSED: Exactly 1 'CRITICAL:' statement")


def test_complete_features():
    """Test that all 7 features are present and complete."""
    print("\n=== Test 5: Complete Features Test ===")

    char = Character(
        id="test_char",
        name="TestCharacter",
        role="main character",
        features=CharacterFeatures(
            hair="short black hair",
            face="olive skin tone, oval face",
            eyes="brown eyes",
            clothing="black t-shirt, blue jeans",
            accessories="silver necklace",
            build="slim build, 5'8\" height",
            age="appears early 30s"
        )
    )

    identity_block = _build_identity_from_characters([char])

    # Check all 7 required features
    required_features = ["Hair:", "Face:", "Eyes:", "Clothing:", "Accessories:", "Build:", "Age:"]
    for feature in required_features:
        assert feature in identity_block, f"FAILED: Missing '{feature}' field"
        # Verify feature is not cut off (has content after colon)
        feature_line = [line for line in identity_block.split("\n") if feature in line][0]
        assert len(feature_line.split(feature)[1].strip()) > 0, f"FAILED: '{feature}' field is empty or cut off"

    print(f"✓ PASSED: All 7 features present: {', '.join(required_features)}")
    print("✓ PASSED: No features cut off")


if __name__ == "__main__":
    print("="*70)
    print("CHARACTER IDENTITY BLOCK FORMATTING TEST SUITE")
    print("Testing Phase 1, 2, and 3 fixes")
    print("="*70)

    try:
        test_single_character_formatting()
        test_multiple_character_formatting()
        test_background_character_formatting()
        test_no_nesting_regression()
        test_complete_features()

        print("\n" + "="*70)
        print("ALL TESTS PASSED! ✓")
        print("="*70)
        print("\nSummary:")
        print("✓ Phase 1: Structured features formatting works correctly")
        print("✓ Phase 2: Background characters are tracked and formatted")
        print("✓ Phase 3: Multiple characters properly separated, no nesting")
        print("✓ Regression: No 'FIXED CHARACTER IDENTITY' nesting issues")
        print("✓ All 7 features present and complete in every character")

    except AssertionError as e:
        print("\n" + "="*70)
        print("TEST FAILED! ✗")
        print("="*70)
        print(f"Error: {e}")
        exit(1)
