#!/usr/bin/env python3
"""
Performance Benchmark for Config File Caching Optimization

This script runs detailed benchmarks to quantify the performance improvement
from caching system.json, agents.json, and tasks JSON files.

The benchmark measures:
1. Cache miss (first call) - requires filesystem I/O and JSON parsing
2. Cache hit (subsequent calls) - returns cached data from memory

Expected outcome: 2x+ speedup for cached calls
"""

import json
import time
from pathlib import Path
from typing import Any, Callable

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.autoflow import (
    load_system_config,
    load_agents,
    load_tasks,
    invalidate_config_cache,
    SYSTEM_CONFIG_FILE,
    AGENTS_FILE,
    STATE_DIR,
    SPECS_DIR,
)


def benchmark_function(
    func: Callable[[], Any],
    invalidate_func: Callable[[], None],
    name: str,
    iterations: int = 20
) -> dict[str, float]:
    """Benchmark a function to measure cache miss vs cache hit performance.

    Args:
        func: The function to benchmark (should use caching)
        invalidate_func: Function to invalidate the cache
        name: Name of the function being benchmarked
        iterations: Number of iterations for each measurement

    Returns:
        Dictionary with benchmark results:
        - avg_miss_ms: Average time for cache miss (milliseconds)
        - avg_hit_ms: Average time for cache hit (milliseconds)
        - speedup: Speedup factor (avg_miss / avg_hit)
        - time_saved_ms: Time saved per call (milliseconds)
    """
    print(f"\n{'='*70}")
    print(f"Benchmark: {name}")
    print(f"{'='*70}")

    # Measure cache miss (first call, requires filesystem I/O)
    times_miss = []
    for _ in range(iterations):
        invalidate_func()  # Clear cache to force cache miss
        start = time.perf_counter()
        result = func()
        times_miss.append(time.perf_counter() - start)

    # Measure cache hit (subsequent calls, from memory)
    invalidate_func()
    func()  # Populate cache

    times_hit = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func()
        times_hit.append(time.perf_counter() - start)

    # Calculate statistics
    avg_miss = sum(times_miss) / len(times_miss)
    avg_hit = sum(times_hit) / len(times_hit)
    speedup = avg_miss / avg_hit if avg_hit > 0 else float('inf')

    print(f"\nCache Miss (first call, filesystem I/O):")
    print(f"  Average: {avg_miss*1000:.3f} ms")
    print(f"  Min: {min(times_miss)*1000:.3f} ms")
    print(f"  Max: {max(times_miss)*1000:.3f} ms")

    print(f"\nCache Hit (subsequent calls, from memory):")
    print(f"  Average: {avg_hit*1000:.3f} ms")
    print(f"  Min: {min(times_hit)*1000:.3f} ms")
    print(f"  Max: {max(times_hit)*1000:.3f} ms")

    print(f"\n🚀 Speedup: {speedup:.2f}x faster")
    print(f"   Time saved: {((avg_miss - avg_hit)*1000):.3f} ms per call")

    return {
        "name": name,
        "avg_miss_ms": avg_miss * 1000,
        "avg_hit_ms": avg_hit * 1000,
        "speedup": speedup,
        "time_saved_ms": (avg_miss - avg_hit) * 1000,
    }


def verify_config_files_exist() -> None:
    """Verify that required config files exist before benchmarking."""
    print(f"\n{'='*70}")
    print("Verifying Configuration Files")
    print(f"{'='*70}")

    files_to_check = [
        ("System Config", SYSTEM_CONFIG_FILE),
        ("Agents Config", AGENTS_FILE),
    ]

    all_exist = True
    for name, path in files_to_check:
        exists = path.exists()
        status = "✅" if exists else "❌"
        print(f"{status} {name}: {path}")
        if not exists:
            all_exist = False

    if not all_exist:
        print("\n⚠️  Warning: Some config files are missing.")
        print("   Benchmarking will test cache behavior but may not reflect")
        print("   real-world performance with actual config files.\n")
    else:
        print("\n✅ All required config files found.\n")


def main():
    """Run all benchmarks for config caching optimization."""
    print("\n" + "="*70)
    print("CONFIG FILE CACHING - PERFORMANCE BENCHMARK RESULTS")
    print("="*70)

    # Verify config files exist
    verify_config_files_exist()

    results = []

    # Benchmark load_system_config()
    try:
        result = benchmark_function(
            func=load_system_config,
            invalidate_func=invalidate_config_cache,
            name="load_system_config()"
        )
        results.append(result)
    except Exception as e:
        print(f"\n❌ Error benchmarking load_system_config(): {e}")

    # Benchmark load_agents()
    try:
        result = benchmark_function(
            func=load_agents,
            invalidate_func=invalidate_config_cache,
            name="load_agents()"
        )
        results.append(result)
    except Exception as e:
        print(f"\n❌ Error benchmarking load_agents(): {e}")

    # Benchmark load_tasks() - use a test spec if available
    try:
        # Try to find an existing spec for testing
        specs_dir = SPECS_DIR
        test_spec = None

        if specs_dir.exists():
            for spec_dir in specs_dir.iterdir():
                if spec_dir.is_dir():
                    tasks_file = spec_dir / "TASKS.json"
                    if tasks_file.exists():
                        test_spec = spec_dir.name
                        break

        if test_spec:
            result = benchmark_function(
                func=lambda: load_tasks(test_spec),
                invalidate_func=invalidate_config_cache,
                name=f"load_tasks('{test_spec[:30]}...')"  # Truncate long names
            )
            results.append(result)
        else:
            print(f"\n⚠️  Skipping load_tasks() benchmark - no test spec found")
            print(f"   Expected spec directory with TASKS.json in: {specs_dir}")

    except Exception as e:
        print(f"\n❌ Error benchmarking load_tasks(): {e}")

    # Summary
    if results:
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"\n{'Function':<35} {'Cache Miss':<15} {'Cache Hit':<15} {'Speedup':<10}")
        print("-" * 70)
        for r in results:
            name_truncated = r['name'][:35] if len(r['name']) > 35 else r['name']
            print(f"{name_truncated:<35} {r['avg_miss_ms']:<15.3f} {r['avg_hit_ms']:<15.3f} {r['speedup']:<10.2f}x")

        # Verify 2x+ speedup requirement
        print(f"\n{'='*70}")
        print("VERIFICATION RESULTS")
        print(f"{'='*70}")

        all_meet_requirement = True
        for r in results:
            meets_requirement = r['speedup'] >= 2.0
            status = "✅ PASS" if meets_requirement else "❌ FAIL"
            print(f"{status} {r['name']}: {r['speedup']:.2f}x speedup "
                  f"({'meets' if meets_requirement else 'does NOT meet'} 2x requirement)")
            if not meets_requirement:
                all_meet_requirement = False

        print(f"\n{'='*70}")
        if all_meet_requirement:
            print("✅ SUCCESS: All functions meet 2x+ speedup requirement!")
        else:
            print("❌ FAILURE: Some functions do NOT meet 2x speedup requirement")
        print(f"{'='*70}")

        print(f"\nKey Findings:")
        print(f"  • Cache provides significant performance improvement")
        print(f"  • Functions with cached calls are {sum(r['speedup'] for r in results)/len(results):.2f}x faster on average")
        print(f"  • Average time saved per call: {sum(r['time_saved_ms'] for r in results)/len(results):.3f} ms")

        if all_meet_requirement:
            print(f"\n✅ All benchmarks completed successfully!")
        else:
            print(f"\n⚠️  Benchmarks completed but speedup requirement not met")

    else:
        print(f"\n⚠️  No benchmarks were run successfully")


if __name__ == "__main__":
    main()
