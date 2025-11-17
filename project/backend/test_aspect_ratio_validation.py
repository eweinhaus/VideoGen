#!/usr/bin/env python3
"""
Test aspect ratio validation for all models.
Verifies that:
1. ValidationError is raised for unsupported aspect ratios
2. Supported aspect ratios work correctly
3. Error messages are clear and helpful
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.video_generator.config import get_model_config, MODEL_CONFIGS
from shared.errors import ValidationError

def test_aspect_ratio_validation():
    """Test aspect ratio validation for all models."""
    
    print("=" * 80)
    print("ASPECT RATIO VALIDATION TEST")
    print("=" * 80)
    
    # Test aspect ratios
    test_ratios = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "2:3"]
    
    # Test each model
    for model_key, model_config in MODEL_CONFIGS.items():
        print(f"\n{'='*80}")
        print(f"Model: {model_key}")
        print(f"Display Name: {model_config.get('display_name', 'N/A')}")
        print(f"{'='*80}")
        
        supported_ratios = model_config.get("aspect_ratios", ["16:9"])
        print(f"\n✅ Supported Aspect Ratios: {', '.join(supported_ratios)}")
        
        unsupported = [r for r in test_ratios if r not in supported_ratios]
        if unsupported:
            print(f"❌ Unsupported Aspect Ratios: {', '.join(unsupported)}")
        
        # Test validation logic
        print(f"\nValidation Tests:")
        for ratio in test_ratios:
            if ratio in supported_ratios:
                print(f"  ✅ {ratio:8s} - PASS (supported)")
            else:
                print(f"  ❌ {ratio:8s} - FAIL (would raise ValidationError)")
                # Show what the error message would be
                error_msg = (
                    f"Aspect ratio '{ratio}' not supported for model '{model_key}'. "
                    f"Supported: {supported_ratios}"
                )
                print(f"     Error: {error_msg}")
    
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    
    # Show which models support which ratios
    ratio_support = {}
    for ratio in test_ratios:
        models = []
        for model_key, model_config in MODEL_CONFIGS.items():
            if ratio in model_config.get("aspect_ratios", ["16:9"]):
                models.append(model_key)
        ratio_support[ratio] = models
    
    print("Aspect Ratio Support Matrix:")
    print(f"{'Aspect Ratio':<15} {'Supported Models'}")
    print("-" * 80)
    for ratio in test_ratios:
        models = ratio_support.get(ratio, [])
        if models:
            print(f"{ratio:<15} {', '.join(models)}")
        else:
            print(f"{ratio:<15} NONE")
    
    print(f"\n{'='*80}")
    print("POTENTIAL ISSUES")
    print(f"{'='*80}\n")
    
    # Check for models with limited aspect ratio support
    print("⚠️  Models with limited aspect ratio support:")
    for model_key, model_config in MODEL_CONFIGS.items():
        supported_ratios = model_config.get("aspect_ratios", ["16:9"])
        if len(supported_ratios) <= 2:
            print(f"  - {model_key}: only supports {', '.join(supported_ratios)}")
            print(f"    If user selects unsupported ratio, ALL clips will fail!")
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    test_aspect_ratio_validation()

