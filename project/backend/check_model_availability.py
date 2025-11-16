#!/usr/bin/env python3
"""Check which video models are actually available on Replicate."""
import asyncio
from modules.video_generator.model_validator import validate_model_config
from modules.video_generator.config import MODEL_CONFIGS

async def main():
    print("\n=== CHECKING MODEL AVAILABILITY ===\n")
    
    for model_key, config in MODEL_CONFIGS.items():
        print(f"\nModel: {model_key}")
        print(f"  Replicate string: {config['replicate_string']}")
        print(f"  Version: {config['version']}")
        print(f"  Full model: {config['full_model']}")
        
        # Check if model is valid
        is_valid, error_msg = await validate_model_config(model_key, config)
        
        if is_valid:
            print(f"  Status: ✅ VALID")
        else:
            print(f"  Status: ❌ INVALID")
            print(f"  Error: {error_msg}")
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(main())

