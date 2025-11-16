"""
Unit tests for video_generator.cost_estimator module.
"""
import pytest
from decimal import Decimal
from uuid import UUID
from modules.video_generator.cost_estimator import estimate_clip_cost, estimate_total_cost
from shared.models.video import ClipPrompts, ClipPrompt


class TestEstimateClipCost:
    """Tests for estimate_clip_cost() function."""
    
    def test_production_cost_zero_duration(self):
        """Test production cost for zero duration returns base_cost."""
        cost = estimate_clip_cost(0.0, "production")
        assert cost == Decimal("0.10")
        assert isinstance(cost, Decimal)
    
    def test_production_cost_4_seconds(self):
        """Test production cost for 4 second clip."""
        cost = estimate_clip_cost(4.0, "production")
        expected = Decimal("0.10") + (Decimal("0.033") * Decimal("4.0"))
        assert cost == expected
        assert isinstance(cost, Decimal)
    
    def test_production_cost_6_seconds(self):
        """Test production cost for 6 second clip."""
        cost = estimate_clip_cost(6.0, "production")
        expected = Decimal("0.10") + (Decimal("0.033") * Decimal("6.0"))
        assert cost == expected
    
    def test_production_cost_8_seconds(self):
        """Test production cost for 8 second clip."""
        cost = estimate_clip_cost(8.0, "production")
        expected = Decimal("0.10") + (Decimal("0.033") * Decimal("8.0"))
        assert cost == expected
    
    def test_development_cost_zero_duration(self):
        """Test development cost for zero duration returns base_cost."""
        cost = estimate_clip_cost(0.0, "development")
        assert cost == Decimal("0.005")
        assert isinstance(cost, Decimal)
    
    def test_development_cost_4_seconds(self):
        """Test development cost for 4 second clip."""
        cost = estimate_clip_cost(4.0, "development")
        expected = Decimal("0.005") + (Decimal("0.002") * Decimal("4.0"))
        assert cost == expected
    
    def test_development_cost_6_seconds(self):
        """Test development cost for 6 second clip."""
        cost = estimate_clip_cost(6.0, "development")
        expected = Decimal("0.005") + (Decimal("0.002") * Decimal("6.0"))
        assert cost == expected
    
    def test_cost_increases_with_duration(self):
        """Test that cost increases with duration."""
        cost_4s = estimate_clip_cost(4.0, "production")
        cost_6s = estimate_clip_cost(6.0, "production")
        cost_8s = estimate_clip_cost(8.0, "production")
        
        assert cost_4s < cost_6s < cost_8s
    
    def test_invalid_environment_raises_error(self):
        """Test invalid environment raises ValueError."""
        with pytest.raises(ValueError, match="Invalid environment"):
            estimate_clip_cost(6.0, "invalid")
    
    def test_very_long_duration(self):
        """Test cost calculation for very long duration."""
        cost = estimate_clip_cost(100.0, "production")
        expected = Decimal("0.10") + (Decimal("0.033") * Decimal("100.0"))
        assert cost == expected
        assert cost > Decimal("3.0")  # Should be substantial
    
    def test_return_type_is_decimal(self):
        """Test that return type is always Decimal."""
        cost = estimate_clip_cost(6.0, "production")
        assert isinstance(cost, Decimal)


class TestEstimateTotalCost:
    """Tests for estimate_total_cost() function."""
    
    def test_empty_clip_prompts(self):
        """Test empty clip_prompts list returns zero."""
        clip_prompts = ClipPrompts(
            job_id=UUID("12345678-1234-1234-1234-123456789012"),
            clip_prompts=[],
            total_clips=0,
            generation_time=0.0
        )
        total = estimate_total_cost(clip_prompts, "production")
        assert total == Decimal("0.00")
        assert isinstance(total, Decimal)
    
    def test_single_clip_production(self):
        """Test total cost for single clip in production."""
        clip_prompts = ClipPrompts(
            job_id=UUID("12345678-1234-1234-1234-123456789012"),
            clip_prompts=[
                ClipPrompt(
                    clip_index=0,
                    prompt="A test scene",
                    negative_prompt="blurry",
                    duration=6.0
                )
            ],
            total_clips=1,
            generation_time=0.0
        )
        total = estimate_total_cost(clip_prompts, "production")
        expected = estimate_clip_cost(6.0, "production")
        assert total == expected
        assert isinstance(total, Decimal)
    
    def test_single_clip_development(self):
        """Test total cost for single clip in development."""
        clip_prompts = ClipPrompts(
            job_id=UUID("12345678-1234-1234-1234-123456789012"),
            clip_prompts=[
                ClipPrompt(
                    clip_index=0,
                    prompt="A test scene",
                    negative_prompt="blurry",
                    duration=4.0
                )
            ],
            total_clips=1,
            generation_time=0.0
        )
        total = estimate_total_cost(clip_prompts, "development")
        expected = estimate_clip_cost(4.0, "development")
        assert total == expected
    
    def test_multiple_clips_production(self):
        """Test total cost for multiple clips in production."""
        clip_prompts = ClipPrompts(
            job_id=UUID("12345678-1234-1234-1234-123456789012"),
            clip_prompts=[
                ClipPrompt(
                    clip_index=0,
                    prompt="Scene 1",
                    negative_prompt="blurry",
                    duration=4.0
                ),
                ClipPrompt(
                    clip_index=1,
                    prompt="Scene 2",
                    negative_prompt="blurry",
                    duration=6.0
                ),
                ClipPrompt(
                    clip_index=2,
                    prompt="Scene 3",
                    negative_prompt="blurry",
                    duration=8.0
                ),
            ],
            total_clips=3,
            generation_time=0.0
        )
        total = estimate_total_cost(clip_prompts, "production")
        
        # Calculate expected sum
        expected = (
            estimate_clip_cost(4.0, "production") +
            estimate_clip_cost(6.0, "production") +
            estimate_clip_cost(8.0, "production")
        )
        assert total == expected
        assert isinstance(total, Decimal)
    
    def test_multiple_clips_development(self):
        """Test total cost for multiple clips in development."""
        clip_prompts = ClipPrompts(
            job_id=UUID("12345678-1234-1234-1234-123456789012"),
            clip_prompts=[
                ClipPrompt(
                    clip_index=0,
                    prompt="Scene 1",
                    negative_prompt="blurry",
                    duration=4.0
                ),
                ClipPrompt(
                    clip_index=1,
                    prompt="Scene 2",
                    negative_prompt="blurry",
                    duration=6.0
                ),
            ],
            total_clips=2,
            generation_time=0.0
        )
        total = estimate_total_cost(clip_prompts, "development")
        
        expected = (
            estimate_clip_cost(4.0, "development") +
            estimate_clip_cost(6.0, "development")
        )
        assert total == expected
    
    def test_total_equals_sum_of_individual_costs(self):
        """Test that total equals sum of individual clip costs."""
        clip_prompts = ClipPrompts(
            job_id=UUID("12345678-1234-1234-1234-123456789012"),
            clip_prompts=[
                ClipPrompt(
                    clip_index=0,
                    prompt="Scene 1",
                    negative_prompt="blurry",
                    duration=5.0
                ),
                ClipPrompt(
                    clip_index=1,
                    prompt="Scene 2",
                    negative_prompt="blurry",
                    duration=7.0
                ),
            ],
            total_clips=2,
            generation_time=0.0
        )
        
        total = estimate_total_cost(clip_prompts, "production")
        individual_sum = (
            estimate_clip_cost(5.0, "production") +
            estimate_clip_cost(7.0, "production")
        )
        assert total == individual_sum
    
    def test_return_type_is_decimal(self):
        """Test that return type is always Decimal."""
        clip_prompts = ClipPrompts(
            job_id=UUID("12345678-1234-1234-1234-123456789012"),
            clip_prompts=[
                ClipPrompt(
                    clip_index=0,
                    prompt="Scene 1",
                    negative_prompt="blurry",
                    duration=6.0
                )
            ],
            total_clips=1,
            generation_time=0.0
        )
        total = estimate_total_cost(clip_prompts, "production")
        assert isinstance(total, Decimal)

