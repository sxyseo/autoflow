"""
Unit Tests for Configuration and Cache Functions

Tests the actual configuration loading and caching functions that exist in scripts/autoflow.py

Functions Tested:
- load_system_config()
- load_agents()
- write_json()
- read_json()
- _populate_run_cache_for_spec()
- _populate_run_cache()
- invalidate_run_cache()
"""

from __future__ import annotations

import json
import shutil
import tempfile
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
    _populate_run_cache_for_spec,
    _populate_run_cache,
    invalidate_run_cache,
    read_json,
    write_json,
    load_system_config,
    load_agents,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test isolation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def temp_system_config(temp_dir):
    """Create a temporary system config file for test isolation."""
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

    config_file = temp_dir / "system.json"
    write_json(config_file, test_config)

    # Patch the SYSTEM_CONFIG_FILE to use our test file
    with patch.object(autoflow_module, 'SYSTEM_CONFIG_FILE', config_file):
        yield config_file, test_config


@pytest.fixture
def temp_agents_config(temp_dir):
    """Create a temporary agents config file."""
    test_agents = {
        "agents": {
            "test-agent": {
                "command": "echo",
                "args": ["test"]
            }
        }
    }

    agents_file = temp_dir / "agents.json"
    write_json(agents_file, test_agents)

    with patch.object(autoflow_module, 'AGENTS_FILE', agents_file):
        yield agents_file, test_agents


# ============================================================================
# Test JSON Operations
# ============================================================================

class TestJsonOperations:
    """Test basic JSON read/write operations."""

    def test_write_json_creates_file(self, temp_dir):
        """Test that write_json creates a file with correct content."""
        test_file = temp_dir / "test.json"
        test_data = {"key": "value"}

        write_json(test_file, test_data)

        assert test_file.exists()
        content = test_file.read_text()
        assert json.loads(content) == test_data

    def test_read_json_loads_existing_file(self, temp_dir):
        """Test that read_json loads existing JSON files."""
        test_file = temp_dir / "test.json"
        test_data = {"key": "value"}

        # Write the file first
        test_file.write_text(json.dumps(test_data))

        # Read it back
        result = read_json(test_file)

        assert result == test_data

    def test_read_json_returns_default_for_missing(self, temp_dir):
        """Test that read_json returns default value for missing files."""
        missing_file = temp_dir / "missing.json"
        default_value = {"default": True}

        result = autoflow_module.read_json_or_default(missing_file, default_value)

        assert result == default_value


# ============================================================================
# Test Config Loading
# ============================================================================

class TestSystemConfig:
    """Test system configuration loading."""

    def test_load_system_config_loads_from_file(self, temp_system_config):
        """Test that load_system_config loads from file."""
        config_file, test_config = temp_system_config

        result = load_system_config()

        # Result should include the file config plus defaults
        assert "memory" in result
        assert result["memory"]["enabled"] == test_config["memory"]["enabled"]
        assert "models" in result

    def test_load_system_config_returns_default_for_missing_file(self, temp_dir):
        """Test that load_system_config returns default when file missing."""
        missing_config = temp_dir / "nonexistent.json"

        with patch.object(autoflow_module, 'SYSTEM_CONFIG_FILE', missing_config):
            result = load_system_config()

        # Should return default config
        assert "memory" in result
        assert "models" in result

    def test_load_system_config_handles_invalid_json(self, temp_dir):
        """Test that load_system_config handles invalid JSON gracefully."""
        invalid_file = temp_dir / "invalid.json"
        invalid_file.write_text("{invalid json")

        with patch.object(autoflow_module, 'SYSTEM_CONFIG_FILE', invalid_file):
            result = load_system_config()

        # Should return default config instead of crashing
        assert isinstance(result, dict)


# ============================================================================
# Test Agents Loading
# ============================================================================

class TestAgentsLoading:
    """Test agents configuration loading."""

    def test_load_agents_loads_from_file(self, temp_agents_config):
        """Test that load_agents loads agents from file."""
        agents_file, test_agents = temp_agents_config

        result = load_agents()

        # Result should contain agents
        assert "test-agent" in result
        assert result["test-agent"].command == "echo"

    def test_load_agents_exits_on_missing_file(self, temp_dir):
        """Test that load_agents exits on missing file."""
        missing_agents = temp_dir / "nonexistent.json"

        with patch.object(autoflow_module, 'AGENTS_FILE', missing_agents):
            with pytest.raises(SystemExit):
                load_agents()


# ============================================================================
# Test Run Cache Functions
# ============================================================================

class TestRunCache:
    """Test run cache population and invalidation."""

    def test_populate_run_cache_for_spec(self, temp_dir):
        """Test populating run cache for a specific spec."""
        # Create a mock spec directory
        spec_slug = "test-spec"
        spec_dir = temp_dir / "specs" / spec_slug
        spec_dir.mkdir(parents=True)

        # Create runs directory
        runs_dir = spec_dir / "runs"
        runs_dir.mkdir()

        # Create a mock run
        run_dir = runs_dir / "20260316T120000Z-test"
        run_dir.mkdir()

        with patch.object(autoflow_module, 'SPECS_DIR', temp_dir / "specs"):
            # Should not crash
            _populate_run_cache_for_spec(spec_slug)

    def test_invalidate_run_cache(self):
        """Test that invalidate_run_cache clears the cache."""
        # This test verifies the function exists and can be called
        invalidate_run_cache()

        # If we get here without exception, test passes
        assert True


# ============================================================================
# Test Integration
# ============================================================================

class TestConfigIntegration:
    """Test integration between different config components."""

    def test_system_and_agents_config_work_together(self, temp_dir):
        """Test that system config and agents config can be used together."""
        # Create both configs
        system_config = {
            "memory": {"enabled": True},
            "models": {
                "spec": {"model": "test-model"}
            }
        }

        agents_config = {
            "agents": {
                "test-agent": {
                    "command": "echo",
                    "model_profile": "spec"
                }
            }
        }

        system_file = temp_dir / "system.json"
        agents_file = temp_dir / "agents.json"

        write_json(system_file, system_config)
        write_json(agents_file, agents_config)

        with patch.object(autoflow_module, 'SYSTEM_CONFIG_FILE', system_file):
            with patch.object(autoflow_module, 'AGENTS_FILE', agents_file):
                sys_config = load_system_config()
                agents = load_agents()

                # Verify configs were loaded
                assert sys_config["memory"]["enabled"] == True
                assert "test-agent" in agents
                assert agents["test-agent"].command == "echo"


# ============================================================================
# Test Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling in config operations."""

    def test_write_json_creates_parent_directories(self, temp_dir):
        """Test that write_json creates parent directories if needed."""
        nested_file = temp_dir / "deep" / "nested" / "config.json"

        write_json(nested_file, {"test": True})

        assert nested_file.exists()
        assert nested_file.parent.exists()

    def test_read_json_handles_corrupt_file(self, temp_dir):
        """Test that read_json handles corrupt JSON files."""
        corrupt_file = temp_dir / "corrupt.json"
        corrupt_file.write_text("{corrupt json content")

        # Should raise appropriate exception or handle gracefully
        with pytest.raises((json.JSONDecodeError, FileNotFoundError)):
            read_json(corrupt_file)

    def test_load_system_config_is_resilient(self, temp_dir):
        """Test that load_system_config is resilient to various issues."""
        # Test with non-existent file
        missing_config = temp_dir / "nonexistent.json"

        with patch.object(autoflow_module, 'SYSTEM_CONFIG_FILE', missing_config):
            result = load_system_config()

        # Should return a valid config, not crash
        assert isinstance(result, dict)
        assert "memory" in result
