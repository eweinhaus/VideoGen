"""
Configuration helpers for character analysis feature flags.

Flags are intentionally read directly from environment variables to avoid
tight coupling with shared configuration, minimizing risk to existing flows.
"""

import os
from typing import Set


def is_use_character_analysis_enabled() -> bool:
    """Return True if character analysis should be applied."""
    return os.getenv("USE_CHARACTER_ANALYSIS", "false").strip().lower() == "true"


def is_character_analysis_mock_enabled() -> bool:
    """Return True if mock mode is enabled."""
    return os.getenv("CHARACTER_ANALYSIS_MOCK", "false").strip().lower() == "true"


def get_character_analysis_test_users() -> Set[str]:
    """
    Return a set of user_id strings for whom analysis should be enabled regardless
    of the global flag (useful for internal/beta testing).
    """
    raw = os.getenv("CHARACTER_ANALYSIS_TEST_USERS", "").strip()
    if not raw:
        return set()
    return {u.strip() for u in raw.split(",") if u.strip()}


