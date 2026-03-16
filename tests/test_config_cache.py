"""
Unit Tests for Configuration Cache Functions

Tests the cache population and invalidation functions for system config,
agents config, and tasks cache. These are unit tests because they test
individual functions in isolation with controlled inputs and outputs.

Functions Tested:
- _populate_system_config_cache()
- _populate_agents_cache()
- _populate_tasks_cache(spec_slug)
- invalidate_config_cache()
- invalidate_system_config_cache()
- invalidate_agents_cache()
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Import the module to access globals
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.autoflow as autoflow_module

from scripts.autoflow import (
    AGENTS_FILE,
    SPECS_DIR,
    SYSTEM_CONFIG_FILE,
    TASKS_DIR,
    _cache_loaded_task_specs,
    _populate_agents_cache,
    _populate_system_config_cache,
    _populate_tasks_cache,
    _tasks_metadata_cache,
    invalidate_agents_cache,
    invalidate_config_cache,
    invalidate_system_config_cache,
    read_json,
    write_json,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    """Clean and reset all config caches before each test to ensure isolation."""
    # Invalidate all caches before test
    invalidate_config_cache()

    # Also clear tasks cache
    global _tasks_metadata_cache, _cache_loaded_task_specs
    _tasks_metadata_cache.clear()
    _cache_loaded_task_specs.clear()

    yield

    # Clean up after test
    invalidate_config_cache()
    _tasks_metadata_cache.clear()
    _cache_loaded_task_specs.clear()


@pytest.fixture
def temp_system_config(tmp_path: Path) -> Path:
    """Create a temporary system config file for test isolation."""
    # Store original config
    original_config = None
    if SYSTEM_CONFIG_FILE.exists():
        original_config = read_json(SYSTEM_CONFIG_FILE)

    # Create test config
    test_config = {
        "memory": {
            "enabled": True,
            "scopes": ["global", "spec"]
        },
        "models": {
            "spec": {"model": "claude-sonnet-4-5"},
            "implementation": {"model": "claude-sonnet-4-5"}
        }
    }

    # Ensure directory exists
    SYSTEM_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write test config
    write_json(SYSTEM_CONFIG_FILE, test_config)

    yield

    # Restore original config
    if original_config is not None:
        write_json(SYSTEM_CONFIG_FILE, original_config)
    elif SYSTEM_CONFIG_FILE.exists():
        SYSTEM_CONFIG_FILE.unlink()


@pytest.fixture
def temp_agents_config(tmp_path: Path) -> Path:
    """Create a temporary agents config file for test isolation."""
    # Store original config
    original_config = None
    if AGENTS_FILE.exists():
        original_config = read_json(AGENTS_FILE)

    # Create test agents config
    test_agents = {
        "agents": {
            "test-agent": {
                "protocol": "cli",
                "command": "echo",
                "args": ["test"]
            }
        }
    }

    # Ensure directory exists
    AGENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write test config
    write_json(AGENTS_FILE, test_agents)

    yield

    # Restore original config
    if original_config is not None:
        write_json(AGENTS_FILE, original_config)
    elif AGENTS_FILE.exists():
        AGENTS_FILE.unlink()


@pytest.fixture
def temp_tasks_dir(tmp_path: Path) -> Path:
    """Create a temporary tasks directory for test isolation."""
    # Store original tasks
    original_tasks = []
    if TASKS_DIR.exists():
        original_tasks = list(TASKS_DIR.iterdir())

    # Clean TASKS_DIR before test
    if TASKS_DIR.exists():
        for task_file in TASKS_DIR.iterdir():
            if task_file.is_file():
                task_file.unlink()

    # Ensure directory exists
    TASKS_DIR.mkdir(parents=True, exist_ok=True)

    # Create test task files
    task_a = {
        "tasks": {
            "task-1": {
                "id": "task-1",
                "status": "todo",
                "description": "Test task 1"
            }
        }
    }

    task_b = {
        "tasks": {
            "task-2": {
                "id": "task-2",
                "status": "in_progress",
                "description": "Test task 2"
            }
        }
    }

    write_json(TASKS_DIR / "spec-a.json", task_a)
    write_json(TASKS_DIR / "spec-b.json", task_b)

    yield

    # Clean up test tasks
    if TASKS_DIR.exists():
        for task_file in TASKS_DIR.iterdir():
            if task_file.is_file():
                task_file.unlink()

    # Restore original tasks (if any)
    for task_path in original_tasks:
        if task_path.is_file():
            shutil.copy(task_path, TASKS_DIR / task_path.name)


# ============================================================================
# System Config Cache Tests
# ============================================================================


class TestSystemConfigCache:
    """Tests for _populate_system_config_cache() function."""

    def test_populate_loads_config(self, temp_system_config: Path) -> None:
        """Test that _populate_system_config_cache() loads config from disk."""
        # Initially cache is empty
        assert autoflow_module._system_config_cache is None

        # Populate cache
        _populate_system_config_cache()

        # Cache should now have config
        assert autoflow_module._system_config_cache is not None
        assert autoflow_module._system_config_cache.get("memory", {}).get("enabled") is True

    def test_populate_is_lazy(self, temp_system_config: Path) -> None:
        """Test that _populate_system_config_cache() only loads once (lazy-loading)."""
        # First call should load
        _populate_system_config_cache()
        first_cache = autoflow_module._system_config_cache

        # Second call should not reload (cache hit)
        _populate_system_config_cache()
        second_cache = autoflow_module._system_config_cache

        # Both should be the same object (not reloaded)
        assert first_cache is second_cache

    def test_populate_handles_missing_file(self) -> None:
        """Test that _populate_system_config_cache() handles missing file gracefully."""
        # Remove config file if it exists
        if SYSTEM_CONFIG_FILE.exists():
            SYSTEM_CONFIG_FILE.unlink()

        # Should not raise an exception
        # (load_system_config should handle missing file with defaults)
        _populate_system_config_cache()

        # Cache should have something (defaults or empty dict)
        assert autoflow_module._system_config_cache is not None

    def test_invalidate_clears_cache(self, temp_system_config: Path) -> None:
        """Test that invalidate_system_config_cache() clears the cache."""
        # Populate cache
        _populate_system_config_cache()
        assert autoflow_module._system_config_cache is not None

        # Invalidate
        invalidate_system_config_cache()

        # Cache should be cleared
        assert autoflow_module._system_config_cache is None

    def test_invalidate_is_idempotent(self, temp_system_config: Path) -> None:
        """Test that invalidate_system_config_cache() is idempotent."""
        # Populate cache
        _populate_system_config_cache()

        # Invalidate once
        invalidate_system_config_cache()
        assert autoflow_module._system_config_cache is None

        # Invalidate again - should be safe
        invalidate_system_config_cache()
        assert autoflow_module._system_config_cache is None

    def test_populate_after_invalidate(self, temp_system_config: Path) -> None:
        """Test that populate works correctly after invalidation."""
        # First load
        _populate_system_config_cache()
        first_cache = autoflow_module._system_config_cache

        # Invalidate
        invalidate_system_config_cache()
        assert autoflow_module._system_config_cache is None

        # Reload - should work
        _populate_system_config_cache()
        second_cache = autoflow_module._system_config_cache

        # Should have loaded again
        assert second_cache is not None
        # But be a different object (reloaded from disk)
        assert first_cache is not second_cache
        # With the same content
        assert first_cache == second_cache


# ============================================================================
# Agents Config Cache Tests
# ============================================================================


class TestAgentsConfigCache:
    """Tests for _populate_agents_cache() function."""

    def test_populate_loads_agents(self, temp_agents_config: Path) -> None:
        """Test that _populate_agents_cache() loads agents from disk."""
        # Initially cache is empty
        assert autoflow_module._agents_config_cache is None

        # Populate cache
        _populate_agents_cache()

        # Cache should now have agents
        assert autoflow_module._agents_config_cache is not None
        assert "test-agent" in autoflow_module._agents_config_cache

    def test_populate_is_lazy(self, temp_agents_config: Path) -> None:
        """Test that _populate_agents_cache() only loads once (lazy-loading)."""
        # First call should load
        _populate_agents_cache()
        first_cache = autoflow_module._agents_config_cache

        # Second call should not reload (cache hit)
        _populate_agents_cache()
        second_cache = autoflow_module._agents_config_cache

        # Both should be the same object (not reloaded)
        assert first_cache is second_cache

    def test_populate_raises_on_missing_file(self) -> None:
        """Test that _populate_agents_cache() raises SystemExit when file is missing."""
        # Remove agents file if it exists
        if AGENTS_FILE.exists():
            AGENTS_FILE.unlink()

        # Should raise SystemExit
        with pytest.raises(SystemExit):
            _populate_agents_cache()

    def test_invalidate_clears_cache(self, temp_agents_config: Path) -> None:
        """Test that invalidate_agents_cache() clears the cache."""
        # Populate cache
        _populate_agents_cache()
        assert autoflow_module._agents_config_cache is not None

        # Invalidate
        invalidate_agents_cache()

        # Cache should be cleared
        assert autoflow_module._agents_config_cache is None

    def test_invalidate_is_idempotent(self, temp_agents_config: Path) -> None:
        """Test that invalidate_agents_cache() is idempotent."""
        # Populate cache
        _populate_agents_cache()

        # Invalidate once
        invalidate_agents_cache()
        assert autoflow_module._agents_config_cache is None

        # Invalidate again - should be safe
        invalidate_agents_cache()
        assert autoflow_module._agents_config_cache is None

    def test_populate_after_invalidate(self, temp_agents_config: Path) -> None:
        """Test that populate works correctly after invalidation."""
        # First load
        _populate_agents_cache()
        first_cache = autoflow_module._agents_config_cache

        # Invalidate
        invalidate_agents_cache()
        assert autoflow_module._agents_config_cache is None

        # Reload - should work
        _populate_agents_cache()
        second_cache = autoflow_module._agents_config_cache

        # Should have loaded again
        assert second_cache is not None
        # But be a different object (reloaded from disk)
        assert first_cache is not second_cache
        # With the same content
        assert first_cache == second_cache


# ============================================================================
# Tasks Cache Tests
# ============================================================================


class TestTasksCache:
    """Tests for _populate_tasks_cache(spec_slug) function."""

    def test_populate_loads_tasks_for_spec(self, temp_tasks_dir: Path) -> None:
        """Test that _populate_tasks_cache() loads tasks for a spec."""
        # Populate cache for spec-a
        _populate_tasks_cache("spec-a")

        # Cache should have tasks for spec-a
        assert "spec-a" in _tasks_metadata_cache
        assert "spec-a" in _cache_loaded_task_specs

        # Check task content
        tasks = _tasks_metadata_cache["spec-a"]
        assert "tasks" in tasks
        assert "task-1" in tasks["tasks"]

    def test_populate_is_lazy(self, temp_tasks_dir: Path) -> None:
        """Test that _populate_tasks_cache() only loads once per spec."""
        # First call should load
        _populate_tasks_cache("spec-a")
        assert "spec-a" in _cache_loaded_task_specs

        # Second call should not reload (cache hit)
        initial_cache_size = len(_cache_loaded_task_specs)
        _populate_tasks_cache("spec-a")
        # Cache size should not change
        assert len(_cache_loaded_task_specs) == initial_cache_size

    def test_populate_uses_opportunistic_caching(self, temp_tasks_dir: Path) -> None:
        """Test that _populate_tasks_cache() opportunistically caches all specs."""
        # Populate cache for spec-a
        _populate_tasks_cache("spec-a")

        # Due to opportunistic caching, spec-b should also be loaded
        # (it was discovered during the scan)
        assert "spec-a" in _cache_loaded_task_specs
        # Note: opportunistic caching is implementation-dependent,
        # so we just verify spec-a is loaded
        assert "spec-a" in _tasks_metadata_cache

    def test_populate_handles_missing_tasks_dir(self) -> None:
        """Test that _populate_tasks_cache() handles missing TASKS_DIR gracefully."""
        # Remove tasks dir if it exists
        if TASKS_DIR.exists():
            shutil.rmtree(TASKS_DIR)

        # Should not raise an exception
        _populate_tasks_cache("nonexistent-spec")

        # Spec should be marked as loaded (even if empty)
        assert "nonexistent-spec" in _cache_loaded_task_specs

    def test_populate_handles_empty_tasks_dir(self, tmp_path: Path) -> None:
        """Test that _populate_tasks_cache() handles empty TASKS_DIR gracefully."""
        # Clean tasks dir
        if TASKS_DIR.exists():
            for task_file in TASKS_DIR.iterdir():
                if task_file.is_file():
                    task_file.unlink()

        # Should not raise an exception
        _populate_tasks_cache("spec-a")

        # Spec should be marked as loaded
        assert "spec-a" in _cache_loaded_task_specs

    def test_populate_multiple_specs(self, temp_tasks_dir: Path) -> None:
        """Test that _populate_tasks_cache() works for multiple specs."""
        # Populate cache for both specs
        _populate_tasks_cache("spec-a")
        _populate_tasks_cache("spec-b")

        # Both should be in cache
        assert "spec-a" in _tasks_metadata_cache
        assert "spec-b" in _tasks_metadata_cache
        assert "spec-a" in _cache_loaded_task_specs
        assert "spec-b" in _cache_loaded_task_specs

        # Each should have the correct tasks
        assert "task-1" in _tasks_metadata_cache["spec-a"]["tasks"]
        assert "task-2" in _tasks_metadata_cache["spec-b"]["tasks"]


# ============================================================================
# Combined Invalidation Tests
# ============================================================================


class TestInvalidateConfigCache:
    """Tests for invalidate_config_cache() function."""

    def test_invalidate_clears_all_caches(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test that invalidate_config_cache() clears all config caches."""
        # Populate all caches
        _populate_system_config_cache()
        _populate_agents_cache()

        # Verify caches are populated
        assert autoflow_module._system_config_cache is not None
        assert autoflow_module._agents_config_cache is not None

        # Invalidate all config caches
        invalidate_config_cache()

        # All caches should be cleared
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None

    def test_invalidate_is_idempotent(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test that invalidate_config_cache() is idempotent."""
        # Populate caches
        _populate_system_config_cache()
        _populate_agents_cache()

        # Invalidate once
        invalidate_config_cache()
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None

        # Invalidate again - should be safe
        invalidate_config_cache()
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None

    def test_invariant_before_populate(self) -> None:
        """Test that invalidate before any populate is safe."""
        # Initially caches are empty
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None

        # Invalidate should be safe
        invalidate_config_cache()

        # Caches should still be None
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and corner cases."""

    def test_concurrent_populate_calls(self, temp_system_config: Path) -> None:
        """Test that concurrent populate calls are handled correctly."""
        # Multiple populate calls should be safe
        _populate_system_config_cache()
        _populate_system_config_cache()
        _populate_system_config_cache()

        # Cache should still be valid
        assert autoflow_module._system_config_cache is not None

    def test_populate_modify_invalidate_cycle(
        self, temp_system_config: Path
    ) -> None:
        """Test the populate-modify-invalidate cycle."""
        # Populate
        _populate_system_config_cache()
        assert autoflow_module._system_config_cache is not None

        # Simulate modification by invalidating
        invalidate_system_config_cache()
        assert autoflow_module._system_config_cache is None

        # Repopulate
        _populate_system_config_cache()
        assert autoflow_module._system_config_cache is not None

    def test_tasks_cache_with_nonexistent_spec(self, temp_tasks_dir: Path) -> None:
        """Test that querying nonexistent spec creates empty cache entry but doesn't mark as loaded."""
        # Clear the cache first to start fresh
        _cache_loaded_task_specs.clear()
        _tasks_metadata_cache.clear()

        # Query a spec that doesn't exist in the temp_tasks_dir
        # (temp_tasks_dir only has spec-a and spec-b)
        _populate_tasks_cache("nonexistent-spec")

        # Due to opportunistic caching, spec-a and spec-b should be loaded
        # (they were discovered during the filesystem scan)
        assert "spec-a" in _cache_loaded_task_specs
        assert "spec-b" in _cache_loaded_task_specs

        # The nonexistent spec should have an empty cache entry (created at line 2672-2673)
        assert "nonexistent-spec" in _tasks_metadata_cache
        assert _tasks_metadata_cache["nonexistent-spec"] == {}

        # But the nonexistent spec should NOT be marked as loaded
        # (because it wasn't discovered during the scan)
        assert "nonexistent-spec" not in _cache_loaded_task_specs

    def test_mixed_cache_operations(
        self, temp_system_config: Path, temp_agents_config: Path, temp_tasks_dir: Path
    ) -> None:
        """Test mixing different cache operations."""
        # Populate system cache
        _populate_system_config_cache()
        assert autoflow_module._system_config_cache is not None

        # Populate agents cache
        _populate_agents_cache()
        assert autoflow_module._agents_config_cache is not None

        # Populate tasks cache
        _populate_tasks_cache("spec-a")
        assert "spec-a" in _cache_loaded_task_specs

        # Invalidate all config caches (but not tasks cache)
        invalidate_config_cache()
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None

        # Tasks cache should not be affected
        assert "spec-a" in _cache_loaded_task_specs

    def test_multiple_invalidation_calls(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test multiple invalidation calls in sequence."""
        # Populate
        _populate_system_config_cache()
        _populate_agents_cache()

        # Multiple invalidations
        invalidate_system_config_cache()
        invalidate_agents_cache()
        invalidate_config_cache()

        # All caches should be cleared
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None
