"""Test fixtures for reference generator module."""

import pytest
from uuid import UUID
from shared.models.scene import ScenePlan, Character, Scene, Style


@pytest.fixture
def sample_style():
    """Sample style object for testing."""
    return Style(
        color_palette=["#00FFFF", "#FF00FF", "#0000FF"],
        visual_style="Neo-noir cyberpunk",
        mood="energetic",
        lighting="High-contrast neon with deep shadows",
        cinematography="Handheld tracking shots"
    )


@pytest.fixture
def sample_scene_plan(sample_style):
    """Sample ScenePlan for testing."""
    return ScenePlan(
        job_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        video_summary="A cyberpunk music video",
        characters=[
            Character(id="protagonist", description="Young woman, 25-30, futuristic jacket", role="main character"),
            Character(id="antagonist", description="Mysterious figure in shadows", role="background")
        ],
        scenes=[
            Scene(id="city_street", description="Rain-slicked cyberpunk street with neon signs", time_of_day="night"),
            Scene(id="interior", description="Futuristic apartment with holographic displays", time_of_day="night")
        ],
        style=sample_style,
        clip_scripts=[],
        transitions=[]
    )


@pytest.fixture
def single_scene_plan(sample_style):
    """ScenePlan with single scene and character (edge case)."""
    return ScenePlan(
        job_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        video_summary="Simple music video",
        characters=[
            Character(id="char1", description="Main character", role="main character")
        ],
        scenes=[
            Scene(id="scene1", description="Urban setting", time_of_day="day")
        ],
        style=sample_style,
        clip_scripts=[],
        transitions=[]
    )


@pytest.fixture
def empty_style():
    """Style with missing fields (edge case)."""
    return Style(
        color_palette=[],
        visual_style="",
        mood="",
        lighting="",
        cinematography=""
    )

