"""
Clip regenerator module.

This module provides data loading and regeneration functionality for the clip chatbot feature.
"""

from modules.clip_regenerator.process import regenerate_clip, RegenerationResult
from modules.clip_regenerator.template_matcher import match_template, apply_template, TemplateMatch
from modules.clip_regenerator.llm_modifier import modify_prompt_with_llm
from modules.clip_regenerator.context_builder import build_llm_context
from modules.clip_regenerator.data_loader import (
    load_clips_from_job_stages,
    load_clips_with_latest_versions,
    load_clip_prompts_from_job_stages,
    load_scene_plan_from_job_stages,
    load_reference_images_from_job_stages
)
from modules.clip_regenerator.style_analyzer import extract_style_keywords, extract_style_with_llm, StyleKeywords
from modules.clip_regenerator.style_applier import apply_style_to_prompt, StyleTransferOptions
from modules.clip_regenerator.style_transfer import transfer_style
from modules.clip_regenerator.suggestion_generator import generate_suggestions, Suggestion
from modules.clip_regenerator.instruction_parser import parse_multi_clip_instruction, ClipInstruction

__all__ = [
    "regenerate_clip",
    "RegenerationResult",
    "match_template",
    "apply_template",
    "TemplateMatch",
    "modify_prompt_with_llm",
    "build_llm_context",
    "load_clips_from_job_stages",
    "load_clips_with_latest_versions",
    "load_clip_prompts_from_job_stages",
    "load_scene_plan_from_job_stages",
    "load_reference_images_from_job_stages",
    "extract_style_keywords",
    "extract_style_with_llm",
    "StyleKeywords",
    "apply_style_to_prompt",
    "StyleTransferOptions",
    "transfer_style",
    "generate_suggestions",
    "Suggestion",
    "parse_multi_clip_instruction",
    "ClipInstruction",
]

