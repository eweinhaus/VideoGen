#!/usr/bin/env python3
"""
Diagnose job fdde43cf-b811-4b7f-8143-ed6aecd8f19e to understand why uploaded character
doesn't appear in all clips.
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / "project" / "backend" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "project" / "backend"))

from supabase import create_client

async def diagnose_job():
    job_id = "fdde43cf-b811-4b7f-8143-ed6aecd8f19e"
    
    # Get Supabase credentials
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY/SUPABASE_KEY")
        return
    
    # Create Supabase client (sync version)
    supabase = create_client(supabase_url, supabase_key)
    
    print(f"=== DIAGNOSING JOB {job_id} ===\n")
    
    # Get job details
    job_result = supabase.table("jobs").select("*").eq("id", job_id).execute()
    
    if not job_result.data:
        print(f"ERROR: Job {job_id} not found")
        return
    
    job = job_result.data[0]
    print(f"Job Status: {job.get('status')}")
    print(f"Created: {job.get('created_at')}")
    print(f"User Prompt: {job.get('user_prompt', 'N/A')[:200]}")
    print()
    
    # Get job stages
    stages_result = supabase.table("job_stages").select("*").eq("job_id", job_id).execute()
    
    if not stages_result.data:
        print("ERROR: No job stages found")
        return
    
    stages = {stage["stage_name"]: stage for stage in stages_result.data}
    
    # === 1. CHECK REFERENCE GENERATOR STAGE ===
    print("=" * 80)
    print("1. REFERENCE GENERATOR STAGE")
    print("=" * 80)
    
    if "reference_generator" not in stages:
        print("ERROR: reference_generator stage not found")
        return
    
    ref_gen_metadata = stages["reference_generator"].get("metadata", {})
    
    # Print full metadata structure to understand what's there
    print("\nFull Reference Generator Metadata Keys:")
    print(f"  {list(ref_gen_metadata.keys())}")
    
    # Check for reference_images (might be nested)
    reference_images = None
    if "reference_images" in ref_gen_metadata:
        reference_images = ref_gen_metadata["reference_images"]
        print(f"\nFound 'reference_images' key")
        print(f"  Type: {type(reference_images)}")
        if isinstance(reference_images, dict):
            print(f"  Keys: {list(reference_images.keys())}")
            if "character_references" in reference_images:
                char_refs = reference_images["character_references"]
                print(f"\nCharacter References Found: {len(char_refs)}")
            else:
                print(f"\nNo 'character_references' in reference_images")
        else:
            print(f"  Content preview: {str(reference_images)[:200]}")
    
    # Check direct character_references
    char_refs = None
    uploaded_char_ref = None
    
    if "character_references" in ref_gen_metadata:
        char_refs = ref_gen_metadata["character_references"]
    elif reference_images and isinstance(reference_images, dict) and "character_references" in reference_images:
        char_refs = reference_images["character_references"]
    
    if char_refs:
        print(f"\nCharacter References Found: {len(char_refs)}")
        
        for i, ref in enumerate(char_refs):
            char_id = ref.get("character_id")
            prompt_used = ref.get("prompt_used", "N/A")
            image_url = ref.get("image_url", "")
            
            print(f"\n  [{i+1}] Character ID: {char_id}")
            print(f"      Prompt: {prompt_used[:60]}")
            print(f"      URL: {image_url[:80]}...")
            
            if prompt_used == "user_uploaded":
                uploaded_char_ref = ref
                print(f"      ✓ THIS IS THE UPLOADED CHARACTER IMAGE")
        
        if not uploaded_char_ref:
            print("\n⚠️  WARNING: No uploaded character reference found (prompt_used='user_uploaded')")
        else:
            print(f"\n✓ Uploaded character is: {uploaded_char_ref.get('character_id')}")
    else:
        print("\n⚠️  WARNING: No character_references found in metadata")
        print("\nDumping full reference_generator metadata for inspection:")
        print(json.dumps(ref_gen_metadata, indent=2, default=str)[:2000])
        print("\n... (truncated)")
        
        # Don't return - continue to check other stages
    
    # === 2. CHECK SCENE PLANNER STAGE ===
    print("\n" + "=" * 80)
    print("2. SCENE PLANNER STAGE")
    print("=" * 80)
    
    if "scene_planner" not in stages:
        print("ERROR: scene_planner stage not found")
        # Don't return - continue diagnosis
        main_character_id = None
    else:
        scene_plan_metadata = stages["scene_planner"].get("metadata", {})
        
        if "scene_plan" in scene_plan_metadata:
            scene_plan = scene_plan_metadata["scene_plan"]
            characters = scene_plan.get("characters", [])
            
            print(f"\nCharacters in Scene Plan: {len(characters)}")
            
            main_character_id = characters[0].get("id") if characters else None
            
            for i, char in enumerate(characters):
                char_id = char.get("id")
                char_name = char.get("name")
                char_role = char.get("role")
                
                is_main = " ← MAIN CHARACTER (first in list)" if i == 0 else ""
                matches_upload = " ← MATCHES UPLOADED IMAGE" if uploaded_char_ref and char_id == uploaded_char_ref.get("character_id") else ""
                
                print(f"\n  [{i+1}] ID: {char_id}{is_main}{matches_upload}")
                print(f"      Name: {char_name}")
                print(f"      Role: {char_role}")
            
            if main_character_id:
                print(f"\n✓ Main character (first in list): {main_character_id}")
                
                if uploaded_char_ref and main_character_id != uploaded_char_ref.get("character_id"):
                    print(f"\n⚠️  PROBLEM DETECTED: Main character ID ({main_character_id}) does NOT match uploaded character ID ({uploaded_char_ref.get('character_id')})")
                    print(f"    The uploaded image will only be used when {uploaded_char_ref.get('character_id')} is in clip.characters")
                    print(f"    But the system thinks {main_character_id} is the main character!")
        else:
            print("ERROR: No scene_plan in metadata")
            main_character_id = None
    
    # === 3. CHECK PROMPT GENERATOR STAGE ===
    print("\n" + "=" * 80)
    print("3. PROMPT GENERATOR STAGE")
    print("=" * 80)
    
    if "prompt_generator" not in stages:
        print("ERROR: prompt_generator stage not found")
        # Continue to root cause analysis anyway
    
    prompt_gen_metadata = stages["prompt_generator"].get("metadata", {})
    
    if "clip_prompts" in prompt_gen_metadata:
        clip_prompts_data = prompt_gen_metadata["clip_prompts"]
        clip_prompts = clip_prompts_data.get("clip_prompts", [])
        
        print(f"\nTotal Clips: {len(clip_prompts)}")
        
        clips_with_main_char = 0
        clips_with_uploaded_char = 0
        clips_without_any_char = 0
        
        for clip in clip_prompts:
            clip_index = clip.get("clip_index")
            char_ref_urls = clip.get("character_reference_urls", [])
            scene_ref_url = clip.get("scene_reference_url")
            
            # Check if this clip has the uploaded character reference
            has_uploaded = False
            if uploaded_char_ref:
                uploaded_url = uploaded_char_ref.get("image_url")
                if uploaded_url in char_ref_urls:
                    has_uploaded = True
                    clips_with_uploaded_char += 1
            
            if not char_ref_urls:
                clips_without_any_char += 1
            
            status = "✓ HAS UPLOADED CHAR" if has_uploaded else "✗ NO UPLOADED CHAR"
            
            print(f"\n  Clip {clip_index}: {status}")
            print(f"    Character refs: {len(char_ref_urls)}")
            if char_ref_urls:
                for j, url in enumerate(char_ref_urls[:2]):
                    print(f"      [{j+1}] {url[:80]}...")
        
        print(f"\n--- SUMMARY ---")
        print(f"Clips with uploaded character: {clips_with_uploaded_char}/{len(clip_prompts)}")
        print(f"Clips without any character: {clips_without_any_char}/{len(clip_prompts)}")
        
        if clips_with_uploaded_char < len(clip_prompts):
            missing_count = len(clip_prompts) - clips_with_uploaded_char
            print(f"\n⚠️  PROBLEM CONFIRMED: {missing_count} clip(s) are missing the uploaded character reference")
    else:
        print("ERROR: No clip_prompts in metadata")
        return
    
    # === 4. ROOT CAUSE ANALYSIS ===
    print("\n" + "=" * 80)
    print("4. ROOT CAUSE ANALYSIS")
    print("=" * 80)
    
    if uploaded_char_ref and main_character_id:
        uploaded_char_id = uploaded_char_ref.get("character_id")
        
        if uploaded_char_id != main_character_id:
            print(f"\n🔴 ROOT CAUSE IDENTIFIED:")
            print(f"\n   The character matcher matched your uploaded image to: {uploaded_char_id}")
            print(f"   But the scene planner's first character (main) is: {main_character_id}")
            print(f"\n   The prompt generator uses the FIRST character ({main_character_id}) as main,")
            print(f"   but your uploaded image is for {uploaded_char_id}.")
            print(f"\n   SOLUTION:")
            print(f"   - Fix character_matcher.py to be more intelligent about role detection")
            print(f"   - OR ensure uploaded image is matched to first character in scene plan")
            print(f"   - OR change reference_mapper.py to identify main character from uploaded images")
        else:
            print(f"\n✓ Character matching looks correct (uploaded={uploaded_char_id}, main={main_character_id})")
            print(f"\n   The issue might be in reference_mapper.py - let me check clip.characters...")
            
            # Check if main character is in all clip.characters
            scene_plan = scene_plan_metadata.get("scene_plan", {})
            clip_scripts = scene_plan.get("clip_scripts", [])
            
            print(f"\n   Checking which clips include main character in their characters list:")
            
            for clip_script in clip_scripts:
                clip_idx = clip_script.get("clip_index")
                clip_chars = clip_script.get("characters", [])
                has_main = main_character_id in clip_chars
                
                status = "✓" if has_main else "✗"
                print(f"     Clip {clip_idx}: {status} (characters: {clip_chars})")
            
            print(f"\n🔴 ROOT CAUSE IDENTIFIED:")
            print(f"\n   The Scene Planner is NOT including the main character in all clips.")
            print(f"   Even though reference_mapper.py should add the main character to ALL clips,")
            print(f"   it seems this logic may not be working correctly.")
            print(f"\n   SOLUTION:")
            print(f"   - Verify reference_mapper.py line 113-136 is being executed")
            print(f"   - Check logs for 'Including main character' messages")
            print(f"   - Ensure main_character_id is correctly identified and passed to map_clip_references()")

if __name__ == "__main__":
    asyncio.run(diagnose_job())

