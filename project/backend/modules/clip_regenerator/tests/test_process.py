"""
Unit tests for regeneration process module.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from decimal import Decimal

from modules.clip_regenerator.process import regenerate_clip, RegenerationResult
from modules.clip_regenerator.template_matcher import TemplateMatch
from shared.models.video import Clips, Clip, ClipPrompts, ClipPrompt
from shared.models.scene import ScenePlan
from shared.errors import ValidationError, GenerationError


@pytest.fixture
def sample_job_id():
    """Sample job ID for testing."""
    return uuid4()


@pytest.fixture
def sample_clips():
    """Sample clips for testing."""
    return Clips(
        job_id=uuid4(),
        total_clips=3,
        successful_clips=3,
        failed_clips=0,
        clips=[
            Clip(
                clip_index=0,
                video_url="https://example.com/clip0.mp4",
                target_duration=5.0,
                actual_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                generation_time=30.0
            ),
            Clip(
                clip_index=1,
                video_url="https://example.com/clip1.mp4",
                target_duration=5.0,
                actual_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                generation_time=30.0
            ),
            Clip(
                clip_index=2,
                video_url="https://example.com/clip2.mp4",
                target_duration=5.0,
                actual_duration=5.0,
                duration_diff=0.0,
                status="success",
                cost=Decimal("0.10"),
                generation_time=30.0
            )
        ],
        total_cost=Decimal("0.30"),
        total_generation_time=90.0
    )


@pytest.fixture
def sample_clip_prompts():
    """Sample clip prompts for testing."""
    return ClipPrompts(
        job_id=uuid4(),
        clip_prompts=[
            ClipPrompt(
                clip_index=0,
                prompt="A cyberpunk street scene",
                negative_prompt="blurry, low quality",
                duration=5.0
            ),
            ClipPrompt(
                clip_index=1,
                prompt="A futuristic cityscape",
                negative_prompt="blurry, low quality",
                duration=5.0
            ),
            ClipPrompt(
                clip_index=2,
                prompt="A neon-lit alleyway",
                negative_prompt="blurry, low quality",
                duration=5.0
            )
        ],
        total_clips=3,
        generation_time=90.0
    )


@pytest.fixture
def sample_scene_plan():
    """Sample scene plan for testing."""
    from shared.models.scene import Style, Character, Scene
    return ScenePlan(
        style=Style(
            visual_style="cyberpunk",
            mood="dark",
            color_palette=["#000000", "#00ff00"],
            lighting="neon",
            cinematography="dynamic"
        ),
        characters=[
            Character(id="protagonist", name="Protagonist", description="Main character", role="hero")
        ],
        scenes=[
            Scene(id="scene1", description="Street scene", location="Cyberpunk street", time_of_day="night")
        ],
        clip_scripts=[],
        transitions=[]
    )


class TestRegenerateClip:
    """Test clip regeneration process."""
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.process.load_clips_from_job_stages')
    @patch('modules.clip_regenerator.process.load_clip_prompts_from_job_stages')
    @patch('modules.clip_regenerator.process.load_scene_plan_from_job_stages')
    @patch('modules.clip_regenerator.process.match_template')
    @patch('modules.clip_regenerator.process.apply_template')
    @patch('modules.clip_regenerator.process.generate_video_clip')
    @patch('modules.clip_regenerator.process._get_job_config')
    @patch('modules.clip_regenerator.process.get_generation_settings')
    @patch('modules.clip_regenerator.process.estimate_clip_cost')
    async def test_regenerate_with_template(
        self,
        mock_estimate_cost,
        mock_get_settings,
        mock_get_config,
        mock_generate_clip,
        mock_apply_template,
        mock_match_template,
        mock_load_scene_plan,
        mock_load_prompts,
        mock_load_clips,
        sample_job_id,
        sample_clips,
        sample_clip_prompts
    ):
        """Test regeneration with template match."""
        # Setup mocks
        mock_load_clips.return_value = sample_clips
        mock_load_prompts.return_value = sample_clip_prompts
        mock_load_scene_plan.return_value = None
        
        template_match = TemplateMatch(
            template_id="nighttime",
            transformation="nighttime scene, dark sky",
            cost_savings=0.01
        )
        mock_match_template.return_value = template_match
        mock_apply_template.return_value = "A cyberpunk street scene, nighttime scene, dark sky"
        
        mock_get_config.return_value = {"video_model": "kling_v21", "aspect_ratio": "16:9"}
        mock_get_settings.return_value = {}
        mock_estimate_cost.return_value = Decimal("0.10")
        
        new_clip = Clip(
            clip_index=0,
            video_url="https://example.com/new_clip.mp4",
            target_duration=5.0,
            actual_duration=5.0,
            duration_diff=0.0,
            status="success",
            cost=Decimal("0.10"),
            generation_time=30.0
        )
        mock_generate_clip.return_value = new_clip
        
        # Call function
        result = await regenerate_clip(
            job_id=sample_job_id,
            clip_index=0,
            user_instruction="make it nighttime",
            conversation_history=[],
            event_publisher=None
        )
        
        # Verify
        assert isinstance(result, RegenerationResult)
        assert result.clip == new_clip
        assert result.template_used == "nighttime"
        assert result.modified_prompt == "A cyberpunk street scene, nighttime scene, dark sky"
        mock_match_template.assert_called_once_with("make it nighttime")
        mock_apply_template.assert_called_once()
        mock_generate_clip.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.process.load_clips_from_job_stages')
    @patch('modules.clip_regenerator.process.load_clip_prompts_from_job_stages')
    @patch('modules.clip_regenerator.process.load_scene_plan_from_job_stages')
    @patch('modules.clip_regenerator.process.match_template')
    @patch('modules.clip_regenerator.process.build_llm_context')
    @patch('modules.clip_regenerator.process.modify_prompt_with_llm')
    @patch('modules.clip_regenerator.process.generate_video_clip')
    @patch('modules.clip_regenerator.process._get_job_config')
    @patch('modules.clip_regenerator.process.get_generation_settings')
    @patch('modules.clip_regenerator.process.estimate_llm_cost')
    @patch('modules.clip_regenerator.process.estimate_clip_cost')
    async def test_regenerate_with_llm(
        self,
        mock_estimate_clip_cost,
        mock_estimate_llm_cost,
        mock_get_settings,
        mock_get_config,
        mock_generate_clip,
        mock_modify_llm,
        mock_build_context,
        mock_match_template,
        mock_load_scene_plan,
        mock_load_prompts,
        mock_load_clips,
        sample_job_id,
        sample_clips,
        sample_clip_prompts,
        sample_scene_plan
    ):
        """Test regeneration with LLM modification."""
        # Setup mocks
        mock_load_clips.return_value = sample_clips
        mock_load_prompts.return_value = sample_clip_prompts
        mock_load_scene_plan.return_value = sample_scene_plan
        
        mock_match_template.return_value = None  # No template match
        mock_build_context.return_value = {
            "style_info": "cyberpunk",
            "character_names": [],
            "scene_locations": [],
            "mood": "dark"
        }
        mock_modify_llm.return_value = "A modified cyberpunk street scene with custom changes"
        
        mock_get_config.return_value = {"video_model": "kling_v21", "aspect_ratio": "16:9"}
        mock_get_settings.return_value = {}
        mock_estimate_llm_cost.return_value = Decimal("0.01")
        mock_estimate_clip_cost.return_value = Decimal("0.10")
        
        new_clip = Clip(
            clip_index=0,
            video_url="https://example.com/new_clip.mp4",
            target_duration=5.0,
            actual_duration=5.0,
            duration_diff=0.0,
            status="success",
            cost=Decimal("0.10"),
            generation_time=30.0
        )
        mock_generate_clip.return_value = new_clip
        
        # Call function
        result = await regenerate_clip(
            job_id=sample_job_id,
            clip_index=0,
            user_instruction="make it more colorful",
            conversation_history=[],
            event_publisher=None
        )
        
        # Verify
        assert isinstance(result, RegenerationResult)
        assert result.clip == new_clip
        assert result.template_used is None
        assert "modified" in result.modified_prompt.lower()
        mock_match_template.assert_called_once()
        mock_build_context.assert_called_once()
        mock_modify_llm.assert_called_once()
        mock_generate_clip.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.process.load_clips_from_job_stages')
    @patch('modules.clip_regenerator.process.load_clip_prompts_from_job_stages')
    async def test_regenerate_invalid_clip_index(
        self,
        mock_load_prompts,
        mock_load_clips,
        sample_job_id,
        sample_clips,
        sample_clip_prompts
    ):
        """Test regeneration with invalid clip index."""
        mock_load_clips.return_value = sample_clips
        mock_load_prompts.return_value = sample_clip_prompts
        
        # Try invalid clip index
        with pytest.raises(ValidationError):
            await regenerate_clip(
                job_id=sample_job_id,
                clip_index=10,  # Invalid index
                user_instruction="test",
                conversation_history=[]
            )
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.process.load_clips_from_job_stages')
    async def test_regenerate_no_clips(
        self,
        mock_load_clips,
        sample_job_id
    ):
        """Test regeneration when clips not found."""
        mock_load_clips.return_value = None
        
        with pytest.raises(ValidationError):
            await regenerate_clip(
                job_id=sample_job_id,
                clip_index=0,
                user_instruction="test",
                conversation_history=[]
            )
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.process.load_clips_from_job_stages')
    @patch('modules.clip_regenerator.process.load_clip_prompts_from_job_stages')
    @patch('modules.clip_regenerator.process.load_scene_plan_from_job_stages')
    @patch('modules.clip_regenerator.process.match_template')
    @patch('modules.clip_regenerator.process.apply_template')
    @patch('modules.clip_regenerator.process.generate_video_clip')
    @patch('modules.clip_regenerator.process._get_job_config')
    @patch('modules.clip_regenerator.process.get_generation_settings')
    @patch('modules.clip_regenerator.process.estimate_clip_cost')
    async def test_regenerate_video_generation_fails(
        self,
        mock_estimate_cost,
        mock_get_settings,
        mock_get_config,
        mock_generate_clip,
        mock_apply_template,
        mock_match_template,
        mock_load_scene_plan,
        mock_load_prompts,
        mock_load_clips,
        sample_job_id,
        sample_clips,
        sample_clip_prompts
    ):
        """Test regeneration when video generation fails."""
        mock_load_clips.return_value = sample_clips
        mock_load_prompts.return_value = sample_clip_prompts
        mock_load_scene_plan.return_value = None
        
        template_match = TemplateMatch(
            template_id="nighttime",
            transformation="nighttime scene",
            cost_savings=0.01
        )
        mock_match_template.return_value = template_match
        mock_apply_template.return_value = "Modified prompt"
        
        mock_get_config.return_value = {"video_model": "kling_v21", "aspect_ratio": "16:9"}
        mock_get_settings.return_value = {}
        mock_estimate_cost.return_value = Decimal("0.10")
        
        # Mock video generation failure
        mock_generate_clip.side_effect = Exception("Video generation failed")
        
        # Call function
        with pytest.raises(GenerationError):
            await regenerate_clip(
                job_id=sample_job_id,
                clip_index=0,
                user_instruction="make it nighttime",
                conversation_history=[]
            )

