from modules.prompt_generator.prompt_synthesizer import (
    ClipContext,
    DEFAULT_NEGATIVE_PROMPT,
    build_clip_prompt,
    compute_word_count,
    summarize_color_palette,
)


def _context() -> ClipContext:
    return ClipContext(
        clip_index=0,
        visual_description="Protagonist walks through neon rain toward camera.",
        motion="Slow push in while rain streaks diagonally.",
        camera_angle="Medium wide, slightly low angle.",
        style_keywords=["cyberpunk", "melancholic"],
        color_palette=["#00FFFF", "#FF00FF"],
        mood="melancholic",
        lighting="high-contrast neon",
        cinematography="tracking shots",
        scene_reference_url="https://cdn.example.com/scene.png",
        character_reference_urls=["https://cdn.example.com/character.png"],
        beat_intensity="medium",
        duration=5.0,
        scene_ids=["city_alley"],
        character_ids=["protagonist"],
        scene_descriptions=["Rain-slicked alley glowing with cyan signs"],
        character_descriptions=["Young woman in reflective visor"],
        primary_scene_id="city_alley",
        lyrics_context="I walk alone",
    )


def test_build_clip_prompt_includes_core_sections():
    prompt, negative = build_clip_prompt(_context())
    # When character references are used, visual description becomes scene setting
    assert "Rain-slicked alley" in prompt or "Protagonist walks" in prompt
    # Check for style elements
    assert "melancholic" in prompt or "MOOD:" in prompt
    assert negative == DEFAULT_NEGATIVE_PROMPT
    # Note: Word count limit was removed to allow more comprehensive prompts
    # but should stay under 1000 words
    assert compute_word_count(prompt) <= 1000


def test_summarize_color_palette_handles_multiple_colors():
    summary = summarize_color_palette(["#FF00FF", "#00FFFF", "#FFFFFF"])
    assert "neon" in summary.lower()

