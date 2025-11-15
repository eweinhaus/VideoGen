from modules.prompt_generator.reference_mapper import map_references


def test_map_references_handles_missing_references(sample_scene_plan):
    mapping = map_references(sample_scene_plan, None)
    assert mapping[0].scene_reference_url is None
    assert mapping[0].reference_mode == "text_only"


def test_map_references_prefers_scene_urls(sample_scene_plan, sample_reference_images):
    mapping = map_references(sample_scene_plan, sample_reference_images)
    clip0 = mapping[0]
    assert clip0.scene_reference_url.endswith("scene_city_alley.png")
    assert clip0.reference_mode == "scene"

