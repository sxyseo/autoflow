"""
Unit Tests for Autoflow CLI Task Commands

Tests the task list and show commands for task management.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from autoflow.cli.task import task, task_list, task_show
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


@pytest.fixture
def sample_tasks() -> list[dict[str, Any]]:
    """Return sample task data for testing."""
    return [
        {
            "id": "task-001",
            "title": "Test Task 1",
            "description": "First test task",
            "status": "pending",
            "priority": 5,
            "assigned_agent": "claude-code",
        },
        {
            "id": "task-002",
            "title": "Test Task 2",
            "description": "Second test task",
            "status": "in_progress",
            "priority": 8,
            "assigned_agent": "codex",
        },
        {
            "id": "task-003",
            "title": "Test Task 3",
            "description": "Third test task",
            "status": "completed",
            "priority": 3,
            "assigned_agent": "claude-code",
        },
    ]


# ============================================================================
# Task List Command Tests - Basic Functionality
# ============================================================================


class TestTaskListBasic:
    """Tests for basic task list command functionality."""

    def test_task_list_displays_header(self, runner: CliRunner) -> None:
        """Test task list displays proper header."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(
                task_list,
                obj={"config": Config(state_dir=str(state_dir)), "output_json": False},
            )

            assert result.exit_code == 0
            assert "Tasks" in result.output
            assert "=" * 60 in result.output

    def test_task_list_with_no_tasks(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task list with no tasks shows appropriate message."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "No tasks found." in result.output

    def test_task_list_shows_tasks(self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list) -> None:
        """Test task list displays tasks."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        # Add sample tasks
        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "task-001" in result.output
            assert "Test Task 1" in result.output
            assert "task-002" in result.output
            assert "Test Task 2" in result.output

    def test_task_list_shows_task_details(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task list shows task status and agent."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test Task",
            "status": "pending",
            "assigned_agent": "claude-code",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Status: pending" in result.output
            assert "Agent: claude-code" in result.output


# ============================================================================
# Task List Command Tests - Filtering
# ============================================================================


class TestTaskListFilters:
    """Tests for task list command filtering options."""

    def test_task_list_filter_by_status_pending(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list --status pending filters correctly."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["--status", "pending"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "task-001" in result.output
            assert "task-002" not in result.output
            assert "task-003" not in result.output

    def test_task_list_filter_by_status_in_progress(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list --status in_progress filters correctly."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["--status", "in_progress"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "task-001" not in result.output
            assert "task-002" in result.output
            assert "task-003" not in result.output

    def test_task_list_filter_by_status_completed(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list --status completed filters correctly."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["--status", "completed"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "task-001" not in result.output
            assert "task-002" not in result.output
            assert "task-003" in result.output

    def test_task_list_filter_by_agent(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list --agent filters correctly."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["--agent", "claude-code"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "task-001" in result.output
            assert "task-002" not in result.output
            assert "task-003" in result.output

    def test_task_list_filter_by_status_and_agent(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list with both status and agent filters."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["--status", "completed", "--agent", "claude-code"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            # Only task-003 matches both filters
            assert "task-001" not in result.output
            assert "task-002" not in result.output
            assert "task-003" in result.output

    def test_task_list_limit(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list --limit limits results."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["--limit", "2"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            # Should show only 2 tasks
            lines = result.output.split("\n")
            task_lines = [l for l in lines if "[task-" in l]
            assert len(task_lines) == 2

    def test_task_list_short_flags(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list short flags work."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["-s", "pending", "-a", "claude-code", "-l", "10"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "task-001" in result.output


# ============================================================================
# Task List Command Tests - JSON Output
# ============================================================================


class TestTaskListJSON:
    """Tests for task list --json functionality."""

    def test_task_list_json_output(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task list returns valid JSON."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            output = json.loads(result.output)
            assert "tasks" in output
            assert "count" in output
            assert output["count"] == 0

    def test_task_list_json_with_tasks(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list --json includes actual tasks."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            output = json.loads(result.output)
            assert output["count"] == 3
            assert len(output["tasks"]) == 3

    def test_task_list_json_with_filters(
        self, runner: CliRunner, temp_state_dir: Path, sample_tasks: list
    ) -> None:
        """Test task list --json respects filters."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        for task_data in sample_tasks:
            manager.save_task(task_data["id"], task_data)

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["--status", "pending"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            output = json.loads(result.output)
            assert output["count"] == 1
            assert output["tasks"][0]["id"] == "task-001"


# ============================================================================
# Task Show Command Tests - Basic Functionality
# ============================================================================


class TestTaskShowBasic:
    """Tests for basic task show command functionality."""

    def test_task_show_displays_task(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task show displays task details."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test Task",
            "description": "A test task",
            "status": "pending",
            "assigned_agent": "claude-code",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_show,
                ["task-001"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Task: task-001" in result.output
            assert "Title: Test Task" in result.output
            assert "Description: A test task" in result.output
            assert "Status: pending" in result.output
            assert "Agent: claude-code" in result.output

    def test_task_show_with_nonexistent_task(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task show with nonexistent task returns error."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_show,
                ["nonexistent-task"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_task_show_displays_timestamps(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task show displays created and updated timestamps."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test Task",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_show,
                ["task-001"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Created:" in result.output
            assert "Updated:" in result.output


# ============================================================================
# Task Show Command Tests - JSON Output
# ============================================================================


class TestTaskShowJSON:
    """Tests for task show --json functionality."""

    def test_task_show_json_output(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task show returns valid JSON."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test Task",
            "description": "A test task",
            "status": "pending",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_show,
                ["task-001"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            output = json.loads(result.output)
            assert output["id"] == "task-001"
            assert output["title"] == "Test Task"
            assert output["description"] == "A test task"
            assert output["status"] == "pending"

    def test_task_show_json_nonexistent(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task show --json with nonexistent task returns error."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_show,
                ["nonexistent"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 1
            assert "not found" in result.output


# ============================================================================
# Task Command Tests - Error Handling
# ============================================================================


class TestTaskErrors:
    """Tests for task command error handling."""

    def test_task_list_without_config(self, runner: CliRunner) -> None:
        """Test task list without config returns error."""
        result = runner.invoke(
            task_list,
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Configuration not loaded" in result.output

    def test_task_show_without_config(self, runner: CliRunner) -> None:
        """Test task show without config returns error."""
        result = runner.invoke(
            task_show,
            ["task-001"],
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Configuration not loaded" in result.output


# ============================================================================
# Task Command Tests - Integration
# ============================================================================


class TestTaskIntegration:
    """Tests for task command integration with StateManager."""

    def test_task_list_matches_state_manager(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test task list matches StateManager.list_tasks()."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        # Add tasks via StateManager
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Task 1",
            "status": "pending",
        })
        manager.save_task("task-002", {
            "id": "task-002",
            "title": "Task 2",
            "status": "in_progress",
        })

        # Get tasks via StateManager
        expected_tasks = manager.list_tasks()

        # Get tasks via CLI (JSON output for easier comparison)
        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            output = json.loads(result.output)
            assert output["count"] == len(expected_tasks)

    def test_task_show_matches_state_manager(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test task show matches StateManager.load_task()."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        # Add task via StateManager
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test Task",
            "status": "pending",
        })

        # Get task via StateManager
        expected_task = manager.load_task("task-001")

        # Get task via CLI (JSON output)
        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_show,
                ["task-001"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            output = json.loads(result.output)
            assert output["id"] == expected_task["id"]
            assert output["title"] == expected_task["title"]


# ============================================================================
# Task Command Tests - Edge Cases
# ============================================================================


class TestTaskEdgeCases:
    """Tests for task command edge cases."""

    def test_task_list_with_unicode(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task list handles unicode characters."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "测试任务",  # Chinese characters
            "description": "Test with emoji 🚀",
            "status": "pending",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            output = json.loads(result.output)
            assert output["tasks"][0]["title"] == "测试任务"

    def test_task_show_with_unicode(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task show handles unicode characters."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Tâche de test",  # French with accent
            "description": "Test avec émojis 🎉",
            "status": "pending",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_show,
                ["task-001"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            # Should display unicode without errors

    def test_task_list_with_many_tasks(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task list handles many tasks efficiently."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        # Create 50 tasks
        for i in range(50):
            manager.save_task(f"task-{i:03d}", {
                "id": f"task-{i:03d}",
                "title": f"Task {i}",
                "status": "pending",
            })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_list,
                ["--limit", "100"],  # Increase limit to see all tasks
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            output = json.loads(result.output)
            assert output["count"] == 50

    def test_task_list_with_empty_description(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test task show with empty description."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test Task",
            "description": "",
            "status": "pending",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                task_show,
                ["task-001"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            # Empty description is shown as empty string, not N/A
            assert "Description:" in result.output
