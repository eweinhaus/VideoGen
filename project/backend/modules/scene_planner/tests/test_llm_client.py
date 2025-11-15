"""
Unit tests for LLM client.

Tests LLM API integration with mocked responses.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from decimal import Decimal

from shared.models.audio import AudioAnalysis, Mood, SongStructure, Lyric, ClipBoundary
from shared.errors import GenerationError, RetryableError

from modules.scene_planner.llm_client import (
    generate_scene_plan,
    _calculate_llm_cost,
    _build_system_prompt,
    _build_user_prompt,
    _get_mood_instructions
)


@pytest.fixture
def sample_audio_analysis(job_id):
    """Create sample AudioAnalysis."""
    return AudioAnalysis(
        job_id=job_id,
        bpm=120.0,
        duration=180.0,
        beat_timestamps=[i * 0.5 for i in range(360)],
        song_structure=[
            SongStructure(type="intro", start=0.0, end=15.0, energy="low"),
            SongStructure(type="chorus", start=15.0, end=45.0, energy="high"),
        ],
        lyrics=[
            Lyric(text="Test lyric", timestamp=15.0)
        ],
        mood=Mood(primary="energetic", energy_level="high", confidence=0.85),
        clip_boundaries=[
            ClipBoundary(start=0.0, end=6.0, duration=6.0),
            ClipBoundary(start=6.0, end=12.0, duration=6.0),
        ],
        metadata={}
    )


class TestCalculateLLMCost:
    """Test cost calculation."""
    
    def test_calculate_gpt4o_cost(self):
        """Test GPT-4o cost calculation."""
        cost = _calculate_llm_cost("gpt-4o", 1000, 500)
        # $0.005 per 1K input + $0.015 per 1K output
        expected = Decimal("0.005") + Decimal("0.0075")
        assert cost == expected
    
    def test_calculate_claude_cost(self):
        """Test Claude 3.5 Sonnet cost calculation."""
        cost = _calculate_llm_cost("claude-3-5-sonnet", 1000, 500)
        # $0.003 per 1K input + $0.015 per 1K output
        expected = Decimal("0.003") + Decimal("0.0075")
        assert cost == expected


class TestBuildPrompts:
    """Test prompt building."""
    
    def test_build_system_prompt(self, sample_audio_analysis):
        """Test system prompt building."""
        director_knowledge = "Test director knowledge"
        prompt = _build_system_prompt(director_knowledge, sample_audio_analysis)
        
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "director knowledge" in prompt.lower() or "Director Knowledge" in prompt
        assert str(sample_audio_analysis.bpm) in prompt
        assert sample_audio_analysis.mood.primary in prompt
    
    def test_build_user_prompt(self, sample_audio_analysis):
        """Test user prompt building."""
        user_prompt = "cyberpunk city at night"
        prompt = _build_user_prompt(user_prompt, sample_audio_analysis)
        
        assert isinstance(prompt, str)
        assert user_prompt in prompt
        assert str(len(sample_audio_analysis.clip_boundaries)) in prompt
    
    def test_get_mood_instructions_energetic(self):
        """Test mood instructions for energetic mood."""
        instructions = _get_mood_instructions("energetic", "high", 140.0)
        
        assert isinstance(instructions, str)
        assert "energetic" in instructions.lower() or "ENERGETIC" in instructions
        assert "vibrant" in instructions.lower() or "saturated" in instructions.lower()
    
    def test_get_mood_instructions_calm(self):
        """Test mood instructions for calm mood."""
        instructions = _get_mood_instructions("calm", "low", 75.0)
        
        assert isinstance(instructions, str)
        assert "calm" in instructions.lower() or "CALM" in instructions
        assert "muted" in instructions.lower() or "desaturated" in instructions.lower()


class TestGenerateScenePlan:
    """Test scene plan generation."""
    
    @pytest.mark.asyncio
    @patch('modules.scene_planner.llm_client.get_openai_client')
    @patch('modules.scene_planner.llm_client.cost_tracker')
    async def test_generate_scene_plan_success(
        self,
        mock_cost_tracker,
        mock_get_client,
        job_id,
        sample_audio_analysis
    ):
        """Test successful scene plan generation."""
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"job_id": "' + str(job_id) + '", "video_summary": "Test", "characters": [], "scenes": [], "style": {"color_palette": ["#000000"], "visual_style": "test", "mood": "test", "lighting": "test", "cinematography": "test"}, "clip_scripts": [], "transitions": []}'
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 500
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client
        
        # Mock cost tracker
        mock_cost_tracker.track_cost = AsyncMock()
        
        # Mock director knowledge
        with patch('modules.scene_planner.director_knowledge.get_director_knowledge') as mock_knowledge:
            mock_knowledge.return_value = "Test knowledge"
            
            result = await generate_scene_plan(
                job_id=job_id,
                user_prompt="cyberpunk city at night",
                audio_data=sample_audio_analysis,
                director_knowledge="Test knowledge"
            )
            
            assert isinstance(result, dict)
            assert "job_id" in result
            assert "clip_scripts" in result
            
            # Verify cost tracking was called
            mock_cost_tracker.track_cost.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.scene_planner.llm_client.get_openai_client')
    async def test_generate_scene_plan_rate_limit(
        self,
        mock_get_client,
        job_id,
        sample_audio_analysis
    ):
        """Test rate limit error handling."""
        from openai import RateLimitError
        from unittest.mock import MagicMock
        
        # Mock rate limit error (need proper response object)
        mock_response = MagicMock()
        mock_response.request = MagicMock()
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError("Rate limit exceeded", response=mock_response, body=None)
        )
        mock_get_client.return_value = mock_client
        
        # Mock cost tracker to avoid database calls
        with patch('modules.scene_planner.llm_client.cost_tracker.track_cost', new_callable=AsyncMock):
            # Should raise RetryableError (will be retried)
            with pytest.raises(RetryableError):
                await generate_scene_plan(
                    job_id=job_id,
                    user_prompt="test",
                    audio_data=sample_audio_analysis,
                    director_knowledge="Test knowledge"
                )
    
    @pytest.mark.asyncio
    @patch('modules.scene_planner.llm_client.get_openai_client')
    async def test_generate_scene_plan_invalid_json(
        self,
        mock_get_client,
        job_id,
        sample_audio_analysis
    ):
        """Test invalid JSON response handling."""
        # Mock invalid JSON response
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client
        
        # Mock cost tracker to avoid database calls
        with patch('modules.scene_planner.llm_client.cost_tracker.track_cost', new_callable=AsyncMock):
            # The retry decorator will retry 3 times on RetryableError
            # After retries are exhausted, it raises the last RetryableError
            # But the outer exception handler catches it and raises GenerationError
            # So we expect GenerationError after retries fail
            with pytest.raises(GenerationError):
                await generate_scene_plan(
                    job_id=job_id,
                    user_prompt="test",
                    audio_data=sample_audio_analysis,
                    director_knowledge="Test knowledge"
                )

