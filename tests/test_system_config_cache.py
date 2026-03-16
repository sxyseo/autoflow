#!/usr/bin/env python3
"""
Test script to verify system config caching behavior.

This script verifies that load_system_config() uses caching by:
1. Calling load_system_config() twice
2. Verifying both calls return the same object (identity check with 'is' operator)
3. Confirming cache hit on second call

Usage:
    python tests/test_system_config_cache.py
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autoflow.core.config import load_config
from autoflow.autoflow_cli import AutoflowCLI, invalidate_system_config_cache


def test_system_config_caching():
    """Test that load_system_config() uses caching correctly."""
    print("Testing system config caching...")

    # Ensure we start with a clean cache
    invalidate_system_config_cache()

    # Initialize CLI
    config = load_config()
    cli = AutoflowCLI(config)

    # First call - should load from disk and cache
    print("  First call (cache miss - loads from disk)...")
    config1 = cli.load_system_config()
    print(f"    Config keys: {list(config1.keys())}")
    print(f"    Config type: {type(config1)}")

    # Second call - should return cached value
    print("  Second call (cache hit - returns cached)...")
    config2 = cli.load_system_config()
    print(f"    Config type: {type(config2)}")

    # Identity check - both should be the same object
    print("\n  Identity check (config1 is config2):")
    is_same_object = config1 is config2
    print(f"    Result: {is_same_object}")

    if is_same_object:
        print("\n✅ PASS: Cache is working correctly!")
        print("   Both calls returned the same object (identity check passed)")
        return True
    else:
        print("\n❌ FAIL: Cache is NOT working!")
        print("   The two calls returned different objects")
        print(f"   config1 id: {id(config1)}")
        print(f"   config2 id: {id(config2)}")
        return False


def test_cache_invalidation():
    """Test that cache invalidation works correctly."""
    print("\nTesting cache invalidation...")

    # Initialize CLI
    config_obj = load_config()
    cli = AutoflowCLI(config_obj)

    # Load config (cache it)
    print("  Loading config...")
    config1 = cli.load_system_config()
    id1 = id(config1)
    print(f"    Config id: {id1}")

    # Invalidate cache
    print("  Invalidating cache...")
    invalidate_system_config_cache()

    # Load config again (should load from disk, get new object)
    print("  Loading config after invalidation...")
    config2 = cli.load_system_config()
    id2 = id(config2)
    print(f"    Config id: {id2}")

    # Check if different objects
    print("\n  Identity check (config1 is NOT config2):")
    is_different_object = config1 is not config2
    print(f"    Result: {is_different_object}")

    if is_different_object:
        print("\n✅ PASS: Cache invalidation is working correctly!")
        print("   After invalidation, a new object was created")
        return True
    else:
        print("\n❌ FAIL: Cache invalidation is NOT working!")
        print("   The object is the same even after invalidation")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("System Config Cache Test")
    print("=" * 70)

    test1_passed = test_system_config_caching()
    test2_passed = test_cache_invalidation()

    print("\n" + "=" * 70)
    print("Test Summary:")
    print("=" * 70)
    print(f"  Caching Test:         {'PASS ✅' if test1_passed else 'FAIL ❌'}")
    print(f"  Invalidation Test:    {'PASS ✅' if test2_passed else 'FAIL ❌'}")
    print("=" * 70)

    # Exit with appropriate code
    if test1_passed and test2_passed:
        print("\nAll tests passed! 🎉")
        sys.exit(0)
    else:
        print("\nSome tests failed! 😞")
        sys.exit(1)
