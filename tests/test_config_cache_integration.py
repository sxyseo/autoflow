"""
Integration Tests for Configuration Cache Consistency

Tests the integration and consistency of the configuration cache across operations:
- Cache remains consistent when config files are created/modified
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

import pytest

# Import the module to access globals
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.autoflow as autoflow_module

from scripts.autoflow import (
    AGENTS_FILE,
    SYSTEM_CONFIG_FILE,
    _agents_config_cache,
    _cache_loaded_task_specs,
    _system_config_cache,
    _tasks_metadata_cache,
    invalidate_agents_cache,
    invalidate_config_cache,
    invalidate_system_config_cache,
    load_agents,
    load_system_config,
    load_tasks,
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

    # Clear tasks cache
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
            "claude-code": {
                "protocol": "cli",
                "command": "claude",
                "args": ["--mode", "code"],
                "model_profile": "implementation"
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


# ============================================================================
# Cache Consistency Tests
# ============================================================================


class TestCacheConsistency:
    """Tests for cache consistency across operations."""

    def test_system_config_cache_consistency_after_modification(
        self, temp_system_config: Path
    ) -> None:
        """Test that system config cache reflects modified files after invalidation."""
        # Load config into cache
        config1 = load_system_config()
        assert config1.get("memory", {}).get("enabled") is True

        # Modify the config file
        modified_config = read_json(SYSTEM_CONFIG_FILE)
        modified_config["memory"]["enabled"] = False
        write_json(SYSTEM_CONFIG_FILE, modified_config)

        # Cache should still show old value (stale)
        config2 = load_system_config()
        assert config2.get("memory", {}).get("enabled") is True

        # Invalidate cache
        invalidate_system_config_cache()

        # Now cache should show updated value
        config3 = load_system_config()
        assert config3.get("memory", {}).get("enabled") is False

    def test_agents_config_cache_consistency_after_modification(
        self, temp_agents_config: Path
    ) -> None:
        """Test that agents config cache reflects modified files after invalidation."""
        # Load config into cache
        agents1 = load_agents()
        assert "claude-code" in agents1

        # Modify the agents file
        modified_agents = read_json(AGENTS_FILE)
        modified_agents["agents"]["claude-spec"] = {
            "protocol": "cli",
            "command": "claude",
            "args": ["--mode", "spec"],
            "model_profile": "spec"
        }
        write_json(AGENTS_FILE, modified_agents)

        # Cache should still show old value (stale)
        agents2 = load_agents()
        assert "claude-spec" not in agents2

        # Invalidate cache
        invalidate_agents_cache()

        # Now cache should show updated value
        agents3 = load_agents()
        assert "claude-spec" in agents3

    def test_cache_consistency_after_creation(
        self, temp_system_config: Path
    ) -> None:
        """Test that cache reflects newly created config sections after invalidation."""
        # Load initial config
        config1 = load_system_config()
        assert "models" in config1

        # Add a new section to the config
        modified_config = read_json(SYSTEM_CONFIG_FILE)
        modified_config["new_section"] = {"key": "value"}
        write_json(SYSTEM_CONFIG_FILE, modified_config)

        # Cache should still show old config (stale)
        config2 = load_system_config()
        assert "new_section" not in config2

        # Invalidate cache
        invalidate_system_config_cache()

        # Now cache should show new section
        config3 = load_system_config()
        assert "new_section" in config3
        assert config3["new_section"]["key"] == "value"

    def test_cross_function_consistency(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test that different cached functions see consistent data."""
        # Load both configs
        system_config = load_system_config()
        agents = load_agents()

        # Verify both are cached
        assert autoflow_module._system_config_cache is not None
        assert autoflow_module._agents_config_cache is not None

        # Modify system config
        modified_system = read_json(SYSTEM_CONFIG_FILE)
        modified_system["memory"]["enabled"] = False
        write_json(SYSTEM_CONFIG_FILE, modified_system)

        # System config should be stale, but agents should still be fresh
        system_stale = load_system_config()
        agents_fresh = load_agents()

        assert system_stale.get("memory", {}).get("enabled") is True  # Still stale
        assert "claude-code" in agents_fresh

        # Invalidate all caches
        invalidate_config_cache()

        # Now both should be fresh
        system_fresh = load_system_config()
        agents_fresh2 = load_agents()

        assert system_fresh.get("memory", {}).get("enabled") is False
        assert "claude-code" in agents_fresh2


# ============================================================================
# Cache Invalidation Tests
# ============================================================================


class TestCacheInvalidation:
    """Tests for cache invalidation behavior."""

    def test_invalidate_config_cache_clears_all(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test that invalidate_config_cache() clears all config caches."""
        # Load configs to populate cache
        load_system_config()
        load_agents()

        # Verify cache is populated
        assert autoflow_module._system_config_cache is not None
        assert autoflow_module._agents_config_cache is not None

        # Invalidate all
        invalidate_config_cache()

        # Verify all caches are cleared
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None

    def test_invalidate_system_config_only(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test that invalidate_system_config_cache() only clears system config."""
        # Load configs to populate cache
        load_system_config()
        load_agents()

        # Store reference to agents cache
        agents_cache_ref = autoflow_module._agents_config_cache

        # Invalidate only system config
        invalidate_system_config_cache()

        # Verify only system cache is cleared
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is agents_cache_ref

    def test_invalidate_agents_only(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test that invalidate_agents_cache() only clears agents config."""
        # Load configs to populate cache
        load_system_config()
        load_agents()

        # Store reference to system cache
        system_cache_ref = autoflow_module._system_config_cache

        # Invalidate only agents
        invalidate_agents_cache()

        # Verify only agents cache is cleared
        assert autoflow_module._system_config_cache is system_cache_ref
        assert autoflow_module._agents_config_cache is None

    def test_invalidate_before_any_load(
        self, temp_system_config: Path
    ) -> None:
        """Test that invalidation before any load is safe."""
        # Invalidate without any cache populated
        invalidate_config_cache()

        # Should be able to load configs normally
        config = load_system_config()
        assert "memory" in config

    def test_multiple_invalidations_in_sequence(
        self, temp_system_config: Path
    ) -> None:
        """Test that multiple invalidations in sequence work correctly."""
        # Load config
        load_system_config()
        assert autoflow_module._system_config_cache is not None

        # Invalidate multiple times
        invalidate_system_config_cache()
        assert autoflow_module._system_config_cache is None

        invalidate_system_config_cache()
        assert autoflow_module._system_config_cache is None

        # Should still work
        config = load_system_config()
        assert "memory" in config


# ============================================================================
# Lazy Loading Tests
# ============================================================================


class TestLazyLoading:
    """Tests for lazy-loading behavior."""

    def test_lazy_load_on_demand(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test that cache lazy-loads configs on demand."""
        # Initially cache is empty
        assert autoflow_module._system_config_cache is None
        assert autoflow_module._agents_config_cache is None

        # Load system config
        system_config = load_system_config()
        assert autoflow_module._system_config_cache is not None
        assert "memory" in system_config

        # Load agents config
        agents = load_agents()
        assert autoflow_module._agents_config_cache is not None
        assert "claude-code" in agents

    def test_cache_hit_returns_same_object(
        self, temp_system_config: Path
    ) -> None:
        """Test that cache hit returns the same object (identity)."""
        config1 = load_system_config()
        config2 = load_system_config()

        # Should be the exact same object
        assert config1 is config2

    def test_cache_miss_after_invalidation(
        self, temp_system_config: Path
    ) -> None:
        """Test that invalidation causes cache miss on next load."""
        config1 = load_system_config()
        invalidate_system_config_cache()
        config2 = load_system_config()

        # Should be different objects (cache miss)
        assert config1 is not config2

        # But content should be the same
        assert config1.get("memory", {}).get("enabled") == config2.get("memory", {}).get("enabled")


# ============================================================================
# Integration with Original Functions
# ============================================================================


class TestIntegrationWithOriginal:
    """Tests for integration with original (uncached) functions."""

    def test_load_system_config_returns_correct_results(
        self, temp_system_config: Path
    ) -> None:
        """Test that cached load_system_config returns same results as uncached."""
        # Load with cache
        invalidate_system_config_cache()
        config_cached = load_system_config()

        # Load from disk directly
        config_disk = read_json(SYSTEM_CONFIG_FILE)

        # Results should match (ignoring default merging)
        assert config_cached.get("memory", {}).get("enabled") == config_disk.get("memory", {}).get("enabled")
        assert "models" in config_cached

    def test_load_agents_returns_correct_results(
        self, temp_agents_config: Path
    ) -> None:
        """Test that cached load_agents returns same results as uncached."""
        # Load with cache
        invalidate_agents_cache()
        agents_cached = load_agents()

        # Load from disk directly
        agents_disk = read_json(AGENTS_FILE)

        # Results should match
        assert "claude-code" in agents_cached
        assert "claude-code" in agents_disk.get("agents", {})


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and corner cases."""

    def test_cache_with_empty_config(
        self, temp_system_config: Path
    ) -> None:
        """Test cache handles empty config files correctly."""
        # Write empty config
        write_json(SYSTEM_CONFIG_FILE, {})

        # Should load without error (with defaults merged in)
        config = load_system_config()
        assert isinstance(config, dict)

    def test_cache_with_malformed_json(
        self, temp_system_config: Path
    ) -> None:
        """Test cache handles malformed JSON gracefully."""
        # Create malformed config file
        SYSTEM_CONFIG_FILE.write_text("{invalid json", encoding="utf-8")

        # Should not raise error (load_system_config uses read_json_or_default)
        config = load_system_config()
        assert isinstance(config, dict)

    def test_cache_invalidation_idempotence(
        self, temp_system_config: Path
    ) -> None:
        """Test that cache invalidation is idempotent."""
        # Load and populate cache
        load_system_config()
        assert autoflow_module._system_config_cache is not None

        # Invalidate once
        invalidate_system_config_cache()
        assert autoflow_module._system_config_cache is None

        # Invalidate again - should be safe
        invalidate_system_config_cache()
        assert autoflow_module._system_config_cache is None

        # Should still work
        config = load_system_config()
        assert "memory" in config

    def test_multiple_load_calls_consistency(
        self, temp_system_config: Path
    ) -> None:
        """Test that multiple load calls return consistent data."""
        # Load multiple times
        config1 = load_system_config()
        config2 = load_system_config()
        config3 = load_system_config()

        # All should be the same object
        assert config1 is config2
        assert config2 is config3

        # All should have the same content
        enabled1 = config1.get("memory", {}).get("enabled")
        enabled2 = config2.get("memory", {}).get("enabled")
        enabled3 = config3.get("memory", {}).get("enabled")
        assert enabled1 == enabled2 == enabled3

    def test_cache_consistency_with_real_files(
        self, temp_system_config: Path, temp_agents_config: Path
    ) -> None:
        """Test cache consistency with actual file operations."""
        # Load configs
        config1 = load_system_config()
        agents1 = load_agents()

        # Verify content
        assert config1.get("memory", {}).get("enabled") is True
        assert "claude-code" in agents1

        # Modify both files
        config_mod = read_json(SYSTEM_CONFIG_FILE)
        config_mod["memory"]["enabled"] = False
        write_json(SYSTEM_CONFIG_FILE, config_mod)

        agents_mod = read_json(AGENTS_FILE)
        agents_mod["agents"]["test-agent"] = {"protocol": "cli", "command": "test"}
        write_json(AGENTS_FILE, agents_mod)

        # Cache should still be stale
        config2 = load_system_config()
        agents2 = load_agents()
        assert config2.get("memory", {}).get("enabled") is True
        assert "test-agent" not in agents2

        # Invalidate both
        invalidate_config_cache()

        # Now should be fresh
        config3 = load_system_config()
        agents3 = load_agents()
        assert config3.get("memory", {}).get("enabled") is False
        assert "test-agent" in agents3
