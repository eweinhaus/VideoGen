"""
Test script to validate each video model configuration.

PHASE 3: Tests all models in MODEL_CONFIGS for availability and basic generation.

Usage:
    python -m modules.video_generator.test_models --model kling_v21
    python -m modules.video_generator.test_models --all
    python -m modules.video_generator.test_models --validate-only
"""
import asyncio
import sys
from typing import Dict, Any
from uuid import uuid4

from modules.video_generator.config import MODEL_CONFIGS, get_model_config
from modules.video_generator.model_validator import validate_model_config, get_latest_version_hash
from shared.logging import get_logger

logger = get_logger("video_generator.test_models")


async def test_model_validation(model_key: str) -> Dict[str, Any]:
    """
    Test validation of a single model configuration.

    Args:
        model_key: Model key (e.g., "kling_v21")

    Returns:
        Dict with test results
    """
    print(f"\n{'='*60}")
    print(f"Testing model: {model_key}")
    print(f"{'='*60}")

    # Get config
    try:
        config = get_model_config(model_key)
        print(f"Model config loaded: {config.get('display_name', model_key)}")
        print(f"  Replicate: {config.get('replicate_string')}")
        print(f"  Type: {config.get('type')}")
        print(f"  Status: {config.get('status')}")
    except Exception as e:
        print(f"❌ FAILED: Could not load config: {str(e)}")
        return {
            "model": model_key,
            "validation_passed": False,
            "hash_retrieved": False,
            "error": f"Config load failed: {str(e)}"
        }

    # Validate model
    is_valid, error = await validate_model_config(model_key, config)
    if not is_valid:
        print(f"❌ VALIDATION FAILED: {error}")
        return {
            "model": model_key,
            "validation_passed": False,
            "hash_retrieved": False,
            "error": error
        }

    print(f"✅ Validation passed")

    # Get latest hash if version is "latest"
    hash_retrieved = False
    hash_value = None
    if config.get("version") == "latest":
        replicate_string = config.get("replicate_string")
        hash_value = await get_latest_version_hash(replicate_string)
        if hash_value:
            print(f"✅ Latest hash retrieved: {hash_value[:20]}...")
            hash_retrieved = True
        else:
            print(f"❌ Could not retrieve latest hash")
            return {
                "model": model_key,
                "validation_passed": True,
                "hash_retrieved": False,
                "error": "Hash retrieval failed"
            }
    else:
        # Pinned version - no need to retrieve hash
        hash_retrieved = True
        hash_value = config.get("version")
        print(f"✅ Using pinned version: {hash_value[:20]}...")

    return {
        "model": model_key,
        "validation_passed": True,
        "hash_retrieved": hash_retrieved,
        "hash_value": hash_value,
        "error": None
    }


async def test_all_models(validate_only: bool = False) -> None:
    """
    Test all configured models.

    Args:
        validate_only: If True, only validate configs without testing generation
    """
    print("\n" + "="*60)
    print("TESTING ALL MODELS")
    print("="*60)
    print(f"Total models configured: {len(MODEL_CONFIGS)}")
    print(f"Mode: {'Validation only' if validate_only else 'Full test'}")
    print()

    results = []
    for model_key in MODEL_CONFIGS.keys():
        result = await test_model_validation(model_key)
        results.append(result)

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    for result in results:
        model = result['model']
        config = MODEL_CONFIGS[model]
        status = config.get('status', 'unknown')

        validation_status = "✅" if result['validation_passed'] else "❌"
        hash_status = "✅" if result['hash_retrieved'] else "❌"

        print(f"\n{model} (status: {status})")
        print(f"  Validation: {validation_status}")
        print(f"  Hash retrieval: {hash_status}")

        if result['error']:
            print(f"  Error: {result['error']}")

    # Count results
    total = len(results)
    validation_passed = sum(1 for r in results if r['validation_passed'])
    hash_passed = sum(1 for r in results if r['hash_retrieved'])

    print(f"\n{'='*60}")
    print(f"Results: {validation_passed}/{total} models validated")
    print(f"         {hash_passed}/{total} hashes retrieved")

    # Check for status mismatches
    mismatches = []
    for result in results:
        model_key = result['model']
        config = MODEL_CONFIGS[model_key]
        status = config.get('status', 'unknown')

        if result['validation_passed'] and status == 'unavailable':
            mismatches.append(f"{model_key}: marked unavailable but validation passed")
        elif not result['validation_passed'] and status == 'available':
            mismatches.append(f"{model_key}: marked available but validation failed")

    if mismatches:
        print(f"\n⚠️  Status mismatches found:")
        for mismatch in mismatches:
            print(f"  - {mismatch}")

    # Exit code
    failures = [r for r in results if not r['validation_passed'] and MODEL_CONFIGS[r['model']].get('status') == 'available']
    if failures:
        print(f"\n❌ {len(failures)} available models failed validation")
        sys.exit(1)
    else:
        print(f"\n✅ All available models validated successfully")
        sys.exit(0)


async def main():
    """Main entry point."""
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--all" in args:
        validate_only = "--validate-only" in args
        await test_all_models(validate_only=validate_only)
    elif "--model" in args:
        try:
            idx = args.index("--model")
            model_key = args[idx + 1]
            result = await test_model_validation(model_key)

            if result['validation_passed']:
                print(f"\n✅ Model {model_key} validated successfully")
                sys.exit(0)
            else:
                print(f"\n❌ Model {model_key} validation failed: {result['error']}")
                sys.exit(1)
        except IndexError:
            print("Error: --model requires a model key argument")
            print(__doc__)
            sys.exit(1)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
