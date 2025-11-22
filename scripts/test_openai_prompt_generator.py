#!/usr/bin/env python3
"""
Test script to verify OpenAI API key works for prompt generator.

This script tests:
1. Basic OpenAI API connectivity
2. Prompt generator LLM client functionality
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent
backend_path = project_root / "project" / "backend"
sys.path.insert(0, str(backend_path))

# Change to backend directory so .env file is found
os.chdir(backend_path)

from openai import AsyncOpenAI, APIError, AuthenticationError
from shared.config import settings
from modules.prompt_generator.llm_client import optimize_prompts, _get_client


async def test_basic_openai_connection():
    """Test basic OpenAI API connection with a simple call."""
    print("=" * 60)
    print("Test 1: Basic OpenAI API Connection")
    print("=" * 60)
    
    try:
        # Check if API key is set
        if not settings.openai_api_key:
            print("❌ ERROR: OPENAI_API_KEY is not set in environment")
            return False
        
        print(f"✓ API Key found: {settings.openai_api_key[:10]}...{settings.openai_api_key[-4:]}")
        
        # Create client and make a simple test call
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        print("Making test API call to OpenAI...")
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'API key is working' if you can read this."}
            ],
            max_tokens=50,
            timeout=30.0,
        )
        
        content = response.choices[0].message.content
        print(f"✓ Response received: {content}")
        print(f"✓ Tokens used: {response.usage.prompt_tokens} input, {response.usage.completion_tokens} output")
        print("✅ Basic OpenAI connection test PASSED\n")
        return True
        
    except AuthenticationError as e:
        print(f"❌ AUTHENTICATION ERROR: {e}")
        print("   Your API key is invalid or expired.")
        return False
    except APIError as e:
        print(f"❌ API ERROR: {e}")
        print(f"   Status: {getattr(e, 'status_code', 'unknown')}")
        return False
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_prompt_generator_llm():
    """Test the prompt generator LLM client with sample data."""
    print("=" * 60)
    print("Test 2: Prompt Generator LLM Client")
    print("=" * 60)
    
    try:
        # Create sample base prompts (similar to what the prompt generator receives)
        base_prompts = [
            {
                "clip_index": 0,
                "draft_prompt": "A person walking down a city street at night",
                "duration": 5.0,
                "reference_mode": "text_only"
            },
            {
                "clip_index": 1,
                "draft_prompt": "Close-up of the person's face with neon lights reflecting",
                "duration": 4.5,
                "reference_mode": "text_only"
            }
        ]
        
        style_keywords = ["cyberpunk", "neon", "urban", "cinematic"]
        job_id = uuid4()
        
        print(f"Testing with {len(base_prompts)} sample prompts")
        print(f"Style keywords: {', '.join(style_keywords)}")
        print(f"Job ID: {job_id}")
        print("\nCalling optimize_prompts...")
        
        result = await optimize_prompts(
            job_id=job_id,
            base_prompts=base_prompts,
            style_keywords=style_keywords
        )
        
        print(f"\n✓ Optimization completed!")
        print(f"✓ Model used: {result.model}")
        print(f"✓ Input tokens: {result.input_tokens}")
        print(f"✓ Output tokens: {result.output_tokens}")
        print(f"✓ Generated {len(result.prompts)} prompts\n")
        
        for i, prompt in enumerate(result.prompts):
            print(f"Prompt {i}:")
            print(f"  {prompt[:100]}..." if len(prompt) > 100 else f"  {prompt}")
            print()
        
        print("✅ Prompt generator LLM test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("OpenAI Prompt Generator API Key Test")
    print("=" * 60 + "\n")
    
    # Test 1: Basic connection
    basic_test_passed = await test_basic_openai_connection()
    
    if not basic_test_passed:
        print("\n❌ Basic connection test failed. Skipping prompt generator test.")
        print("   Please check your OPENAI_API_KEY environment variable.")
        sys.exit(1)
    
    # Test 2: Prompt generator (only if basic test passes)
    prompt_test_passed = await test_prompt_generator_llm()
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Basic OpenAI Connection: {'✅ PASSED' if basic_test_passed else '❌ FAILED'}")
    print(f"Prompt Generator LLM: {'✅ PASSED' if prompt_test_passed else '❌ FAILED'}")
    print("=" * 60)
    
    if basic_test_passed and prompt_test_passed:
        print("\n🎉 All tests passed! Your OpenAI API key is working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

