"""
Debug script to see exact identity blocks being generated.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent))

from shared.models.scene import ScenePlan, Character, Scene, Style, ClipScript
from modules.prompt_generator.process import process


async def debug_identity_blocks():
    """Debug identity block generation."""

    character = Character(
        id="char_1",
        description="""Alice - FIXED CHARACTER IDENTITY:
- Hair: shoulder-length brown curly hair with natural texture and volume, parted in the middle
- Face: olive skin tone, round face shape, defined cheekbones, no visible freckles
- Eyes: dark brown eyes, thick arched eyebrows
- Clothing: bright blue denim jacket with silver buttons and rolled sleeves, white crew-neck t-shirt underneath, dark blue jeans
- Accessories: round tortoiseshell glasses with thick frames, silver hoop earrings (1 inch diameter)
- Build: athletic build, approximately 5'6" height, medium frame
- Age: appears mid-20s

CRITICAL: These are EXACT, IMMUTABLE features. Do not modify or reinterpret these specific details. This character appears in all scenes with this precise appearance.""",
        role="main character"
    )

    scene = Scene(
        id="scene_1",
        description="Urban street at night with neon signs",
        time_of_day="night"
    )

    style = Style(
        color_palette=["#00FFFF", "#FF00FF", "#FFFF00"],
        visual_style="Cinematic urban style with vibrant neon colors",
        mood="Energetic and confident",
        lighting="High-contrast neon lighting with deep shadows",
        cinematography="Smooth tracking shots with handheld camera work"
    )

    clip_scripts = [
        ClipScript(
            clip_index=0,
            start=0.0,
            end=5.0,
            visual_description="Artist walks down the street",
            motion="Smooth tracking shot",
            camera_angle="Medium wide shot",
            characters=["char_1"],
            scenes=["scene_1"],
            lyrics_context="Living the dream",
            beat_intensity="medium"
        ),
        ClipScript(
            clip_index=1,
            start=5.0,
            end=10.0,
            visual_description="Artist looks at city skyline",
            motion="Static shot",
            camera_angle="Medium shot",
            characters=["char_1"],
            scenes=["scene_1"],
            lyrics_context="In the city lights",
            beat_intensity="low"
        ),
    ]

    job_id = uuid4()
    plan = ScenePlan(
        job_id=job_id,
        video_summary="An artist living their dream in the city",
        characters=[character],
        scenes=[scene],
        style=style,
        clip_scripts=clip_scripts,
        transitions=[]
    )

    result = await process(
        job_id=job_id,
        plan=plan,
        references=None,
        beat_timestamps=[0.0, 2.5, 5.0, 7.5, 10.0]
    )

    print("\n" + "="*80)
    print("IDENTITY BLOCK COMPARISON")
    print("="*80 + "\n")

    for clip_prompt in result.clip_prompts:
        prompt = clip_prompt.prompt
        clip_index = clip_prompt.clip_index

        print(f"\n{'='*80}")
        print(f"CLIP {clip_index}")
        print(f"{'='*80}\n")

        # Find identity block
        if "CHARACTER IDENTITY:" in prompt:
            identity_start = prompt.index("CHARACTER IDENTITY:")
            identity_block = prompt[identity_start:]

            print(f"Length: {len(identity_block)} characters")
            print(f"Length of full prompt: {len(prompt)} characters\n")
            print(f"Identity Block (FULL):\n{identity_block}\n")

            # Check for CRITICAL keyword
            if "CRITICAL:" in identity_block:
                print("✅ CRITICAL keyword found")
            else:
                print("❌ CRITICAL keyword MISSING")
                # Show where it should be
                print(f"\nLast 200 chars of identity block:")
                print(f"{identity_block[-200:]}")
        else:
            print("❌ NO IDENTITY BLOCK FOUND")

        print("\n" + "-"*80 + "\n")

    # Compare blocks
    blocks = []
    for clip_prompt in result.clip_prompts:
        if "CHARACTER IDENTITY:" in clip_prompt.prompt:
            identity_start = clip_prompt.prompt.index("CHARACTER IDENTITY:")
            blocks.append(clip_prompt.prompt[identity_start:])

    if len(blocks) >= 2:
        print("\n" + "="*80)
        print("BLOCK COMPARISON")
        print("="*80 + "\n")

        block0 = blocks[0]
        block1 = blocks[1]

        print(f"Block 0 length: {len(block0)}")
        print(f"Block 1 length: {len(block1)}")
        print(f"Blocks are identical: {block0 == block1}\n")

        if block0 != block1:
            # Find where they differ
            min_len = min(len(block0), len(block1))
            first_diff = None
            for i in range(min_len):
                if block0[i] != block1[i]:
                    first_diff = i
                    break

            if first_diff is not None:
                print(f"First difference at position {first_diff}:")
                start = max(0, first_diff - 50)
                end = min(min_len, first_diff + 50)
                print(f"\nBlock 0 [{start}:{end}]:")
                print(repr(block0[start:end]))
                print(f"\nBlock 1 [{start}:{end}]:")
                print(repr(block1[start:end]))
            elif len(block0) != len(block1):
                print("Blocks are identical up to length difference")
                print(f"\nLonger block ends with:")
                longer = block0 if len(block0) > len(block1) else block1
                print(longer[min_len:])


if __name__ == "__main__":
    asyncio.run(debug_identity_blocks())
