"""
Multi-clip instruction parser.

Parses natural language instructions to identify which clips to modify.
"""
import re
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel

from shared.logging import get_logger
from shared.models.audio import AudioAnalysis

logger = get_logger("clip_regenerator.instruction_parser")


class ClipInstruction(BaseModel):
    """Instruction for a specific clip."""
    
    clip_index: int
    instruction: str


def extract_modification(instruction: str) -> str:
    """
    Extract modification text from instruction, removing clip references.
    
    Args:
        instruction: Full instruction text
        
    Returns:
        Clean modification instruction
    """
    # Remove clip references
    modification = instruction
    
    # Remove range notation first: "clips 1-3"
    modification = re.sub(r'clips?\s+\d+\s*-\s*\d+', '', modification, flags=re.IGNORECASE)
    
    # Remove "clip" or "clips" followed by numbers (handles "clips 2 and 4")
    modification = re.sub(r'clip[s]?\s+\d+(\s+and\s+\d+)*', '', modification, flags=re.IGNORECASE)
    
    # Remove standalone numbers that might be clip references (after "and", "or", etc.)
    # Only remove if they appear after clip-related words
    modification = re.sub(r'(and|or)\s+\d+', '', modification, flags=re.IGNORECASE)
    
    # Remove "all clips", "every clip"
    modification = re.sub(r'(all|every)\s+clip[s]?', '', modification, flags=re.IGNORECASE)
    
    # Remove "first N", "last N"
    modification = re.sub(r'(first|last)\s+\d+', '', modification, flags=re.IGNORECASE)
    
    # Remove "except clip N"
    modification = re.sub(r'except\s+clip[s]?\s+\d+', '', modification, flags=re.IGNORECASE)
    
    # Remove audio context references
    modification = re.sub(r'(chorus|verse|bridge|intro|outro)\s+clip[s]?', '', modification, flags=re.IGNORECASE)
    
    # Remove "the" before remaining words if it's orphaned
    modification = re.sub(r'^\s*the\s+', '', modification, flags=re.IGNORECASE)
    
    # Clean up whitespace
    modification = re.sub(r'\s+', ' ', modification).strip()
    
    # Remove leading/trailing punctuation
    modification = modification.strip('.,;:')
    
    return modification


def parse_multi_clip_instruction(
    instruction: str,
    total_clips: int,
    audio_data: Optional[AudioAnalysis] = None
) -> List[ClipInstruction]:
    """
    Parse instruction to identify target clips.
    
    Returns list of (clip_index, instruction) pairs.
    
    Args:
        instruction: User instruction (e.g., "make clips 2 and 4 brighter")
        total_clips: Total number of clips in the job
        audio_data: Optional audio analysis data for context matching
        
    Returns:
        List of ClipInstruction objects
    """
    instruction_lower = instruction.lower()
    modification = extract_modification(instruction)
    
    # Check for "all clips" or "every clip"
    if "all clips" in instruction_lower or "every clip" in instruction_lower:
        # Check for exclusion: "all clips except clip 2"
        if "except" in instruction_lower:
            excluded = re.findall(r'except\s+clip[s]?\s+(\d+)', instruction_lower)
            excluded_indices = [int(x) - 1 for x in excluded]
            return [
                ClipInstruction(clip_index=i, instruction=modification)
                for i in range(total_clips) if i not in excluded_indices
            ]
        else:
            return [
                ClipInstruction(clip_index=i, instruction=modification)
                for i in range(total_clips)
            ]
    
    # Check for range notation first (before specific numbers): "clips 1-3"
    range_match = re.search(r'clips?\s+(\d+)\s*-\s*(\d+)', instruction_lower)
    if range_match:
        start_idx = int(range_match.group(1)) - 1
        end_idx = int(range_match.group(2)) - 1
        return [
            ClipInstruction(clip_index=i, instruction=modification)
            for i in range(max(0, start_idx), min(total_clips, end_idx + 1))
        ]
    
    # Check for specific clip numbers: "clips 2 and 4"
    # Find all numbers after "clip" or "clips" and after "and"/"or"
    clip_numbers = []
    # First, find numbers directly after "clip" or "clips"
    clip_numbers.extend(re.findall(r'clip[s]?\s+(\d+)', instruction_lower))
    # Then find numbers after "and" or "or" (which might be clip numbers)
    and_numbers = re.findall(r'(?:and|or)\s+(\d+)', instruction_lower)
    clip_numbers.extend(and_numbers)
    
    if clip_numbers:
        # Remove duplicates and convert to indices
        unique_indices = set()
        for num in clip_numbers:
            idx = int(num) - 1
            if 0 <= idx < total_clips:
                unique_indices.add(idx)
        
        if unique_indices:
            return [
                ClipInstruction(clip_index=i, instruction=modification)
                for i in sorted(unique_indices)
            ]
    
    # Check for audio context (chorus, verse, etc.)
    if "chorus" in instruction_lower and audio_data:
        chorus_clips = identify_chorus_clips(audio_data)
        if chorus_clips:
            return [
                ClipInstruction(clip_index=i, instruction=modification)
                for i in chorus_clips
            ]
    
    if "verse" in instruction_lower and audio_data:
        verse_clips = identify_verse_clips(audio_data)
        if verse_clips:
            return [
                ClipInstruction(clip_index=i, instruction=modification)
                for i in verse_clips
            ]
    
    # Check for range-based (first 3, last 2, etc.)
    if "first" in instruction_lower:
        match = re.search(r'first\s+(\d+)', instruction_lower)
        if match:
            count = int(match.group(1))
            return [
                ClipInstruction(clip_index=i, instruction=modification)
                for i in range(min(count, total_clips))
            ]
    
    if "last" in instruction_lower:
        match = re.search(r'last\s+(\d+)', instruction_lower)
        if match:
            count = int(match.group(1))
            start_idx = max(0, total_clips - count)
            return [
                ClipInstruction(clip_index=i, instruction=modification)
                for i in range(start_idx, total_clips)
            ]
    
    # Default: apply to all clips if no match
    logger.warning(
        f"No clip pattern matched, defaulting to all clips",
        extra={"instruction": instruction[:100]}
    )
    return [
        ClipInstruction(clip_index=i, instruction=modification)
        for i in range(total_clips)
    ]


def identify_chorus_clips(audio_data: AudioAnalysis) -> List[int]:
    """
    Identify clips that correspond to chorus segments.
    
    Args:
        audio_data: Audio analysis data with song structure and clip boundaries
        
    Returns:
        List of clip indices that overlap with chorus segments
    """
    chorus_clips = []
    
    if not audio_data.song_structure or not audio_data.clip_boundaries:
        return chorus_clips
    
    for i, boundary in enumerate(audio_data.clip_boundaries):
        # Calculate clip end time
        clip_start = boundary.start
        clip_end = boundary.start + boundary.duration
        
        # Check if clip overlaps with any chorus segment
        for segment in audio_data.song_structure:
            if segment.type == "chorus":
                segment_start = segment.start
                segment_end = segment.end
                
                # Check for overlap
                if (clip_start >= segment_start and clip_start < segment_end) or \
                   (clip_end > segment_start and clip_end <= segment_end) or \
                   (clip_start < segment_start and clip_end > segment_end):
                    chorus_clips.append(i)
                    break
    
    return chorus_clips


def identify_verse_clips(audio_data: AudioAnalysis) -> List[int]:
    """
    Identify clips that correspond to verse segments.
    
    Args:
        audio_data: Audio analysis data with song structure and clip boundaries
        
    Returns:
        List of clip indices that overlap with verse segments
    """
    verse_clips = []
    
    if not audio_data.song_structure or not audio_data.clip_boundaries:
        return verse_clips
    
    for i, boundary in enumerate(audio_data.clip_boundaries):
        # Calculate clip end time
        clip_start = boundary.start
        clip_end = boundary.start + boundary.duration
        
        # Check if clip overlaps with any verse segment
        for segment in audio_data.song_structure:
            if segment.type == "verse":
                segment_start = segment.start
                segment_end = segment.end
                
                # Check for overlap
                if (clip_start >= segment_start and clip_start < segment_end) or \
                   (clip_end > segment_start and clip_end <= segment_end) or \
                   (clip_start < segment_start and clip_end > segment_end):
                    verse_clips.append(i)
                    break
    
    return verse_clips

