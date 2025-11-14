"""
Budget helper functions.

Environment-aware budget limits and cost estimation.
"""

from decimal import Decimal
from typing import Literal


def get_budget_limit(environment: str) -> Decimal:
    """
    Get budget limit based on environment.
    
    Args:
        environment: Environment string ("production", "staging", or "development")
        
    Returns:
        Budget limit as Decimal
        
    Examples:
        >>> get_budget_limit("production")
        Decimal('2000.00')
        >>> get_budget_limit("development")
        Decimal('50.00')
    """
    if environment in ["production", "staging"]:
        return Decimal("2000.00")
    # Default to development mode
    return Decimal("50.00")


def get_cost_per_minute(environment: str) -> float:
    """
    Get cost per minute for estimation.
    
    Args:
        environment: Environment string ("production", "staging", or "development")
        
    Returns:
        Cost per minute as float
        
    Examples:
        >>> get_cost_per_minute("production")
        200.0
        >>> get_cost_per_minute("development")
        2.0
    """
    if environment in ["production", "staging"]:
        return 200.00
    # Default to development mode
    return 2.00


def get_cost_estimate(duration_minutes: float, environment: str) -> float:
    """
    Get cost estimate for audio duration.
    
    Production: duration_minutes * 200.00
    Development: max(2.00, duration_minutes * 1.50) - minimum $2
    
    Args:
        duration_minutes: Audio duration in minutes
        environment: Environment string ("production", "staging", or "development")
        
    Returns:
        Estimated cost as float
        
    Examples:
        >>> get_cost_estimate(3.0, "production")
        600.0
        >>> get_cost_estimate(1.0, "development")
        2.0
        >>> get_cost_estimate(3.0, "development")
        4.5
    """
    if environment in ["production", "staging"]:
        return duration_minutes * 200.00
    # Development: minimum $2, ~$1.50/minute
    return max(2.00, duration_minutes * 1.50)


