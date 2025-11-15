from shared.models.scene import Style

from modules.prompt_generator.style_synthesizer import (
    apply_style_keywords,
    ensure_global_consistency,
    extract_style_keywords,
)


def test_extract_style_keywords_returns_deduped_tokens():
    style = Style(
        color_palette=["#00FFFF", "#FF00FF"],
        visual_style="Neo-noir cyberpunk",
        mood="Melancholic",
        lighting="High-contrast neon",
        cinematography="Wide tracking shots",
    )
    keywords = extract_style_keywords(style)
    assert "neo-noir cyberpunk" in keywords[0]
    assert "#00FFFF" in keywords


def test_apply_style_keywords_injects_phrase():
    prompt = "A detailed prompt"
    updated = apply_style_keywords(prompt, ["cyberpunk", "melancholic"])
    assert "cyberpunk" in updated


def test_ensure_global_consistency_appends_keywords():
    prompts = ["Scene one prompt"]
    consistent = ensure_global_consistency(prompts, ["cyberpunk"])
    assert "cyberpunk" in consistent[0].lower()

