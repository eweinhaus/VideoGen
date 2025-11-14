"""
Unit tests for budget helper functions.
"""

import pytest
from decimal import Decimal
from api_gateway.services.budget_helpers import (
    get_budget_limit,
    get_cost_per_minute,
    get_cost_estimate
)


class TestGetBudgetLimit:
    """Tests for get_budget_limit function."""
    
    def test_production_mode_returns_2000(self):
        """Test production mode returns $2000 limit."""
        limit = get_budget_limit("production")
        assert limit == Decimal("2000.00")
    
    def test_staging_mode_returns_2000(self):
        """Test staging mode returns $2000 limit."""
        limit = get_budget_limit("staging")
        assert limit == Decimal("2000.00")
    
    def test_development_mode_returns_50(self):
        """Test development mode returns $50 limit."""
        limit = get_budget_limit("development")
        assert limit == Decimal("50.00")
    
    def test_invalid_environment_defaults_to_development(self):
        """Test invalid environment defaults to development mode."""
        limit = get_budget_limit("invalid")
        assert limit == Decimal("50.00")


class TestGetCostPerMinute:
    """Tests for get_cost_per_minute function."""
    
    def test_production_mode_returns_200(self):
        """Test production mode returns $200/minute."""
        cost = get_cost_per_minute("production")
        assert cost == 200.00
    
    def test_staging_mode_returns_200(self):
        """Test staging mode returns $200/minute."""
        cost = get_cost_per_minute("staging")
        assert cost == 200.00
    
    def test_development_mode_returns_2(self):
        """Test development mode returns $2/minute."""
        cost = get_cost_per_minute("development")
        assert cost == 2.00
    
    def test_invalid_environment_defaults_to_development(self):
        """Test invalid environment defaults to development mode."""
        cost = get_cost_per_minute("invalid")
        assert cost == 2.00


class TestGetCostEstimate:
    """Tests for get_cost_estimate function."""
    
    def test_production_mode_calculation(self):
        """Test production mode cost estimation."""
        cost = get_cost_estimate(3.0, "production")
        assert cost == 600.0  # 3 minutes * $200
    
    def test_staging_mode_calculation(self):
        """Test staging mode cost estimation."""
        cost = get_cost_estimate(3.0, "staging")
        assert cost == 600.0  # 3 minutes * $200
    
    def test_development_mode_calculation(self):
        """Test development mode cost estimation."""
        cost = get_cost_estimate(3.0, "development")
        assert cost == 4.5  # 3 minutes * $1.50
    
    def test_development_mode_minimum_cost(self):
        """Test development mode enforces minimum $2 cost."""
        cost = get_cost_estimate(1.0, "development")
        assert cost == 2.0  # Minimum $2, not 1.5
    
    def test_development_mode_short_audio(self):
        """Test development mode with very short audio (<1 minute)."""
        cost = get_cost_estimate(0.5, "development")
        assert cost == 2.0  # Minimum $2
    
    def test_development_mode_long_audio(self):
        """Test development mode with long audio (>10 minutes)."""
        cost = get_cost_estimate(15.0, "development")
        assert cost == 22.5  # 15 minutes * $1.50
    
    def test_invalid_environment_defaults_to_development(self):
        """Test invalid environment defaults to development mode."""
        cost = get_cost_estimate(3.0, "invalid")
        assert cost == 4.5  # Development formula


