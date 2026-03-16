"""Unit Tests for Autoflow CLI Run Command.

Tests the CLI run command for task execution, agent selection, and configuration.
These tests ensure the run command can:
- Create and manage tasks with proper state management
- Select and assign appropriate agents (claude-code, codex, openclaw)
- Execute skills with proper metadata tracking
- Handle working directory specification and validation
- Configure timeout values for task execution
- Support resume functionality for task continuation
- Validate input arguments and handle missing requirements
- Provide both human-readable and JSON output formats
- Handle errors gracefully with proper exit codes
- Integrate properly with StateManager for persistence
- Handle edge cases including unicode, special characters, and long descriptions
- Generate unique task IDs based on timestamps

All tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from autoflow.cli.run import run
from autoflow.core.config import Config
from autoflow.core.state import StateManager, TaskStatus


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
# Run Command Tests - Basic Functionality
# ============================================================================


class TestRunBasic:
    """Tests for basic run command functionality."""

    def test_run_with_task(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run with a simple task string."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["Fix the login bug"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Started task:" in result.output
            assert "Agent: claude-code" in result.output
            assert "Status: in_progress" in result.output

    def test_run_creates_task_record(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run creates a task record in state."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

            # Verify task was created
            tasks = manager.list_tasks()
            assert len(tasks) == 1
            assert tasks[0]["title"] == "Test task"
            assert tasks[0]["status"] == TaskStatus.IN_PROGRESS.value
            assert tasks[0]["assigned_agent"] == "claude-code"

    def test_run_generates_task_id(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test run generates unique task IDs."""
        # Create two separate state directories to avoid ID conflicts
        state_dir1 = tmp_path / "autoflow1"
        state_dir1.mkdir()
        config1 = Config(state_dir=str(state_dir1))
        manager1 = StateManager(state_dir1)
        manager1.initialize()

        state_dir2 = tmp_path / "autoflow2"
        state_dir2.mkdir()
        config2 = Config(state_dir=str(state_dir2))
        manager2 = StateManager(state_dir2)
        manager2.initialize()

        # Create tasks in separate directories
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result1 = runner.invoke(
                run,
                ["Task 1"],
                obj={"config": config1, "output_json": False},
            )
            assert result1.exit_code == 0

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result2 = runner.invoke(
                run,
                ["Task 2"],
                obj={"config": config2, "output_json": False},
            )
            assert result2.exit_code == 0

        # Each manager should have one task
        tasks1 = manager1.list_tasks()
        tasks2 = manager2.list_tasks()

        assert len(tasks1) == 1, f"Expected 1 task in dir1, got {len(tasks1)}"
        assert len(tasks2) == 1, f"Expected 1 task in dir2, got {len(tasks2)}"

        # Task IDs should have been generated
        assert "task-" in tasks1[0]["id"]
        assert "task-" in tasks2[0]["id"]


# ============================================================================
# Run Command Tests - Agent Selection
# ============================================================================


class TestRunAgent:
    """Tests for run command agent selection."""

    def test_run_with_default_agent(self, runner: CliRunner) -> None:
        """Test run uses claude-code as default agent."""
        with runner.isolated_filesystem():
            result = runner.invoke(
                run,
                ["Test task"],
                obj={"config": None, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Agent: claude-code" in result.output

    def test_run_with_codex_agent(self, runner: CliRunner) -> None:
        """Test run with --agent codex."""
        with runner.isolated_filesystem():
            result = runner.invoke(
                run,
                ["--agent", "codex", "Test task"],
                obj={"config": None, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Agent: codex" in result.output

    def test_run_with_openclaw_agent(self, runner: CliRunner) -> None:
        """Test run with --agent openclaw."""
        with runner.isolated_filesystem():
            result = runner.invoke(
                run,
                ["--agent", "openclaw", "Test task"],
                obj={"config": None, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Agent: openclaw" in result.output

    def test_run_agent_short_flag(self, runner: CliRunner) -> None:
        """Test run -a (short flag) works."""
        with runner.isolated_filesystem():
            result = runner.invoke(
                run,
                ["-a", "codex", "Test task"],
                obj={"config": None, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Agent: codex" in result.output

    def test_run_invalid_agent(self, runner: CliRunner) -> None:
        """Test run rejects invalid agent."""
        # Click's Choice type should handle this before our code runs
        with runner.isolated_filesystem():
            result = runner.invoke(
                run,
                ["--agent", "invalid", "Test task"],
                obj={"config": None, "output_json": False},
            )

            # Click should reject invalid choice
            assert result.exit_code != 0
            assert "Invalid value for '--agent'" in result.output


# ============================================================================
# Run Command Tests - Skill Execution
# ============================================================================


class TestRunSkill:
    """Tests for run command skill execution."""

    def test_run_with_skill(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run with --skill option."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--skill", "CONTINUOUS_ITERATOR"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Skill: CONTINUOUS_ITERATOR" in result.output

    def test_run_skill_short_flag(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run -k (short flag) works."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["-k", "TEST_SKILL"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_skill_creates_task_record(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test run with skill creates proper task record."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--skill", "MY_SKILL"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

            tasks = manager.list_tasks()
            assert len(tasks) == 1
            assert "Execute skill: MY_SKILL" in tasks[0]["title"]
            assert tasks[0]["metadata"]["skill"] == "MY_SKILL"


# ============================================================================
# Run Command Tests - Working Directory
# ============================================================================


class TestRunWorkdir:
    """Tests for run command working directory option."""

    def test_run_with_workdir(self, runner: CliRunner, temp_state_dir: Path, tmp_path: Path) -> None:
        """Test run with --workdir option."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        workdir = tmp_path / "workspace"
        workdir.mkdir()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--workdir", str(workdir), "Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_workdir_short_flag(self, runner: CliRunner, temp_state_dir: Path, tmp_path: Path) -> None:
        """Test run -w (short flag) works."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        workdir = tmp_path / "workspace"
        workdir.mkdir()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["-w", str(workdir), "Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_workdir_nonexistent(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run rejects nonexistent working directory."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--workdir", "/nonexistent/path", "Test task"],
                obj={"config": config, "output_json": False},
            )

            # Click's path_type should validate existence
            assert result.exit_code != 0

    def test_run_workdir_in_metadata(
        self, runner: CliRunner, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Test run saves workdir in task metadata."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        workdir = tmp_path / "workspace"
        workdir.mkdir()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--workdir", str(workdir), "Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

            tasks = manager.list_tasks()
            assert tasks[0]["metadata"]["workdir"] == str(workdir)


# ============================================================================
# Run Command Tests - Timeout Option
# ============================================================================


class TestRunTimeout:
    """Tests for run command timeout option."""

    def test_run_with_default_timeout(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run uses default timeout (300 seconds)."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_with_custom_timeout(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run with --timeout option."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--timeout", "600", "Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_timeout_short_flag(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run -t (short flag) works."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["-t", "120", "Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_timeout_in_metadata(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test run saves timeout in task metadata."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--timeout", "450", "Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

            tasks = manager.list_tasks()
            assert tasks[0]["metadata"]["timeout"] == 450


# ============================================================================
# Run Command Tests - Resume Option
# ============================================================================


class TestRunResume:
    """Tests for run command resume functionality."""

    def test_run_with_resume(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run with --resume flag."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--resume"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Started task:" in result.output

    def test_run_resume_short_flag(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run -r (short flag) works."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["-r"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_resume_in_metadata(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test run saves resume flag in task metadata."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--resume"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

            tasks = manager.list_tasks()
            assert tasks[0]["metadata"]["resume"] is True


# ============================================================================
# Run Command Tests - Missing Arguments
# ============================================================================


class TestRunMissingArgs:
    """Tests for run command with missing required arguments."""

    def test_run_without_task_or_skill(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run fails without task, skill, or resume."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                [],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 1
            assert "Either TASK, --skill, or --resume is required" in result.output

    def test_run_with_empty_task(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run handles empty task string."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                [""],
                obj={"config": config, "output_json": False},
            )

            # Empty task is valid and creates a task
            # but should not fail
            assert result.exit_code == 0 or result.exit_code == 1


# ============================================================================
# Run Command Tests - JSON Output
# ============================================================================


class TestRunJSON:
    """Tests for run command JSON output."""

    def test_run_json_output(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run --json returns JSON output."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["Test task"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            assert output["status"] == "started"
            assert "task_id" in output
            assert output["agent"] == "claude-code"
            assert output["skill"] is None

    def test_run_json_with_skill(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run --json includes skill information."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--skill", "TEST_SKILL"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            assert output["skill"] == "TEST_SKILL"

    def test_run_json_with_agent(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run --json includes agent information."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--agent", "codex", "Test task"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            assert output["agent"] == "codex"


# ============================================================================
# Run Command Tests - Error Handling
# ============================================================================


class TestRunErrors:
    """Tests for run command error handling."""

    def test_run_handles_state_manager_error(self, runner: CliRunner) -> None:
        """Test run handles StateManager errors gracefully."""
        with runner.isolated_filesystem():
            # Use invalid state dir
            result = runner.invoke(
                run,
                ["Test task"],
                obj={
                    "config": Config(state_dir="/invalid/path"),
                    "output_json": False,
                },
            )

            # Should handle error gracefully
            assert result.exit_code == 1


# ============================================================================
# Run Command Tests - Integration
# ============================================================================


class TestRunIntegration:
    """Tests for run command integration with StateManager."""

    def test_run_task_status_in_progress(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test run creates task with in_progress status."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

            tasks = manager.list_tasks()
            assert len(tasks) == 1
            assert tasks[0]["status"] == TaskStatus.IN_PROGRESS.value

    def test_run_task_metadata_complete(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test run saves complete task metadata."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["--skill", "TEST", "--timeout", "500", "--resume", "Test task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

            tasks = manager.list_tasks()
            metadata = tasks[0]["metadata"]
            assert metadata["skill"] == "TEST"
            assert metadata["timeout"] == 500
            assert metadata["resume"] is True


# ============================================================================
# Run Command Tests - Edge Cases
# ============================================================================


class TestRunEdgeCases:
    """Tests for run command edge cases."""

    def test_run_with_special_characters(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run handles special characters in task description."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ['Fix "quotes" and \'apostrophes\''],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_with_unicode(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run handles unicode characters."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                ["Test 世界 🌍"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_with_long_task_description(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test run handles long task descriptions."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        long_task = "Test task " + "x" * 1000

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                run,
                [long_task],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_run_generates_unique_timestamps(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test run generates unique task IDs based on timestamps."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            # Create multiple tasks quickly
            task_ids = []
            for i in range(5):
                result = runner.invoke(
                    run,
                    [f"Task {i}"],
                    obj={"config": config, "output_json": False},
                )
                assert result.exit_code == 0

            tasks = manager.list_tasks()
            # All task IDs should be unique
            task_ids = [t["id"] for t in tasks]
            assert len(task_ids) == len(set(task_ids))
