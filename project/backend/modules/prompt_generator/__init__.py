"""
Prompt Generator module public API.

Exposes the high-level process function for orchestrator usage.
"""

from shared.logging import get_logger

from .process import process as process_prompts

__all__ = ["process_prompts"]

# Configure module-level logger early so submodules can import it
logger = get_logger("prompt_generator")

