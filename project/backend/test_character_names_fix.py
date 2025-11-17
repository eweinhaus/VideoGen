"""
Quick test to verify character names are showing up in output.
"""

from shared.models.scene import Character, CharacterFeatures
from modules.prompt_generator.prompt_synthesizer import build_character_identity_block, ClipContext

# Create test characters with names and features
char1 = Character(
    id="char_1",
    name="Sarah",
    role="love interest",
    features=CharacterFeatures(
        hair="long, wavy auburn hair with a side part",
        face="fair skin tone, oval face shape, high cheekbones, no visible freckles",
        eyes="hazel eyes, thick arched eyebrows",
        clothing="light blue plaid shirt with rolled sleeves, dark denim jeans, brown cowboy boots",
        accessories="silver hoop earrings, leather bracelet on left wrist",
        build="slim build, approximately 5'7\" height, narrow shoulders",
        age="appears mid-20s"
    )
)

char2 = Character(
    id="char_2",
    name="John",
    role="main protagonist",
    features=CharacterFeatures(
        hair="short, sandy blonde hair with a slight wave, styled in a casual quiff",
        face="light tan skin tone, square face shape, dimple on the left cheek",
        eyes="blue eyes, straight eyebrows",
        clothing="red flannel shirt, dark blue jeans, brown leather belt",
        accessories="silver watch on left wrist, simple gold ring on right hand",
        build="athletic build, approximately 6'0\" height, broad shoulders",
        age="appears late-20s"
    )
)

# Create clip context with characters
context = ClipContext(
    clip_index=0,
    visual_description="Test",
    motion=None,
    camera_angle=None,
    style_keywords=[],
    color_palette=[],
    mood="test",
    lighting="test",
    cinematography="test",
    scene_reference_url=None,
    character_reference_urls=[],
    beat_intensity="medium",
    duration=5.0,
    scene_ids=[],
    character_ids=["char_1", "char_2"],
    scene_descriptions=[],
    character_descriptions=[],
    primary_scene_id=None,
    characters=[char1, char2]  # Pass Character objects
)

# Build identity block
identity_block = build_character_identity_block(context)

print("\n" + "="*80)
print("CHARACTER IDENTITY BLOCK OUTPUT")
print("="*80 + "\n")
print(identity_block)
print("\n" + "="*80)

# Verify
checks = {
    "Has 'Sarah' name": "Sarah" in identity_block,
    "Has 'John' name": "John" in identity_block,
    "Has role labels": "(love interest)" in identity_block and "(main protagonist)" in identity_block,
    "Characters separated": identity_block.count("Hair:") == 2,
    "Has CRITICAL statement": "CRITICAL:" in identity_block,
    "No nested FIXED": identity_block.count("FIXED CHARACTER IDENTITY") == 0
}

print("\nVERIFICATION:")
all_passed = True
for check, passed in checks.items():
    status = "✅" if passed else "❌"
    print(f"{status} {check}")
    if not passed:
        all_passed = False

print("\n" + "="*80)
if all_passed:
    print("✅ ALL CHECKS PASSED - Character names are showing correctly!")
else:
    print("❌ SOME CHECKS FAILED - Issue still present")
print("="*80 + "\n")
