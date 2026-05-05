#!/usr/bin/env python3
"""Quick test of LLM provider router."""

import os
import sys
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_router():
    """Test that router initializes correctly."""
    from llm_provider_router import get_router, reset_router

    # Test 1: Router initializes (should work even without API keys)
    print("Test 1: Initializing router...")
    reset_router()
    router = get_router()
    print(f"  Primary provider: {router.primary_provider}")
    print(f"  Anthropic client: {router.anthropic_client}")
    print(f"  Ollama client: {router.ollama_client}")
    print(f"  OpenRouter client: {router.openrouter_client}")
    print("  ✓ Router initialized")

    # Test 2: Router selection logic
    print("\nTest 2: Testing provider selection...")
    client = router._get_client('anthropic')
    print(f"  _get_client('anthropic'): {client}")
    client = router._get_client('ollama')
    print(f"  _get_client('ollama'): {client}")
    client = router._get_client('openrouter')
    print(f"  _get_client('openrouter'): {client}")
    print("  ✓ Provider selection works")

    # Test 3: Simulate environment variable change
    print("\nTest 3: Testing provider switch via env var...")
    os.environ['LLM_PROVIDER'] = 'ollama'
    reset_router()
    router = get_router()
    print(f"  After env change, primary provider: {router.primary_provider}")
    assert router.primary_provider == 'ollama', "Provider should be ollama"
    print("  ✓ Provider switch works")

    print("\n✅ All tests passed!")

if __name__ == '__main__':
    asyncio.run(test_router())
