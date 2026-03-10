"""
Unit Tests for Autoflow CLI Memory Commands

Tests the memory command functionality including listing, getting,
setting, and deleting memory entries.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from autoflow.cli.memory import memory
from autoflow.core.config import Config
from autoflow.core.state import StateManager


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / ".autoflow"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def state_manager(temp_state_dir: Path) -> StateManager:
    """Create a StateManager instance with temporary directory."""
    manager = StateManager(temp_state_dir)
    manager.initialize()
    return manager


@pytest.fixture
def sample_config(temp_state_dir: Path) -> Config:
    """Create a sample config for testing."""
    return Config(state_dir=str(temp_state_dir))


# ============================================================================
# Memory List Command Tests - Basic Functionality
# ============================================================================


class TestMemoryListBasic:
    """Tests for memory list command basic functionality."""

    def test_memory_list_displays_header(self, runner: CliRunner, sample_config: Config) -> None:
        """Test memory list displays proper header."""
        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Memory Entries" in result.output
        assert "=" * 60 in result.output

    def test_memory_list_empty(self, runner: CliRunner, sample_config: Config) -> None:
        """Test memory list with no entries."""
        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "No memory entries found" in result.output

    def test_memory_list_short_flag(self, runner: CliRunner, sample_config: Config) -> None:
        """Test memory list with -c short flag."""
        result = runner.invoke(
            memory,
            ["list", "-c", "general"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0

    def test_memory_list_without_config(self, runner: CliRunner) -> None:
        """Test memory list fails without config."""
        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Configuration not loaded" in result.output


# ============================================================================
# Memory List Command Tests - With Data
# ============================================================================


class TestMemoryListWithData:
    """Tests for memory list command with actual data."""

    def test_memory_list_shows_entries(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list shows memory entries."""
        state_manager.save_memory("key1", "value1", category="general")
        state_manager.save_memory("key2", "value2", category="git")

        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "key1" in result.output
        assert "key2" in result.output

    def test_memory_list_shows_category(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list shows category."""
        state_manager.save_memory("test_key", "test_value", category="project")

        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Category: project" in result.output

    def test_memory_list_shows_created_at(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list shows created timestamp."""
        state_manager.save_memory("test_key", "test_value")

        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Created:" in result.output


# ============================================================================
# Memory List Command Tests - Category Filter
# ============================================================================


class TestMemoryListCategory:
    """Tests for memory list command category filtering."""

    def test_memory_list_filter_by_category(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list filters by category."""
        state_manager.save_memory("key1", "value1", category="git")
        state_manager.save_memory("key2", "value2", category="project")
        state_manager.save_memory("key3", "value3", category="git")

        result = runner.invoke(
            memory,
            ["list", "--category", "git"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "key1" in result.output
        assert "key3" in result.output
        assert "key2" not in result.output

    def test_memory_list_filter_nonexistent_category(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list with nonexistent category."""
        state_manager.save_memory("key1", "value1", category="git")

        result = runner.invoke(
            memory,
            ["list", "--category", "nonexistent"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "No memory entries found" in result.output

    def test_memory_list_no_filter_shows_all(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list without category filter shows all."""
        state_manager.save_memory("key1", "value1", category="git")
        state_manager.save_memory("key2", "value2", category="project")

        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "key1" in result.output
        assert "key2" in result.output


# ============================================================================
# Memory List Command Tests - JSON Output
# ============================================================================


class TestMemoryListJSON:
    """Tests for memory list command JSON output."""

    def test_memory_list_json_output(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list returns valid JSON."""
        state_manager.save_memory("key1", "value1")

        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "memories" in output
        assert "count" in output

    def test_memory_list_json_with_entries(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list JSON includes entries."""
        state_manager.save_memory("key1", "value1")
        state_manager.save_memory("key2", "value2")

        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["count"] == 2
        assert len(output["memories"]) == 2

    def test_memory_list_json_empty(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory list JSON with no entries."""
        result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["count"] == 0
        assert output["memories"] == []

    def test_memory_list_json_with_category_filter(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list JSON filters by category."""
        state_manager.save_memory("key1", "value1", category="git")
        state_manager.save_memory("key2", "value2", category="project")

        result = runner.invoke(
            memory,
            ["list", "--category", "git"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["count"] == 1
        assert output["memories"][0]["category"] == "git"


# ============================================================================
# Memory Get Command Tests
# ============================================================================


class TestMemoryGet:
    """Tests for memory get command."""

    def test_memory_get_existing(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory get retrieves existing entry."""
        state_manager.save_memory("test_key", "test_value")

        result = runner.invoke(
            memory,
            ["get", "test_key"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "test_key: test_value" in result.output

    def test_memory_get_nonexistent(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory get fails for nonexistent key."""
        result = runner.invoke(
            memory,
            ["get", "nonexistent_key"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_memory_get_json(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory get returns valid JSON."""
        state_manager.save_memory("test_key", {"nested": "data"})

        result = runner.invoke(
            memory,
            ["get", "test_key"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["key"] == "test_key"
        assert output["value"] == {"nested": "data"}

    def test_memory_get_without_config(self, runner: CliRunner) -> None:
        """Test memory get fails without config."""
        result = runner.invoke(
            memory,
            ["get", "test_key"],
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Configuration not loaded" in result.output


# ============================================================================
# Memory Set Command Tests
# ============================================================================


class TestMemorySet:
    """Tests for memory set command."""

    def test_memory_set_simple_value(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory set with simple string value."""
        result = runner.invoke(
            memory,
            ["set", "test_key", "test_value"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Saved: test_key = test_value" in result.output

    def test_memory_set_with_category(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory set with custom category."""
        result = runner.invoke(
            memory,
            ["set", "test_key", "test_value", "--category", "project"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Saved: test_key = test_value" in result.output

    def test_memory_set_category_short_flag(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory set with -c short flag."""
        result = runner.invoke(
            memory,
            ["set", "test_key", "test_value", "-c", "git"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Saved: test_key = test_value" in result.output

    def test_memory_set_default_category(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory set uses 'general' as default category."""
        runner.invoke(
            memory,
            ["set", "test_key", "test_value"],
            obj={"config": sample_config, "output_json": False},
        )

        # Verify the category was set to 'general'
        memories = state_manager.list_memory(category="general")
        assert len(memories) == 1
        assert memories[0]["key"] == "test_key"

    def test_memory_set_json(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory set returns JSON confirmation."""
        result = runner.invoke(
            memory,
            ["set", "test_key", "test_value", "-c", "workflow"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["key"] == "test_key"
        assert output["value"] == "test_value"
        assert output["category"] == "workflow"
        assert output["status"] == "saved"

    def test_memory_set_without_config(self, runner: CliRunner) -> None:
        """Test memory set fails without config."""
        result = runner.invoke(
            memory,
            ["set", "test_key", "test_value"],
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Configuration not loaded" in result.output

    def test_memory_set_overwrites_existing(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory set overwrites existing entry."""
        state_manager.save_memory("test_key", "old_value")

        result = runner.invoke(
            memory,
            ["set", "test_key", "new_value"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0

        # Verify it was updated
        value = state_manager.load_memory("test_key")
        assert value == "new_value"


# ============================================================================
# Memory Delete Command Tests
# ============================================================================


class TestMemoryDelete:
    """Tests for memory delete command."""

    def test_memory_delete_existing(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory delete removes existing entry."""
        state_manager.save_memory("to_delete", "value")

        result = runner.invoke(
            memory,
            ["delete", "to_delete"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Deleted: to_delete" in result.output
        assert state_manager.load_memory("to_delete") is None

    def test_memory_delete_nonexistent(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory delete fails for nonexistent key."""
        result = runner.invoke(
            memory,
            ["delete", "nonexistent_key"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_memory_delete_json(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory delete returns JSON confirmation."""
        state_manager.save_memory("to_delete", "value")

        result = runner.invoke(
            memory,
            ["delete", "to_delete"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["key"] == "to_delete"
        assert output["status"] == "deleted"

    def test_memory_delete_without_config(self, runner: CliRunner) -> None:
        """Test memory delete fails without config."""
        result = runner.invoke(
            memory,
            ["delete", "test_key"],
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Configuration not loaded" in result.output


# ============================================================================
# Memory Command Tests - Integration
# ============================================================================


class TestMemoryIntegration:
    """Tests for memory command integration with StateManager."""

    def test_memory_set_then_get(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory set then get round trip."""
        # Set a value
        set_result = runner.invoke(
            memory,
            ["set", "test_key", "test_value"],
            obj={"config": sample_config, "output_json": False},
        )
        assert set_result.exit_code == 0

        # Get the value
        get_result = runner.invoke(
            memory,
            ["get", "test_key"],
            obj={"config": sample_config, "output_json": False},
        )
        assert get_result.exit_code == 0
        assert "test_value" in get_result.output

    def test_memory_set_then_list(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory set then list shows entry."""
        # Set a value
        runner.invoke(
            memory,
            ["set", "test_key", "test_value"],
            obj={"config": sample_config, "output_json": False},
        )

        # List entries
        list_result = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": False},
        )
        assert list_result.exit_code == 0
        assert "test_key" in list_result.output

    def test_memory_set_then_delete(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory set then delete removes entry."""
        # Set a value
        runner.invoke(
            memory,
            ["set", "test_key", "test_value"],
            obj={"config": sample_config, "output_json": False},
        )

        # Delete the value
        delete_result = runner.invoke(
            memory,
            ["delete", "test_key"],
            obj={"config": sample_config, "output_json": False},
        )
        assert delete_result.exit_code == 0

        # Verify it's gone
        get_result = runner.invoke(
            memory,
            ["get", "test_key"],
            obj={"config": sample_config, "output_json": False},
        )
        assert get_result.exit_code == 1

    def test_memory_with_special_characters(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory with special characters in value."""
        result = runner.invoke(
            memory,
            ["set", "test_key", "value with spaces and - dashes"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0


# ============================================================================
# Memory Command Tests - Edge Cases
# ============================================================================


class TestMemoryEdgeCases:
    """Tests for memory command edge cases."""

    def test_memory_list_consistency(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory list output is consistent."""
        state_manager.save_memory("key1", "value1")

        result1 = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": True},
        )
        result2 = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert result1.output == result2.output

    def test_memory_with_different_categories(
        self, runner: CliRunner, sample_config: Config, state_manager: StateManager
    ) -> None:
        """Test memory with multiple categories."""
        state_manager.save_memory("key1", "value1", category="git")
        state_manager.save_memory("key2", "value2", category="project")
        state_manager.save_memory("key3", "value3", category="docker")

        # List all
        result_all = runner.invoke(
            memory,
            ["list"],
            obj={"config": sample_config, "output_json": False},
        )
        assert result_all.exit_code == 0
        assert "key1" in result_all.output
        assert "key2" in result_all.output
        assert "key3" in result_all.output

        # Filter by category
        result_git = runner.invoke(
            memory,
            ["list", "--category", "git"],
            obj={"config": sample_config, "output_json": False},
        )
        assert result_git.exit_code == 0
        assert "key1" in result_git.output
        assert "key2" not in result_git.output

    def test_memory_get_after_category_change(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test memory get after changing category."""
        # Set with one category
        runner.invoke(
            memory,
            ["set", "test_key", "value1", "-c", "git"],
            obj={"config": sample_config, "output_json": False},
        )

        # Update with different category
        runner.invoke(
            memory,
            ["set", "test_key", "value2", "-c", "project"],
            obj={"config": sample_config, "output_json": False},
        )

        # Get should return updated value
        result = runner.invoke(
            memory,
            ["get", "test_key"],
            obj={"config": sample_config, "output_json": False},
        )
        assert result.exit_code == 0
        assert "value2" in result.output
