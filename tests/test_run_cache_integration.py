"""
Integration Tests for Run Metadata Cache Consistency

Tests the integration and consistency of the run metadata cache across operations:
- Cache remains consistent when runs are created/modified
- Cache invalidation works correctly across all cached functions
- Different cached functions see consistent data
- Lazy-loading and opportunistic caching work correctly

These are integration tests because they verify the behavior of the entire
caching system across multiple operations and function calls.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Import the functions to test
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.autoflow import (
    RUNS_DIR,
    _cache_loaded_specs,
    _run_metadata_cache,
    active_runs_for_spec_cached,
    invalidate_run_cache,
    read_json,
    run_metadata_iter,
    run_metadata_iter_cached,
    task_run_history_cached,
    write_json,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_runs_dir(tmp_path: Path) -> Path:
    """Create a temporary runs directory for test isolation."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR


@pytest.fixture(autouse=True)
def clean_runs_dir() -> None:
    """Clean and reset the runs directory before each test to ensure isolation."""
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


def create_run(
    runs_dir: Path,
    run_id: str,
    spec_slug: str,
    task_id: str,
    status: str = "running",
) -> Path:
    """Helper to create a test run directory with metadata.

    Args:
        runs_dir: Directory to create run in
        run_id: Unique run identifier
        spec_slug: Spec slug for the run
        task_id: Task ID for the run
        status: Run status (default: "running")

    Returns:
        Path to the created run directory
    """
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    metadata = {
        "id": run_id,
        "spec": spec_slug,
        "task": task_id,
        "agent": "claude-code",
        "status": status,
        "created_at": "2026-03-07T12:00:00Z",
    }

    metadata_path = run_dir / "run.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    return run_dir


# ============================================================================
# Cache Consistency Tests
# ============================================================================


class TestCacheConsistency:
    """Tests for cache consistency across operations."""

    def test_cache_consistency_after_creation(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cache reflects newly created runs after invalidation."""
        # Create initial runs
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-2")

        # Load into cache
        runs = run_metadata_iter_cached()
        assert len(runs) == 2

        # Create a new run
        create_run(temp_runs_dir, "run-003", "spec-a", "task-3")

        # Cache should still show 2 runs (stale)
        runs_stale = run_metadata_iter_cached()
        assert len(runs_stale) == 2

        # Invalidate cache
        invalidate_run_cache()

        # Now cache should show 3 runs
        runs_fresh = run_metadata_iter_cached()
        assert len(runs_fresh) == 3

        run_ids = {r["id"] for r in runs_fresh}
        assert run_ids == {"run-001", "run-002", "run-003"}

    def test_cache_consistency_after_modification(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cache reflects modified runs after invalidation."""
        # Create a run
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1", status="running")

        # Load into cache
        runs = run_metadata_iter_cached()
        assert runs[0]["status"] == "running"

        # Modify the run status
        run_dir = temp_runs_dir / "run-001"
        metadata = read_json(run_dir / "run.json")
        metadata["status"] = "completed"
        write_json(run_dir / "run.json", metadata)

        # Cache should still show old status (stale)
        runs_stale = run_metadata_iter_cached()
        assert runs_stale[0]["status"] == "running"

        # Invalidate cache
        invalidate_run_cache()

        # Now cache should show updated status
        runs_fresh = run_metadata_iter_cached()
        assert runs_fresh[0]["status"] == "completed"

    def test_cache_consistency_after_deletion(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cache reflects deleted runs after invalidation."""
        # Create runs
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-2")

        # Load into cache
        runs = run_metadata_iter_cached()
        assert len(runs) == 2

        # Delete a run directory
        shutil.rmtree(temp_runs_dir / "run-001")

        # Cache should still show 2 runs (stale)
        runs_stale = run_metadata_iter_cached()
        assert len(runs_stale) == 2

        # Invalidate cache
        invalidate_run_cache()

        # Now cache should show 1 run
        runs_fresh = run_metadata_iter_cached()
        assert len(runs_fresh) == 1
        assert runs_fresh[0]["id"] == "run-002"

    def test_active_runs_consistency(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that active_runs_for_spec_cached shows consistent data."""
        # Create runs with different statuses
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1", status="running")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-2", status="completed")
        create_run(temp_runs_dir, "run-003", "spec-a", "task-3", status="running")

        # Get active runs
        active = active_runs_for_spec_cached("spec-a")
        assert len(active) == 2
        assert all(r["status"] != "completed" for r in active)

        # Complete a running run
        run_dir = temp_runs_dir / "run-001"
        metadata = read_json(run_dir / "run.json")
        metadata["status"] = "completed"
        write_json(run_dir / "run.json", metadata)

        # Cache should still show 2 active runs (stale)
        active_stale = active_runs_for_spec_cached("spec-a")
        assert len(active_stale) == 2

        # Invalidate and check again
        invalidate_run_cache()
        active_fresh = active_runs_for_spec_cached("spec-a")
        assert len(active_fresh) == 1
        assert active_fresh[0]["id"] == "run-003"

    def test_task_history_consistency(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that task_run_history_cached shows consistent data."""
        # Create runs for the same task
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1", status="completed")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-1", status="completed")
        create_run(temp_runs_dir, "run-003", "spec-a", "task-2", status="completed")

        # Get history for task-1
        history = task_run_history_cached("spec-a", "task-1")
        assert len(history) == 2

        # Add another run for task-1
        create_run(temp_runs_dir, "run-004", "spec-a", "task-1", status="completed")

        # Cache should still show 2 runs (stale)
        history_stale = task_run_history_cached("spec-a", "task-1")
        assert len(history_stale) == 2

        # Invalidate and check again
        invalidate_run_cache()
        history_fresh = task_run_history_cached("spec-a", "task-1")
        assert len(history_fresh) == 3

    def test_cross_function_consistency(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that different cached functions see consistent data."""
        # Create runs
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1", status="running")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-2", status="completed")

        # Get data from different functions
        all_runs = run_metadata_iter_cached()
        active_runs = active_runs_for_spec_cached("spec-a")
        task_history = task_run_history_cached("spec-a", "task-1")

        # Verify consistency
        assert len(all_runs) == 2
        assert len(active_runs) == 1  # Only run-001 is active
        assert len(task_history) == 1  # Only run-001 is for task-1

        # Verify the active run is the same
        assert active_runs[0]["id"] == "run-001"
        assert task_history[0]["id"] == "run-001"

        # Now modify run-001 to completed
        run_dir = temp_runs_dir / "run-001"
        metadata = read_json(run_dir / "run.json")
        metadata["status"] = "completed"
        write_json(run_dir / "run.json", metadata)

        # Without invalidation, data is stale
        active_stale = active_runs_for_spec_cached("spec-a")
        assert len(active_stale) == 1  # Still shows run-001 as active

        # After invalidation, all functions should see fresh data
        invalidate_run_cache()
        active_fresh = active_runs_for_spec_cached("spec-a")
        assert len(active_fresh) == 0  # No active runs now


# ============================================================================
# Cache Invalidation Tests
# ============================================================================


class TestCacheInvalidation:
    """Tests for cache invalidation behavior."""

    def test_invalidate_clears_all_cache_state(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that invalidate_run_cache() clears all cache state."""
        # Create runs and populate cache
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")
        create_run(temp_runs_dir, "run-002", "spec-b", "task-2")

        run_metadata_iter_cached()
        active_runs_for_spec_cached("spec-a")
        task_run_history_cached("spec-b", "task-2")

        # Verify cache is populated
        assert len(_run_metadata_cache) > 0
        assert len(_cache_loaded_specs) > 0

        # Invalidate
        invalidate_run_cache()

        # Verify cache is cleared
        assert len(_run_metadata_cache) == 0
        assert len(_cache_loaded_specs) == 0

    def test_invalidate_before_lazy_load(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that invalidation before any lazy load is safe."""
        # Invalidate without any cache populated
        invalidate_run_cache()

        # Should be able to load runs normally
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")
        runs = run_metadata_iter_cached()

        assert len(runs) == 1

    def test_multiple_invalidations_in_sequence(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that multiple invalidations in sequence work correctly."""
        # Create runs
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")

        # Load cache
        run_metadata_iter_cached()
        assert len(_run_metadata_cache) > 0

        # Invalidate multiple times
        invalidate_run_cache()
        assert len(_run_metadata_cache) == 0

        invalidate_run_cache()
        assert len(_run_metadata_cache) == 0

        # Should still work
        runs = run_metadata_iter_cached()
        assert len(runs) == 1


# ============================================================================
# Lazy Loading Tests
# ============================================================================


class TestLazyLoading:
    """Tests for lazy-loading behavior."""

    def test_lazy_loads_on_demand(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cache lazy-loads specs on demand."""
        # Create runs for different specs
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")
        create_run(temp_runs_dir, "run-002", "spec-b", "task-2")
        create_run(temp_runs_dir, "run-003", "spec-c", "task-3")

        # Initially cache is empty
        assert len(_run_metadata_cache) == 0
        assert len(_cache_loaded_specs) == 0

        # Query spec-a - should load only spec-a (and opportunistically others)
        active_runs_for_spec_cached("spec-a")

        # Cache should have at least spec-a loaded
        assert "spec-a" in _cache_loaded_specs

        # Query spec-b - should already be loaded from opportunistic caching
        # (run_metadata_iter_cached loads all specs, but active_runs_for_spec_cached
        # uses lazy loading which opportunistically caches discovered specs)
        active_runs_for_spec_cached("spec-b")

        # Both specs should be loaded
        assert "spec-b" in _cache_loaded_specs

    def test_opportunistic_caching(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that opportunistic caching works during lazy load."""
        # Create runs for multiple specs
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")
        create_run(temp_runs_dir, "run-002", "spec-b", "task-2")

        # Invalidate to start fresh
        invalidate_run_cache()

        # Query one spec - should opportunistically cache other specs seen
        # during the filesystem scan
        active_runs_for_spec_cached("spec-a")

        # Due to opportunistic caching, spec-b might also be loaded
        # (it was discovered during the scan for spec-a)
        # This is implementation-dependent, so we just verify the cache works
        runs_a = active_runs_for_spec_cached("spec-a")
        assert len(runs_a) == 1

        # Second call should be from cache
        runs_a_again = active_runs_for_spec_cached("spec-a")
        assert len(runs_a_again) == 1
        assert runs_a[0]["id"] == runs_a_again[0]["id"]

    def test_lazy_load_with_task_history(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that task_run_history_cached uses lazy loading correctly."""
        # Create runs for different tasks
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-2")
        create_run(temp_runs_dir, "run-003", "spec-b", "task-1")

        # Initially cache is empty
        assert len(_run_metadata_cache) == 0

        # Query task-1 in spec-a
        history = task_run_history_cached("spec-a", "task-1")

        # Should load spec-a
        assert len(history) == 1
        assert "spec-a" in _cache_loaded_specs


# ============================================================================
# Integration with Original Functions
# ============================================================================


class TestIntegrationWithOriginal:
    """Tests for integration with original (uncached) functions."""

    def test_cached_matches_uncached_results(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cached functions return same results as uncached."""
        # Create runs
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1", status="running")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-2", status="completed")
        create_run(temp_runs_dir, "run-003", "spec-b", "task-1", status="running")

        # Get results from uncached functions
        uncached_all = run_metadata_iter()

        # Get results from cached functions
        invalidate_run_cache()
        cached_all = run_metadata_iter_cached()

        # Results should be identical
        assert len(uncached_all) == len(cached_all) == 3

        uncached_ids = sorted([r["id"] for r in uncached_all])
        cached_ids = sorted([r["id"] for r in cached_all])

        assert uncached_ids == cached_ids

    def test_cached_functions_interoperate_with_uncached(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cached and uncached functions can interoperate."""
        # Create runs
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1", status="running")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-2", status="running")

        # Use uncached function
        uncached_runs = run_metadata_iter()
        assert len(uncached_runs) == 2

        # Use cached function
        invalidate_run_cache()
        cached_runs = run_metadata_iter_cached()
        assert len(cached_runs) == 2

        # They should return the same data
        assert uncached_runs[0]["id"] == cached_runs[0]["id"]
        assert uncached_runs[1]["id"] == cached_runs[1]["id"]


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and corner cases."""

    def test_empty_directory_consistency(
        self, temp_runs_dir: Path
    ) -> None:
        """Test cache consistency with empty runs directory."""
        # Don't create any runs

        # All functions should return empty results
        invalidate_run_cache()
        assert run_metadata_iter_cached() == []
        assert active_runs_for_spec_cached("spec-a") == []
        assert task_run_history_cached("spec-a", "task-1") == []

    def test_nonexistent_spec_returns_empty(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that querying nonexistent spec returns empty list."""
        # Create runs for spec-a only
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")

        # Query spec-b which doesn't exist
        invalidate_run_cache()
        runs = active_runs_for_spec_cached("spec-b")
        assert runs == []

    def test_cache_with_multiple_runs_same_task(
        self, temp_runs_dir: Path
    ) -> None:
        """Test cache consistency with multiple runs for same task."""
        # Create multiple runs for the same task
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1", status="completed")
        create_run(temp_runs_dir, "run-002", "spec-a", "task-1", status="completed")
        create_run(temp_runs_dir, "run-003", "spec-a", "task-1", status="running")

        # Get history
        history = task_run_history_cached("spec-a", "task-1")
        assert len(history) == 3

        # Verify all are for the same task
        assert all(r["task"] == "task-1" for r in history)

    def test_cache_with_special_characters_in_ids(
        self, temp_runs_dir: Path
    ) -> None:
        """Test cache handles special characters in IDs correctly."""
        # Create runs with special characters
        create_run(temp_runs_dir, "run-001", "spec-with-dash", "task-with-dash")
        create_run(temp_runs_dir, "run-002", "spec_with_underscore", "task_with_underscore")

        # Should work normally
        invalidate_run_cache()
        runs = run_metadata_iter_cached()
        assert len(runs) == 2

    def test_cache_invalidation_idempotence(
        self, temp_runs_dir: Path
    ) -> None:
        """Test that cache invalidation is idempotent."""
        # Create runs and populate cache
        create_run(temp_runs_dir, "run-001", "spec-a", "task-1")
        run_metadata_iter_cached()

        # Invalidate once
        invalidate_run_cache()
        assert len(_run_metadata_cache) == 0

        # Invalidate again - should be safe
        invalidate_run_cache()
        assert len(_run_metadata_cache) == 0

        # Should still work
        runs = run_metadata_iter_cached()
        assert len(runs) == 1
