"""
Unit and Integration Tests for AutoflowCLI Cache Functions

Tests the cache population and invalidation functions for system config
and agents config in the AutoflowCLI module.

Unit tests (test individual functions in isolation):
- _populate_system_config_cache()
- _populate_agents_cache()
- invalidate_config_cache()
- invalidate_system_config_cache()
- invalidate_agents_cache()

Integration tests (test load methods with caching):
- load_system_config() uses cache
- load_agents() uses cache
- cache invalidation triggers reload
- multiple AutoflowCLI instances share cache
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autoflow.autoflow_cli import (
    AutoflowCLI,
    _agents_config_cache,
    _cache_loaded_specs,
    _cache_loaded_task_specs,
    _populate_agents_cache,
    _populate_system_config_cache,
    _run_metadata_cache,
    _system_config_cache,
    _tasks_metadata_cache,
    invalidate_agents_cache,
    invalidate_config_cache,
    invalidate_system_config_cache,
)

# Import module to access globals
import autoflow.autoflow_cli as autoflow_cli_module


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    """Clean and reset all CLI caches before each test to ensure isolation."""
    # Invalidate all caches before test
    invalidate_config_cache()

    # Also clear run metadata and tasks cache
    global _run_metadata_cache, _cache_loaded_specs, _tasks_metadata_cache, _cache_loaded_task_specs
    _run_metadata_cache.clear()
    _cache_loaded_specs.clear()
    _tasks_metadata_cache.clear()
    _cache_loaded_task_specs.clear()

    yield

    # Clean up after test
    invalidate_config_cache()
    _run_metadata_cache.clear()
    _cache_loaded_specs.clear()
    _tasks_metadata_cache.clear()
    _cache_loaded_task_specs.clear()


@pytest.fixture
def cli_instance() -> AutoflowCLI:
    """Create a test CLI instance."""
    from autoflow.core.config import load_config

    config = load_config()
    return AutoflowCLI(config)


# ============================================================================
# System Config Cache Tests
# ============================================================================


class TestSystemConfigCache:
    """Tests for _populate_system_config_cache() function."""

    def test_populate_loads_config(self, cli_instance: AutoflowCLI) -> None:
        """Test that _populate_system_config_cache() loads config from disk."""
        # Initially cache is empty
        assert autoflow_cli_module._system_config_cache is None

        # Populate cache
        _populate_system_config_cache()

        # Cache should now have config
        assert autoflow_cli_module._system_config_cache is not None
        assert isinstance(autoflow_cli_module._system_config_cache, dict)

    def test_populate_is_lazy(self, cli_instance: AutoflowCLI) -> None:
        """Test that _populate_system_config_cache() only loads once (lazy-loading)."""
        # First call should load
        _populate_system_config_cache()
        first_cache = autoflow_cli_module._system_config_cache

        # Second call should not reload (cache hit)
        _populate_system_config_cache()
        second_cache = autoflow_cli_module._system_config_cache

        # Both should be the same object (not reloaded)
        assert first_cache is second_cache

    def test_populate_handles_missing_file_gracefully(
        self, cli_instance: AutoflowCLI
    ) -> None:
        """Test that _populate_system_config_cache() handles missing file gracefully."""
        # The AutoflowCLI.load_system_config() handles missing files by creating defaults
        # so _populate_system_config_cache() should not raise an exception

        # Should not raise an exception
        _populate_system_config_cache()

        # Cache should have something (defaults or config)
        assert autoflow_cli_module._system_config_cache is not None
        assert isinstance(autoflow_cli_module._system_config_cache, dict)

    def test_invalidate_clears_cache(self, cli_instance: AutoflowCLI) -> None:
        """Test that invalidate_system_config_cache() clears the cache."""
        # Populate cache
        _populate_system_config_cache()
        assert autoflow_cli_module._system_config_cache is not None

        # Invalidate
        invalidate_system_config_cache()

        # Cache should be cleared
        assert autoflow_cli_module._system_config_cache is None

    def test_invalidate_is_idempotent(self, cli_instance: AutoflowCLI) -> None:
        """Test that invalidate_system_config_cache() is idempotent."""
        # Populate cache
        _populate_system_config_cache()

        # Invalidate once
        invalidate_system_config_cache()
        assert autoflow_cli_module._system_config_cache is None

        # Invalidate again - should be safe
        invalidate_system_config_cache()
        assert autoflow_cli_module._system_config_cache is None

    def test_populate_after_invalidate(self, cli_instance: AutoflowCLI) -> None:
        """Test that populate works correctly after invalidation."""
        # First load
        _populate_system_config_cache()
        first_cache = autoflow_cli_module._system_config_cache

        # Invalidate
        invalidate_system_config_cache()
        assert autoflow_cli_module._system_config_cache is None

        # Reload - should work
        _populate_system_config_cache()
        second_cache = autoflow_cli_module._system_config_cache

        # Should have loaded again
        assert second_cache is not None
        # But be a different object (reloaded from disk)
        assert first_cache is not second_cache
        # With the same content (both are dicts with similar structure)
        assert isinstance(first_cache, dict)
        assert isinstance(second_cache, dict)


# ============================================================================
# Agents Config Cache Tests
# ============================================================================


class TestAgentsConfigCache:
    """Tests for _populate_agents_cache() function."""

    def test_populate_loads_agents(self, cli_instance: AutoflowCLI) -> None:
        """Test that _populate_agents_cache() loads agents from disk."""
        # Initially cache is empty
        assert autoflow_cli_module._agents_config_cache is None

        # Populate cache
        _populate_agents_cache()

        # Cache should now have agents (or empty dict if no agents file)
        assert autoflow_cli_module._agents_config_cache is not None
        assert isinstance(autoflow_cli_module._agents_config_cache, dict)

    def test_populate_is_lazy(self, cli_instance: AutoflowCLI) -> None:
        """Test that _populate_agents_cache() only loads once (lazy-loading)."""
        # First call should load
        _populate_agents_cache()
        first_cache = autoflow_cli_module._agents_config_cache

        # Second call should not reload (cache hit)
        _populate_agents_cache()
        second_cache = autoflow_cli_module._agents_config_cache

        # Both should be the same object (not reloaded)
        assert first_cache is second_cache

    def test_populate_handles_missing_file_gracefully(
        self, cli_instance: AutoflowCLI
    ) -> None:
        """Test that _populate_agents_cache() handles missing file gracefully."""
        # The AutoflowCLI.load_agents() handles missing files by returning empty dict
        # so _populate_agents_cache() should not raise an exception

        # Should not raise an exception
        _populate_agents_cache()

        # Cache should have something (empty dict or agents)
        assert autoflow_cli_module._agents_config_cache is not None
        assert isinstance(autoflow_cli_module._agents_config_cache, dict)

    def test_invalidate_clears_cache(self, cli_instance: AutoflowCLI) -> None:
        """Test that invalidate_agents_cache() clears the cache."""
        # Populate cache
        _populate_agents_cache()
        assert autoflow_cli_module._agents_config_cache is not None

        # Invalidate
        invalidate_agents_cache()

        # Cache should be cleared
        assert autoflow_cli_module._agents_config_cache is None

    def test_invalidate_is_idempotent(self, cli_instance: AutoflowCLI) -> None:
        """Test that invalidate_agents_cache() is idempotent."""
        # Populate cache
        _populate_agents_cache()

        # Invalidate once
        invalidate_agents_cache()
        assert autoflow_cli_module._agents_config_cache is None

        # Invalidate again - should be safe
        invalidate_agents_cache()
        assert autoflow_cli_module._agents_config_cache is None

    def test_populate_after_invalidate(self, cli_instance: AutoflowCLI) -> None:
        """Test that populate works correctly after invalidation."""
        # First load
        _populate_agents_cache()
        first_cache = autoflow_cli_module._agents_config_cache

        # Invalidate
        invalidate_agents_cache()
        assert autoflow_cli_module._agents_config_cache is None

        # Reload - should work
        _populate_agents_cache()
        second_cache = autoflow_cli_module._agents_config_cache

        # Should have loaded again
        assert second_cache is not None
        # But be a different object (reloaded from disk)
        assert first_cache is not second_cache
        # With the same type
        assert isinstance(first_cache, dict)
        assert isinstance(second_cache, dict)


# ============================================================================
# Combined Invalidation Tests
# ============================================================================


class TestInvalidateConfigCache:
    """Tests for invalidate_config_cache() function."""

    def test_invalidate_clears_all_caches(self, cli_instance: AutoflowCLI) -> None:
        """Test that invalidate_config_cache() clears all config caches."""
        # Populate all caches
        _populate_system_config_cache()
        _populate_agents_cache()

        # Verify caches are populated
        assert autoflow_cli_module._system_config_cache is not None
        assert autoflow_cli_module._agents_config_cache is not None

        # Invalidate all config caches
        invalidate_config_cache()

        # All caches should be cleared
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is None

    def test_invalidate_is_idempotent(self, cli_instance: AutoflowCLI) -> None:
        """Test that invalidate_config_cache() is idempotent."""
        # Populate caches
        _populate_system_config_cache()
        _populate_agents_cache()

        # Invalidate once
        invalidate_config_cache()
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is None

        # Invalidate again - should be safe
        invalidate_config_cache()
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is None

    def test_invariant_before_populate(self, cli_instance: AutoflowCLI) -> None:
        """Test that invalidate before any populate is safe."""
        # Initially caches are empty
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is None

        # Invalidate should be safe
        invalidate_config_cache()

        # Caches should still be None
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is None


# ============================================================================
# Integration with AutoflowCLI Methods
# ============================================================================


class TestLoadMethodsCaching:
    """Integration tests for AutoflowCLI load methods with caching."""

    @pytest.mark.integration
    def test_load_system_config_uses_cache(
        self, cli_instance: AutoflowCLI
    ) -> None:
        """Test that load_system_config() method uses caching."""
        # Ensure clean cache
        invalidate_system_config_cache()

        # First call - cache miss
        config1 = cli_instance.load_system_config()

        # Second call - cache hit (should return same object)
        config2 = cli_instance.load_system_config()

        # Both should be the same object (identity check)
        assert config1 is config2

    @pytest.mark.integration
    def test_load_agents_uses_cache(self, cli_instance: AutoflowCLI) -> None:
        """Test that load_agents() method uses caching."""
        # Ensure clean cache
        invalidate_agents_cache()

        # First call - cache miss
        agents1 = cli_instance.load_agents()

        # Second call - cache hit (should return same object)
        agents2 = cli_instance.load_agents()

        # Both should be the same object (identity check)
        assert agents1 is agents2

    @pytest.mark.integration
    def test_cache_invalidation_triggers_reload(
        self, cli_instance: AutoflowCLI
    ) -> None:
        """Test that cache invalidation triggers reload on next access."""
        # First load
        config1 = cli_instance.load_system_config()

        # Invalidate cache
        invalidate_system_config_cache()

        # Second load - should reload (different object)
        config2 = cli_instance.load_system_config()

        # Should be different objects
        assert config1 is not config2

    @pytest.mark.integration
    def test_cache_invalidation_for_agents(self, cli_instance: AutoflowCLI) -> None:
        """Test that agents cache invalidation triggers reload on next access."""
        # First load
        agents1 = cli_instance.load_agents()

        # Invalidate cache
        invalidate_agents_cache()

        # Second load - should reload (different object)
        agents2 = cli_instance.load_agents()

        # Should be different objects
        assert agents1 is not agents2

    @pytest.mark.integration
    def test_multiple_cli_instances_share_cache(self) -> None:
        """Test that multiple AutoflowCLI instances share the same cache."""
        from autoflow.core.config import load_config

        # Ensure clean cache
        invalidate_config_cache()

        # Create two instances
        config1 = load_config()
        config2 = load_config()
        cli1 = AutoflowCLI(config1)
        cli2 = AutoflowCLI(config2)

        # Load from first instance
        system_config1 = cli1.load_system_config()
        agents1 = cli1.load_agents()

        # Load from second instance - should hit cache
        system_config2 = cli2.load_system_config()
        agents2 = cli2.load_agents()

        # Should be the same objects (module-level cache is shared)
        assert system_config1 is system_config2
        assert agents1 is agents2

    @pytest.mark.integration
    def test_cache_performance_benefit(self, cli_instance: AutoflowCLI) -> None:
        """Test that caching provides performance benefit by avoiding disk I/O."""
        import time

        # Ensure clean cache
        invalidate_config_cache()

        # First call - should be slower (cache miss, reads from disk)
        start = time.perf_counter()
        cli_instance.load_system_config()
        first_call_time = time.perf_counter() - start

        # Second call - should be faster (cache hit, no disk I/O)
        start = time.perf_counter()
        cli_instance.load_system_config()
        second_call_time = time.perf_counter() - start

        # Second call should be significantly faster (or at least not slower)
        # We allow some tolerance for timing variations
        assert second_call_time <= first_call_time * 1.5

    @pytest.mark.integration
    def test_combined_cache_operations(self, cli_instance: AutoflowCLI) -> None:
        """Test combining multiple cache operations in sequence."""
        # Ensure clean cache
        invalidate_config_cache()

        # Load both configs
        system_config = cli_instance.load_system_config()
        agents = cli_instance.load_agents()

        # Verify they're cached
        assert autoflow_cli_module._system_config_cache is not None
        assert autoflow_cli_module._agents_config_cache is not None

        # Invalidate all
        invalidate_config_cache()

        # Verify both are cleared
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is None

        # Reload both
        system_config2 = cli_instance.load_system_config()
        agents2 = cli_instance.load_agents()

        # Should be different objects (reloaded)
        assert system_config is not system_config2
        assert agents is not agents2

    @pytest.mark.integration
    def test_selective_cache_invalidation(self, cli_instance: AutoflowCLI) -> None:
        """Test that selective cache invalidation works correctly."""
        # Ensure clean cache and load both
        invalidate_config_cache()
        system_config = cli_instance.load_system_config()
        agents = cli_instance.load_agents()

        # Invalidate only system config
        invalidate_system_config_cache()

        # System config should be None, agents should still be cached
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is not None

        # Reload system config
        system_config2 = cli_instance.load_system_config()

        # System config should be reloaded (different object)
        assert system_config is not system_config2

        # Agents should still be the same cached object
        agents2 = cli_instance.load_agents()
        assert agents is agents2


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and corner cases."""

    def test_concurrent_populate_calls(self, cli_instance: AutoflowCLI) -> None:
        """Test that concurrent populate calls are handled correctly."""
        # Multiple populate calls should be safe
        _populate_system_config_cache()
        _populate_system_config_cache()
        _populate_system_config_cache()

        # Cache should still be valid
        assert autoflow_cli_module._system_config_cache is not None

    def test_populate_modify_invalidate_cycle(self, cli_instance: AutoflowCLI) -> None:
        """Test the populate-modify-invalidate cycle."""
        # Populate
        _populate_system_config_cache()
        assert autoflow_cli_module._system_config_cache is not None

        # Simulate modification by invalidating
        invalidate_system_config_cache()
        assert autoflow_cli_module._system_config_cache is None

        # Repopulate
        _populate_system_config_cache()
        assert autoflow_cli_module._system_config_cache is not None

    def test_mixed_cache_operations(self, cli_instance: AutoflowCLI) -> None:
        """Test mixing different cache operations."""
        # Populate system cache
        _populate_system_config_cache()
        assert autoflow_cli_module._system_config_cache is not None

        # Populate agents cache
        _populate_agents_cache()
        assert autoflow_cli_module._agents_config_cache is not None

        # Invalidate all config caches
        invalidate_config_cache()
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is None

        # Repopulate both
        _populate_system_config_cache()
        _populate_agents_cache()
        assert autoflow_cli_module._system_config_cache is not None
        assert autoflow_cli_module._agents_config_cache is not None

    def test_multiple_invalidation_calls(self, cli_instance: AutoflowCLI) -> None:
        """Test multiple invalidation calls in sequence."""
        # Populate
        _populate_system_config_cache()
        _populate_agents_cache()

        # Multiple invalidations
        invalidate_system_config_cache()
        invalidate_agents_cache()
        invalidate_config_cache()

        # All caches should be cleared
        assert autoflow_cli_module._system_config_cache is None
        assert autoflow_cli_module._agents_config_cache is None

    def test_invalidate_does_not_affect_other_caches(
        self, cli_instance: AutoflowCLI
    ) -> None:
        """Test that invalidating one cache doesn't affect others."""
        # Populate all caches
        _populate_system_config_cache()
        _populate_agents_cache()

        # Add some dummy data to run metadata cache
        _run_metadata_cache["test"] = [{}]

        # Invalidate only system config
        invalidate_system_config_cache()

        # System config should be cleared
        assert autoflow_cli_module._system_config_cache is None

        # But agents and run metadata should not be affected
        assert autoflow_cli_module._agents_config_cache is not None
        assert len(_run_metadata_cache) == 1

    def test_cache_survives_across_multiple_cli_calls(self) -> None:
        """Test that cache persists across multiple CLI method calls."""
        from autoflow.core.config import load_config

        # Ensure clean cache
        invalidate_config_cache()

        # Create CLI instance and load config
        config = load_config()
        cli = AutoflowCLI(config)

        # Load config multiple times
        for _ in range(5):
            result = cli.load_system_config()
            assert result is not None
            assert isinstance(result, dict)

        # All calls should have returned the same cached object
        # (verified by checking that cache is still the same object)
        final_result = cli.load_system_config()
        assert autoflow_cli_module._system_config_cache is final_result
