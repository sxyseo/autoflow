"""
Unit Tests for Autoflow CLI Status Command

Tests the status command functionality including basic status,
detailed view, and JSON output modes.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from autoflow.cli.status import status
from autoflow.core.config import Config
from autoflow.core.state import StateManager, TaskStatus, RunStatus


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
# Status Command Tests - Basic Functionality
# ============================================================================


class TestStatusBasic:
    """Tests for basic status command functionality."""

    def test_status_displays_header(self, runner: CliRunner) -> None:
        """Test status displays proper header."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(status, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "Autoflow Status" in result.output
            assert "=" * 50 in result.output

    def test_status_shows_state_dir(self, runner: CliRunner) -> None:
        """Test status shows state directory path."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(status, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "State Directory:" in result.output

    def test_status_shows_initialized(self, runner: CliRunner) -> None:
        """Test status shows initialized status."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(status, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "Initialized:" in result.output

    def test_status_with_no_data(self, runner: CliRunner) -> None:
        """Test status with empty state shows zeros."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(status, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "Tasks: 0 total" in result.output
            assert "Runs: 0 total" in result.output
            assert "Specs: 0 total" in result.output
            assert "Memory Entries: 0 total" in result.output


# ============================================================================
# Status Command Tests - With Data
# ============================================================================


class TestStatusWithData:
    """Tests for status command with actual data."""

    def test_status_with_tasks(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status shows task counts."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test Task",
            "status": "pending",
        })
        manager.save_task("task-002", {
            "id": "task-002",
            "title": "Another Task",
            "status": "in_progress",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Tasks: 2 total" in result.output

    def test_status_with_runs(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status shows run counts."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_run("run-001", {
            "id": "run-001",
            "agent": "claude-code",
            "status": "running",
        })
        manager.save_run("run-002", {
            "id": "run-002",
            "agent": "codex",
            "status": "completed",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Runs: 2 total" in result.output

    def test_status_with_specs(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status shows spec counts."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_spec("spec-001", {
            "id": "spec-001",
            "title": "Test Spec",
            "content": "Content",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Specs: 1 total" in result.output

    def test_status_with_memory(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status shows memory entry counts."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_memory("test_key", "test_value")
        manager.save_memory("another_key", {"nested": "data"})

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Memory Entries: 2 total" in result.output


# ============================================================================
# Status Command Tests - Detailed Option
# ============================================================================


class TestStatusDetailed:
    """Tests for status --detailed functionality."""

    def test_status_detailed_shows_task_breakdown(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status --detailed shows task status breakdown."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Pending Task",
            "status": "pending",
        })
        manager.save_task("task-002", {
            "id": "task-002",
            "title": "In Progress Task",
            "status": "in_progress",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                ["--detailed"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            # Should show status breakdown
            assert "pending:" in result.output or "in_progress:" in result.output

    def test_status_detailed_shows_run_breakdown(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status --detailed shows run status breakdown."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_run("run-001", {
            "id": "run-001",
            "agent": "claude-code",
            "status": "running",
        })
        manager.save_run("run-002", {
            "id": "run-002",
            "agent": "claude-code",
            "status": "completed",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                ["--detailed"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            # Should show status breakdown
            assert "running:" in result.output or "completed:" in result.output

    def test_status_detailed_short_flag(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status -d (short flag) works."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test",
            "status": "pending",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                ["-d"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_status_detailed_shows_config(self, runner: CliRunner) -> None:
        """Test status --detailed shows configuration section."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            config = Config()

            result = runner.invoke(
                status,
                ["--detailed"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Configuration:" in result.output
            assert "OpenClaw Gateway:" in result.output
            assert "State Directory:" in result.output
            assert "Scheduler Enabled:" in result.output
            assert "CI Gates Required:" in result.output


# ============================================================================
# Status Command Tests - JSON Output
# ============================================================================


class TestStatusJSON:
    """Tests for status --json functionality."""

    def test_status_json_output(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status --json returns valid JSON."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            # Parse JSON
            import json

            output = json.loads(result.output)
            assert "state_dir" in output
            assert "initialized" in output
            assert "tasks" in output
            assert "runs" in output
            assert "specs" in output
            assert "memory" in output

    def test_status_json_with_data(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status --json includes actual data."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test",
            "status": "pending",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            assert output["tasks"]["total"] == 1
            assert output["initialized"] is True

    def test_status_json_structure(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status --json has proper structure."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)

            # Check tasks structure
            assert "total" in output["tasks"]
            assert "by_status" in output["tasks"]

            # Check runs structure
            assert "total" in output["runs"]
            assert "by_status" in output["runs"]

            # Check specs structure
            assert "total" in output["specs"]

            # Check memory structure
            assert "total" in output["memory"]


# ============================================================================
# Status Command Tests - Error Handling
# ============================================================================


class TestStatusErrors:
    """Tests for status command error handling."""

    def test_status_with_uninitialized_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test status handles uninitialized state directory."""
        state_dir = tmp_path / ".autoflow"

        with runner.isolated_filesystem():
            result = runner.invoke(
                status,
                obj={"config": Config(state_dir=str(state_dir)), "output_json": False},
            )

            # Should still work, just show 0 counts
            assert result.exit_code == 0


# ============================================================================
# Status Command Tests - Integration
# ============================================================================


class TestStatusIntegration:
    """Tests for status command integration with StateManager."""

    def test_status_matches_state_manager(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status output matches StateManager.get_status()."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        # Add some data
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test",
            "status": "pending",
        })
        manager.save_run("run-001", {
            "id": "run-001",
            "agent": "claude-code",
            "status": "running",
        })

        # Get status from StateManager
        expected = manager.get_status()

        # Get status from CLI
        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)

            # Should match
            assert output["tasks"]["total"] == expected["tasks"]["total"]
            assert output["runs"]["total"] == expected["runs"]["total"]

    def test_status_with_multiple_tasks_by_status(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status correctly counts tasks by status."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Pending 1",
            "status": "pending",
        })
        manager.save_task("task-002", {
            "id": "task-002",
            "title": "Pending 2",
            "status": "pending",
        })
        manager.save_task("task-003", {
            "id": "task-003",
            "title": "In Progress",
            "status": "in_progress",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            assert output["tasks"]["total"] == 3
            assert output["tasks"]["by_status"]["pending"] == 2
            assert output["tasks"]["by_status"]["in_progress"] == 1


# ============================================================================
# Status Command Tests - Edge Cases
# ============================================================================


class TestStatusEdgeCases:
    """Tests for status command edge cases."""

    def test_status_with_custom_state_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test status works with custom state directory."""
        custom_dir = tmp_path / "custom_autoflow"
        custom_dir.mkdir()
        config = Config(state_dir=str(custom_dir))
        manager = StateManager(custom_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert str(custom_dir) in result.output

    def test_status_consistency(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status output is consistent across calls."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result1 = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )
            result2 = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result1.exit_code == 0
            assert result2.exit_code == 0
            assert result1.output == result2.output

    def test_status_with_complex_data(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status with complex nested data."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_memory("complex", {
            "nested": {
                "deep": {
                    "value": 42,
                    "list": [1, 2, 3],
                }
            }
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0
            assert "memory" in result.output
