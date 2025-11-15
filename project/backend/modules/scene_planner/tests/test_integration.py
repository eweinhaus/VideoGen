"""
End-to-end integration tests.

Tests the full pipeline with mocked external dependencies.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from shared.models.audio import AudioAnalysis, Mood, SongStructure, ClipBoundary
from shared.models.scene import ScenePlan

from modules.scene_planner import planner
from modules.scene_planner import llm_client
from modules.scene_planner.main import process_scene_planning


@pytest.fixture
def mock_llm_response():
    """Mock LLM response matching PRD format."""
    return {
        "job_id": str(uuid4()),
        "video_summary": "A cyberpunk cityscape at night with neon lights",
        "characters": [
            {
                "id": "protagonist",
                "description": "Young woman, 25-30, futuristic jacket, signature red jacket",
                "role": "main character"
            }
        ],
        "scenes": [
            {
                "id": "city_street",
                "description": "Rain-slicked cyberpunk street with neon signs, distant city lights",
                "time_of_day": "night"
            }
        ],
        "style": {
            "color_palette": ["#00FFFF", "#FF00FF", "#0000FF"],
            "visual_style": "Neo-noir cyberpunk with rain and neon",
            "mood": "Melancholic yet hopeful",
            "lighting": "High-contrast neon with deep shadows",
            "cinematography": "Handheld, slight shake, tracking shots"
        },
        "clip_scripts": [
            {
                "clip_index": i,
                "start": float(i * 6.0),
                "end": float((i + 1) * 6.0),
                "visual_description": f"Scene {i} description",
                "motion": "Tracking shot",
                "camera_angle": "Medium shot",
                "characters": ["protagonist"],
                "scenes": ["city_street"],
                "lyrics_context": None,
                "beat_intensity": "medium"
            }
            for i in range(5)
        ],
        "transitions": [
            {
                "from_clip": i,
                "to_clip": i + 1,
                "type": "crossfade",
                "duration": 0.5,
                "rationale": "Smooth transition"
            }
            for i in range(4)
        ]
    }


@pytest.mark.asyncio
@patch('modules.scene_planner.director_knowledge.get_director_knowledge')
@patch('modules.scene_planner.llm_client.cost_tracker.track_cost', new_callable=AsyncMock)
@patch.object(llm_client, 'generate_scene_plan', new_callable=AsyncMock)
async def test_full_pipeline_success(
    mock_generate_scene_plan,
    mock_track_cost,
    mock_get_director_knowledge,
    mock_llm_response,
    job_id
):
    """Test full pipeline with mocked LLM."""
    # Setup
    mock_get_director_knowledge.return_value = "Test director knowledge"
    mock_track_cost.return_value = None
    mock_generate_scene_plan.return_value = mock_llm_response
    
    audio_analysis = AudioAnalysis(
        job_id=job_id,
        bpm=120.0,
        duration=30.0,
        beat_timestamps=[i * 0.5 for i in range(60)],
        song_structure=[
            SongStructure(type="verse", start=0.0, end=30.0, energy="medium")
        ],
        lyrics=[],
        mood=Mood(primary="energetic", energy_level="high", confidence=0.8),
        clip_boundaries=[
            ClipBoundary(start=i * 6.0, end=(i + 1) * 6.0, duration=6.0)
            for i in range(5)
        ],
        metadata={}
    )
    
    user_prompt = "cyberpunk city at night with neon lights, rain-slicked streets"
    
    # Also patch it in planner module where it's imported
    with patch.object(planner, 'generate_scene_plan', new_callable=AsyncMock) as mock_planner_generate:
        mock_planner_generate.return_value = mock_llm_response
        # Execute
        scene_plan = await process_scene_planning(
            job_id=job_id,
            user_prompt=user_prompt,
            audio_data=audio_analysis
        )
        
        # Verify
        assert isinstance(scene_plan, ScenePlan)
        assert scene_plan.job_id == job_id
        assert len(scene_plan.clip_scripts) == 5
        assert len(scene_plan.transitions) == 4
        assert len(scene_plan.characters) == 1
        assert len(scene_plan.scenes) == 1
        assert len(scene_plan.style.color_palette) >= 3
        
        # Verify clip alignment
        for i, (clip, boundary) in enumerate(zip(scene_plan.clip_scripts, audio_analysis.clip_boundaries)):
            assert abs(clip.start - boundary.start) <= 0.5
            assert abs(clip.end - boundary.end) <= 0.5
        
        # Verify transitions
        for i, transition in enumerate(scene_plan.transitions):
            assert transition.from_clip == i
            assert transition.to_clip == i + 1


@pytest.mark.asyncio
@patch('modules.scene_planner.director_knowledge.get_director_knowledge')
@patch('modules.scene_planner.llm_client.cost_tracker.track_cost', new_callable=AsyncMock)
@patch.object(llm_client, 'generate_scene_plan', new_callable=AsyncMock)
async def test_director_knowledge_applied(
    mock_generate_scene_plan,
    mock_track_cost,
    mock_get_director_knowledge,
    mock_llm_response,
    job_id
):
    """Test that director knowledge is applied in prompts."""
    mock_get_director_knowledge.return_value = "Test director knowledge"
    mock_generate_scene_plan.return_value = mock_llm_response
    mock_track_cost.return_value = None
    
    audio_analysis = AudioAnalysis(
        job_id=job_id,
        bpm=140.0,  # High BPM
        duration=30.0,
        beat_timestamps=[i * 0.43 for i in range(70)],
        song_structure=[
            SongStructure(type="chorus", start=0.0, end=30.0, energy="high")
        ],
        lyrics=[],
        mood=Mood(primary="energetic", energy_level="high", confidence=0.9),
        clip_boundaries=[
            ClipBoundary(start=i * 6.0, end=(i + 1) * 6.0, duration=6.0)
            for i in range(5)
        ],
        metadata={}
    )
    
    user_prompt = "high energy dance scene with vibrant colors and dynamic movements" * 2  # Make it 50+ chars
    
    # Also patch it in planner module where it's imported
    with patch.object(planner, 'generate_scene_plan', new_callable=AsyncMock) as mock_planner_generate:
        mock_planner_generate.return_value = mock_llm_response
        await process_scene_planning(
            job_id=job_id,
            user_prompt=user_prompt,
            audio_data=audio_analysis
        )
        
        # Verify LLM was called with director knowledge
        assert mock_planner_generate.called
        call_args = mock_planner_generate.call_args
        assert "director_knowledge" in call_args.kwargs or len(call_args.args) >= 3

