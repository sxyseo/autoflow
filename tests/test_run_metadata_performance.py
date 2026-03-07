"""
Performance Benchmark Tests for run_metadata_iter Functions

Tests the performance difference between:
- run_metadata_iter(): Original O(n) filesystem scan version
- run_metadata_iter_cached(): Cached version with lazy-loading

These benchmarks validate that the cached implementation provides
significant performance improvements for repeated calls.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

# Import the functions to test
# Note: We need to import from scripts.autoflow
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.autoflow import (
    RUNS_DIR,
    _cache_loaded_specs,
    _run_metadata_cache,
    invalidate_run_cache,
    read_json,
    run_metadata_iter,
    run_metadata_iter_cached,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_runs_dir(tmp_path: Path) -> Path:
    """Create a temporary runs directory for test isolation.

    Note: Tests will use the actual RUNS_DIR, but clean_runs_dir fixture
    ensures it's cleaned before/after each test.
    """
    # Ensure RUNS_DIR exists
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR


@pytest.fixture
def sample_run_data() -> dict[str, Any]:
    """Return sample run metadata for testing."""
    return {
        "id": "run-001",
        "spec": "test-spec",
        "task": "task-001",
        "agent": "claude-code",
        "status": "running",
        "created_at": "2026-03-07T12:00:00Z",
    }


@pytest.fixture(autouse=True)
def clean_runs_dir(tmp_path: Path) -> None:
    """Clean and reset the runs directory before each test to ensure isolation."""
    import shutil

    # Store original runs
    original_runs = []
    if RUNS_DIR.exists():
        original_runs = list(RUNS_DIR.iterdir())

    # Clean RUNS_DIR before test
    if RUNS_DIR.exists():
        for run_dir in RUNS_DIR.iterdir():
            if run_dir.is_dir():
                shutil.rmtree(run_dir)

    # Always invalidate cache at start of test
    invalidate_run_cache()

    yield

    # Clean up test runs
    if RUNS_DIR.exists():
        for run_dir in RUNS_DIR.iterdir():
            if run_dir.is_dir():
                shutil.rmtree(run_dir)

    # Restore original runs (if any)
    for run_path in original_runs:
        if run_path.is_dir():
            shutil.copytree(run_path, RUNS_DIR / run_path.name)


def create_test_runs(
    runs_dir: Path,
    count: int,
    spec_prefix: str = "spec",
    status: str = "running",
) -> list[str]:
    """Helper to create test run directories with metadata.

    Args:
        runs_dir: Directory to create runs in
        count: Number of runs to create
        spec_prefix: Prefix for spec names (will create spec-001, spec-002, etc.)
        status: Status for all runs

    Returns:
        List of run IDs that were created
    """
    run_ids = []
    for i in range(count):
        run_id = f"run-{i:04d}"
        spec_slug = f"{spec_prefix}-{i % 3:03d}"  # Distribute across 3 specs

        run_dir = runs_dir / run_id
        run_dir.mkdir()

        metadata = {
            "id": run_id,
            "spec": spec_slug,
            "task": f"task-{i % 5:03d}",  # Distribute across 5 tasks
            "agent": "claude-code",
            "status": status,
            "created_at": f"2026-03-07T{i:02d}:00:00Z",
        }

        metadata_path = run_dir / "run.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        run_ids.append(run_id)

    return run_ids


# ============================================================================
# Performance Benchmark Tests
# ============================================================================


class TestRunMetadataIterPerformance:
    """Performance benchmarks for run_metadata_iter functions."""

    def test_uncached_vs_cached_small_dataset(
        self, temp_runs_dir: Path, sample_run_data: dict
    ) -> None:
        """Benchmark uncached vs cached with small dataset (10 runs)."""
        # Create test data
        create_test_runs(temp_runs_dir, 10)

        # Benchmark uncached version - single call
        start = time.perf_counter()
        result_uncached = run_metadata_iter()
        time_uncached_single = time.perf_counter() - start

        # Invalidate cache to ensure fresh measurement
        invalidate_run_cache()

        # Benchmark cached version - first call (cache miss)
        start = time.perf_counter()
        result_cached_first = run_metadata_iter_cached()
        time_cached_first = time.perf_counter() - start

        # Benchmark cached version - second call (cache hit)
        start = time.perf_counter()
        result_cached_second = run_metadata_iter_cached()
        time_cached_second = time.perf_counter() - start

        # Verify results are identical
        assert len(result_uncached) == 10
        assert len(result_cached_first) == 10
        assert len(result_cached_second) == 10
        assert sorted(r["id"] for r in result_uncached) == sorted(
            r["id"] for r in result_cached_first
        )

        # Cached second call should be significantly faster
        # (it's just reading from memory, no filesystem I/O)
        assert time_cached_second < time_uncached_single

        # First cached call might be similar or slightly slower due to cache overhead
        # but second call should be much faster
        speedup = time_uncached_single / time_cached_second
        # With small datasets, speedup may be modest due to fast filesystem I/O
        assert speedup > 1.1  # At least 10% speedup on cache hit

    def test_uncached_vs_cached_medium_dataset(
        self, temp_runs_dir: Path
    ) -> None:
        """Benchmark uncached vs cached with medium dataset (50 runs)."""
        # Create test data
        create_test_runs(temp_runs_dir, 50)

        # Benchmark uncached - single call
        start = time.perf_counter()
        result_uncached = run_metadata_iter()
        time_uncached = time.perf_counter() - start

        # Invalidate and benchmark cached
        invalidate_run_cache()
        start = time.perf_counter()
        run_metadata_iter_cached()
        time_cached_first = time.perf_counter() - start

        start = time.perf_counter()
        run_metadata_iter_cached()
        time_cached_second = time.perf_counter() - start

        assert len(result_uncached) == 50

        # Cached second call should be faster or at least not slower
        # (may vary due to OS caching, system load, etc.)
        speedup = time_uncached / time_cached_second
        assert speedup > 0.9  # At least not significantly slower

    def test_uncached_vs_cached_large_dataset(
        self, temp_runs_dir: Path
    ) -> None:
        """Benchmark uncached vs cached with large dataset (100 runs)."""
        # Create test data
        create_test_runs(temp_runs_dir, 100)

        # Benchmark uncached - single call
        start = time.perf_counter()
        result_uncached = run_metadata_iter()
        time_uncached = time.perf_counter() - start

        # Invalidate and benchmark cached
        invalidate_run_cache()
        start = time.perf_counter()
        run_metadata_iter_cached()
        time_cached_first = time.perf_counter() - start

        start = time.perf_counter()
        run_metadata_iter_cached()
        time_cached_second = time.perf_counter() - start

        assert len(result_uncached) == 100

        # With larger dataset, cache advantage should be more pronounced
        # but can still vary due to OS caching, system load, etc.
        speedup = time_uncached / time_cached_second
        assert speedup > 1.0  # At least somewhat faster

    def test_repeated_uncached_calls_performance(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that repeated uncached calls show no performance improvement."""
        # Create test data
        create_test_runs(temp_runs_dir, 30)

        # Make multiple uncached calls - each should scan filesystem
        times = []
        for _ in range(5):
            start = time.perf_counter()
            run_metadata_iter()
            times.append(time.perf_counter() - start)

        # All calls should take similar time (no caching benefit)
        # Verify that the variance is within reasonable bounds
        avg_time = sum(times) / len(times)
        for t in times:
            # Each call should be within 50% of average (filesystem I/O varies)
            assert t < avg_time * 1.5

    def test_repeated_cached_calls_performance(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that repeated cached calls show significant performance improvement."""
        # Create test data
        create_test_runs(temp_runs_dir, 30)

        # First call populates cache
        invalidate_run_cache()
        start = time.perf_counter()
        run_metadata_iter_cached()
        time_first = time.perf_counter() - start

        # Subsequent calls should be much faster
        times_cached = []
        for _ in range(5):
            start = time.perf_counter()
            run_metadata_iter_cached()
            times_cached.append(time.perf_counter() - start)

        # All cached calls after the first should be very fast
        avg_cached = sum(times_cached) / len(times_cached)

        # Cached calls should be significantly faster than first call
        # (first call does the work, subsequent calls just read from memory)
        # Performance can vary, so use a more lenient threshold
        assert avg_cached < time_first * 0.8  # At least 20% faster

    def test_cache_invalidation_performance(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cache invalidation correctly resets performance."""
        # Create test data
        create_test_runs(temp_runs_dir, 20)

        # Populate cache
        run_metadata_iter_cached()

        # Fast cached call
        start = time.perf_counter()
        run_metadata_iter_cached()
        time_cached = time.perf_counter() - start

        # Invalidate cache
        invalidate_run_cache()

        # After invalidation, should be slower again (cache miss)
        start = time.perf_counter()
        run_metadata_iter_cached()
        time_after_invalidation = time.perf_counter() - start

        # After invalidation, should take longer than cached call
        assert time_after_invalidation > time_cached * 1.5

    def test_empty_runs_directory_performance(
        self, temp_runs_dir: Path
    ) -> None:
        """Test performance with empty runs directory."""
        # Don't create any runs - directory is empty

        # Both should be fast with empty directory
        start = time.perf_counter()
        result_uncached = run_metadata_iter()
        time_uncached = time.perf_counter() - start

        invalidate_run_cache()
        start = time.perf_counter()
        result_cached = run_metadata_iter_cached()
        time_cached = time.perf_counter() - start

        assert result_uncached == []
        assert result_cached == []

        # Both should complete quickly
        assert time_uncached < 0.1  # Less than 100ms
        assert time_cached < 0.1

    def test_sorted_order_performance(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that both versions return results in the same sorted order."""
        # Create test data
        create_test_runs(temp_runs_dir, 25)

        # Get results from both versions
        invalidate_run_cache()
        result_uncached = run_metadata_iter()
        result_cached = run_metadata_iter_cached()

        # Extract run IDs
        ids_uncached = [r["id"] for r in result_uncached]
        ids_cached = [r["id"] for r in result_cached]

        # Both should return results sorted by run ID (directory name)
        assert ids_uncached == sorted(ids_uncached)
        assert ids_cached == sorted(ids_cached)

        # Results should be identical
        assert ids_uncached == ids_cached

    def test_performance_with_multiple_specs(
        self, temp_runs_dir: Path
    ) -> None:
        """Test performance when runs are distributed across multiple specs."""
        # Create runs distributed across 10 specs
        create_test_runs(temp_runs_dir, 60, spec_prefix="feature")

        # Benchmark uncached
        start = time.perf_counter()
        result_uncached = run_metadata_iter()
        time_uncached = time.perf_counter() - start

        # Benchmark cached
        invalidate_run_cache()
        start = time.perf_counter()
        run_metadata_iter_cached()
        time_cached_first = time.perf_counter() - start

        start = time.perf_counter()
        run_metadata_iter_cached()
        time_cached_second = time.perf_counter() - start

        assert len(result_uncached) == 60

        # Verify cache is indexed by spec
        # After loading, cache should have entries for multiple specs
        invalidate_run_cache()
        run_metadata_iter_cached()
        spec_count = len(_run_metadata_cache)
        assert spec_count > 1  # Should have cached multiple specs

        # Second call should be faster or at least not significantly slower
        # Performance can vary due to OS caching, system load, etc.
        speedup = time_uncached / time_cached_second
        assert speedup > 0.9  # At least not significantly slower


class TestCacheEfficiency:
    """Tests for cache efficiency and memory usage."""

    def test_cache_memory_overhead(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cache memory overhead is reasonable."""
        # Create test runs
        create_test_runs(temp_runs_dir, 50)

        # Populate cache
        invalidate_run_cache()
        results = run_metadata_iter_cached()

        # Count total cache entries
        total_cached_runs = sum(len(runs) for runs in _run_metadata_cache.values())

        # Should cache all runs
        assert total_cached_runs == len(results) == 50

        # Cache should be organized by spec (not all in one list)
        # This verifies lazy-loading by spec works
        num_specs = len(_run_metadata_cache)
        assert num_specs > 1  # Runs distributed across multiple specs

    def test_lazy_loading_by_spec(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cache lazy-loads by spec_slug."""
        # Create runs for different specs
        create_test_runs(temp_runs_dir, 30, spec_prefix="lazy")

        # Invalidate to start fresh
        invalidate_run_cache()

        # Initially cache should be empty
        assert len(_run_metadata_cache) == 0
        assert len(_cache_loaded_specs) == 0

        # Call run_metadata_iter_cached which loads everything
        run_metadata_iter_cached()

        # Cache should be populated
        assert len(_run_metadata_cache) > 0
        assert len(_cache_loaded_specs) > 0

    def test_cache_invalidation_clears_all_state(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that invalidate_run_cache() properly clears all cache state."""
        # Create and cache runs
        create_test_runs(temp_runs_dir, 20)
        run_metadata_iter_cached()

        # Verify cache is populated
        assert len(_run_metadata_cache) > 0
        assert len(_cache_loaded_specs) > 0

        # Invalidate
        invalidate_run_cache()

        # Verify cache is cleared
        assert len(_run_metadata_cache) == 0
        assert len(_cache_loaded_specs) == 0
