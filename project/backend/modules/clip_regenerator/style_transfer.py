"""
Style transfer process for applying style from one clip to another.
"""
from typing import Optional
from uuid import UUID

from shared.logging import get_logger
from shared.errors import ValidationError

from modules.clip_regenerator.data_loader import load_clip_prompts_from_job_stages
from modules.clip_regenerator.style_analyzer import extract_style_keywords, extract_style_with_llm
from modules.clip_regenerator.style_applier import apply_style_to_prompt, StyleTransferOptions
from modules.clip_regenerator.cost_tracker import track_regeneration_cost

logger = get_logger("clip_regenerator.style_transfer")


async def transfer_style(
    job_id: UUID,
    source_clip_index: int,
    target_clip_index: int,
    transfer_options: StyleTransferOptions,
    additional_instruction: Optional[str] = None
) -> str:
    """
    Transfer style from source clip to target clip.
    
    Steps:
    1. Load clip prompts from job_stages
    2. Extract source and target prompts
    3. Extract style keywords from source prompt
    4. Apply style to target prompt
    5. Add additional instruction if provided
    
    Args:
        job_id: Job ID
        source_clip_index: Index of source clip (style to copy)
        target_clip_index: Index of target clip (clip to modify)
        transfer_options: Options controlling which style elements to transfer
        additional_instruction: Optional additional instruction to append
        
    Returns:
        Modified prompt with style applied
        
    Raises:
        ValidationError: If clip indices are invalid or data loading fails
    """
    logger.info(
        f"Starting style transfer",
        extra={
            "job_id": str(job_id),
            "source_clip_index": source_clip_index,
            "target_clip_index": target_clip_index
        }
    )
    
    # Step 1: Load clip prompts
    clip_prompts = await load_clip_prompts_from_job_stages(job_id)
    if not clip_prompts:
        raise ValidationError(f"Failed to load clip prompts for job {job_id}")
    
    # Step 2: Validate clip indices
    if source_clip_index < 0 or source_clip_index >= len(clip_prompts.clip_prompts):
        raise ValidationError(
            f"Invalid source_clip_index: {source_clip_index}. "
            f"Valid range: 0-{len(clip_prompts.clip_prompts) - 1}"
        )
    
    if target_clip_index < 0 or target_clip_index >= len(clip_prompts.clip_prompts):
        raise ValidationError(
            f"Invalid target_clip_index: {target_clip_index}. "
            f"Valid range: 0-{len(clip_prompts.clip_prompts) - 1}"
        )
    
    if source_clip_index == target_clip_index:
        raise ValidationError("Source and target clip indices must be different")
    
    # Step 3: Extract prompts
    source_prompt = clip_prompts.clip_prompts[source_clip_index].prompt
    target_prompt = clip_prompts.clip_prompts[target_clip_index].prompt
    
    logger.debug(
        f"Extracted prompts",
        extra={
            "job_id": str(job_id),
            "source_prompt_length": len(source_prompt),
            "target_prompt_length": len(target_prompt)
        }
    )
    
    # Step 4: Extract style keywords from source
    style_keywords = extract_style_keywords(source_prompt)
    
    # Check if we need LLM fallback
    total_keywords = len(style_keywords.color) + len(style_keywords.lighting) + len(style_keywords.mood)
    if total_keywords < 2:
        logger.info(
            f"Insufficient keywords ({total_keywords}), using LLM fallback",
            extra={"job_id": str(job_id), "source_clip_index": source_clip_index}
        )
        style_keywords = await extract_style_with_llm(source_prompt)
        
        # Track LLM cost
        await track_regeneration_cost(
            job_id=job_id,
            cost=0.015,  # Approximate cost for GPT-4o style extraction
            operation="style_transfer_llm_fallback"
        )
    
    logger.debug(
        f"Style keywords extracted",
        extra={
            "job_id": str(job_id),
            "color_keywords": style_keywords.color,
            "lighting_keywords": style_keywords.lighting,
            "mood_keywords": style_keywords.mood
        }
    )
    
    # Step 5: Apply style to target prompt
    modified_prompt = apply_style_to_prompt(target_prompt, style_keywords, transfer_options)
    
    # Step 6: Add additional instruction if provided
    if additional_instruction and additional_instruction.strip():
        modified_prompt = f"{modified_prompt}. {additional_instruction.strip()}"
    
    logger.info(
        f"Style transfer complete",
        extra={
            "job_id": str(job_id),
            "target_clip_index": target_clip_index,
            "modified_prompt_length": len(modified_prompt)
        }
    )
    
    return modified_prompt

