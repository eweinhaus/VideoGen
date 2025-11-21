#!/usr/bin/env python3
"""
Check which clips have the "rapper" character and which don't in job fdde43cf-b811-4b7f-8143-ed6aecd8f19e
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
env_path = Path(__file__).parent / "project" / "backend" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

job_id = "fdde43cf-b811-4b7f-8143-ed6aecd8f19e"

# Get Supabase credentials
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

supabase = create_client(supabase_url, supabase_key)

print(f"=== ANALYZING CLIP CHARACTER DISTRIBUTION ===\n")

# Get job stages
stages_result = supabase.table("job_stages").select("*").eq("job_id", job_id).execute()
stages = {stage["stage_name"]: stage for stage in stages_result.data}

# Get scene plan
scene_plan = stages["scene_planner"]["metadata"]["scene_plan"]
clip_scripts = scene_plan.get("clip_scripts", [])

# Get reference generator data
ref_gen_metadata = stages["reference_generator"]["metadata"]
reference_images = ref_gen_metadata.get("reference_images", {})
character_refs = reference_images.get("character_references", [])

# Build character reference URLs map
char_ref_map = {}
for ref in character_refs:
    char_id = ref.get("character_id")
    url = ref.get("image_url")
    if char_id not in char_ref_map:
        char_ref_map[char_id] = []
    char_ref_map[char_id].append(url)

print(f"Character References Available:")
for char_id, urls in char_ref_map.items():
    print(f"  {char_id}: {len(urls)} reference image(s)")
print()

# Get prompt generator data
prompt_gen_metadata = stages["prompt_generator"]["metadata"]
clip_prompts = prompt_gen_metadata["clip_prompts"]["clip_prompts"]

print(f"=== CLIP-BY-CLIP ANALYSIS ===\n")

clips_with_rapper = 0
clips_without_rapper = 0
rapper_ref_url = char_ref_map.get("rapper", [None])[0] if "rapper" in char_ref_map else None

for i, clip in enumerate(clip_prompts[:10]):  # Show first 10
    clip_index = clip.get("clip_index")
    
    # Get which characters are in this clip from scene plan
    clip_script = clip_scripts[clip_index] if clip_index < len(clip_scripts) else None
    clip_characters = clip_script.get("characters", []) if clip_script else []
    
    # Get character references in the prompt
    char_ref_urls = clip.get("character_reference_urls", [])
    
    has_rapper_in_chars = "rapper" in clip_characters
    has_rapper_ref = rapper_ref_url in char_ref_urls if rapper_ref_url else False
    
    if has_rapper_in_chars or has_rapper_ref:
        clips_with_rapper += 1
        status = "✓ HAS RAPPER"
    else:
        clips_without_rapper += 1
        status = "✗ NO RAPPER"
    
    print(f"Clip {clip_index}: {status}")
    print(f"  Characters in scene plan: {clip_characters}")
    print(f"  Character refs in prompt: {len(char_ref_urls)}")
    if char_ref_urls:
        print(f"    First ref: {char_ref_urls[0][-50:]}")
    print()

print(f"\n=== SUMMARY ===")
print(f"Clips with rapper: {clips_with_rapper}")
print(f"Clips without rapper: {clips_without_rapper}")
print(f"\n=== ANALYSIS ===")

if clips_without_rapper > 0:
    print(f"\n🔴 PROBLEM IDENTIFIED:")
    print(f"   The Scene Planner did NOT include 'rapper' in all clips' character lists.")
    print(f"   The reference_mapper.py should be adding the main character to ALL clips,")
    print(f"   but it's only adding it to clips where the scene planner included it.")
    print(f"\n   This means the 'always include main character' logic (lines 113-136)")
    print(f"   in reference_mapper.py is NOT working correctly.")
    print(f"\n   LIKELY CAUSE:")
    print(f"   - main_character_id might not be correctly identified")
    print(f"   - OR the logic has a bug and isn't adding the main char to all clips")
else:
    print(f"\n✓ All clips have the rapper character in the scene plan.")
    print(f"   The issue might be in video generation stage instead.")

