"""
Unit tests for video_generator.config module.
"""
import pytest
from unittest.mock import patch
from decimal import Decimal
from modules.video_generator.config import (
    get_generation_settings,
    get_model_version,
    PRODUCTION_SETTINGS,
    DEVELOPMENT_SETTINGS,
    COST_PER_CLIP,
    SVD_MODEL,
    COGVIDEOX_MODEL,
)


class TestGetGenerationSettings:
    """Tests for get_generation_settings() function."""
    
    def test_default_uses_settings_environment(self):
        """Test that default behavior uses settings.environment."""
        from shared.config import settings
        result = get_generation_settings()
        
        if settings.environment in ["production", "staging"]:
            assert result == PRODUCTION_SETTINGS
        else:
            assert result == DEVELOPMENT_SETTINGS
    
    def test_production_environment(self):
        """Test production environment returns production settings."""
        result = get_generation_settings("production")
        assert result == PRODUCTION_SETTINGS
        assert result is not PRODUCTION_SETTINGS  # Should be a copy
    
    def test_staging_environment(self):
        """Test staging environment returns production settings."""
        result = get_generation_settings("staging")
        assert result == PRODUCTION_SETTINGS
        assert result is not PRODUCTION_SETTINGS  # Should be a copy
    
    def test_development_environment(self):
        """Test development environment returns development settings."""
        result = get_generation_settings("development")
        assert result == DEVELOPMENT_SETTINGS
        assert result is not DEVELOPMENT_SETTINGS  # Should be a copy
    
    def test_all_settings_keys_present(self):
        """Test that all required settings keys are present."""
        prod_settings = get_generation_settings("production")
        dev_settings = get_generation_settings("development")
        
        required_keys = {"resolution", "fps", "motion_bucket_id", "steps", "max_duration"}
        assert set(prod_settings.keys()) == required_keys
        assert set(dev_settings.keys()) == required_keys
    
    def test_production_settings_values(self):
        """Test production settings values match PRD."""
        settings = get_generation_settings("production")
        assert settings["resolution"] == "1024x576"
        assert settings["fps"] == 30
        assert settings["motion_bucket_id"] == 127
        assert settings["steps"] == 25
        assert settings["max_duration"] == 8.0
    
    def test_development_settings_values(self):
        """Test development settings values match PRD."""
        settings = get_generation_settings("development")
        assert settings["resolution"] == "768x432"
        assert settings["fps"] == 24
        assert settings["motion_bucket_id"] == 100
        assert settings["steps"] == 20
        assert settings["max_duration"] == 4.0
    
    def test_settings_are_independent_copies(self):
        """Test that returned settings are independent copies."""
        settings1 = get_generation_settings("production")
        settings2 = get_generation_settings("production")
        
        # Modify one copy
        settings1["fps"] = 60
        
        # Other copy should be unchanged
        assert settings2["fps"] == 30
        assert PRODUCTION_SETTINGS["fps"] == 30


class TestGetModelVersion:
    """Tests for get_model_version() function."""
    
    def test_svd_model(self):
        """Test SVD model version retrieval."""
        result = get_model_version("svd")
        assert result == SVD_MODEL
        assert "stability-ai/stable-video-diffusion" in result
    
    def test_cogvideox_model(self):
        """Test CogVideoX model version retrieval."""
        result = get_model_version("cogvideox")
        assert result == COGVIDEOX_MODEL
        assert "THUDM/cogvideox" in result
    
    def test_default_model(self):
        """Test default model is SVD."""
        result = get_model_version()
        assert result == SVD_MODEL
    
    def test_invalid_model_raises_error(self):
        """Test invalid model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model"):
            get_model_version("invalid_model")


class TestEnvironmentVariableOverrides:
    """Tests for environment variable overrides."""
    
    @patch.dict("os.environ", {"SVD_MODEL_VERSION": "custom_version"})
    def test_svd_model_version_override(self):
        """Test SVD_MODEL_VERSION environment variable override."""
        # Need to reload module to pick up new env var
        import importlib
        import modules.video_generator.config as config_module
        importlib.reload(config_module)
        
        result = config_module.get_model_version("svd")
        assert "custom_version" in result
    
    @patch.dict("os.environ", {"COGVIDEOX_MODEL_VERSION": "custom_cogvideox"})
    def test_cogvideox_model_version_override(self):
        """Test COGVIDEOX_MODEL_VERSION environment variable override."""
        # Need to reload module to pick up new env var
        import importlib
        import modules.video_generator.config as config_module
        importlib.reload(config_module)
        
        result = config_module.get_model_version("cogvideox")
        assert "custom_cogvideox" in result


class TestCostLookupTable:
    """Tests for COST_PER_CLIP lookup table."""
    
    def test_cost_structure(self):
        """Test COST_PER_CLIP has correct structure."""
        assert "production" in COST_PER_CLIP
        assert "development" in COST_PER_CLIP
        
        for env in ["production", "development"]:
            assert "base_cost" in COST_PER_CLIP[env]
            assert "per_second" in COST_PER_CLIP[env]
    
    def test_cost_values_are_decimal(self):
        """Test all cost values are Decimal type."""
        for env in ["production", "development"]:
            assert isinstance(COST_PER_CLIP[env]["base_cost"], Decimal)
            assert isinstance(COST_PER_CLIP[env]["per_second"], Decimal)
    
    def test_production_cost_values(self):
        """Test production cost values."""
        assert COST_PER_CLIP["production"]["base_cost"] == Decimal("0.10")
        assert COST_PER_CLIP["production"]["per_second"] == Decimal("0.033")
    
    def test_development_cost_values(self):
        """Test development cost values."""
        assert COST_PER_CLIP["development"]["base_cost"] == Decimal("0.005")
        assert COST_PER_CLIP["development"]["per_second"] == Decimal("0.002")

