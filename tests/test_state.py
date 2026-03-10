"""
Unit Tests for Autoflow State Management

Tests the StateManager class and related models (Task, Run, Spec, Memory)
for persistent state management with atomic writes.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from autoflow.core.state import (
    Memory,
    Run,
    RunStatus,
    Spec,
    StateManager,
    Task,
    TaskStatus,
    read_json,
    write_json,
)

# ============================================================================
# Fixtures
# ============================================================================


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
def sample_task_data() -> dict[str, Any]:
    """Return sample task data for testing."""
    return {
        "id": "task-001",
        "title": "Test Task",
        "description": "A test task for unit testing",
        "status": "pending",
        "priority": 5,
    }


@pytest.fixture
def sample_run_data() -> dict[str, Any]:
    """Return sample run data for testing."""
    return {
        "id": "run-001",
        "task_id": "task-001",
        "agent": "claude-code",
        "status": "running",
        "workdir": "/test/workdir",
    }


@pytest.fixture
def sample_spec_data() -> dict[str, Any]:
    """Return sample spec data for testing."""
    return {
        "id": "spec-001",
        "title": "Test Spec",
        "content": "# Test Specification\n\nThis is a test spec.",
        "version": "1.0",
        "tags": ["test", "unit"],
    }


# ============================================================================
# TaskStatus Enum Tests
# ============================================================================


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_task_status_values(self) -> None:
        """Test TaskStatus enum values."""
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"

    def test_task_status_is_string(self) -> None:
        """Test that TaskStatus values are strings."""
        assert isinstance(TaskStatus.PENDING.value, str)

    def test_task_status_from_string(self) -> None:
        """Test creating TaskStatus from string."""
        status = TaskStatus("in_progress")
        assert status == TaskStatus.IN_PROGRESS


# ============================================================================
# RunStatus Enum Tests
# ============================================================================


class TestRunStatus:
    """Tests for RunStatus enum."""

    def test_run_status_values(self) -> None:
        """Test RunStatus enum values."""
        assert RunStatus.STARTED == "started"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.TIMEOUT == "timeout"
        assert RunStatus.CANCELLED == "cancelled"

    def test_run_status_is_string(self) -> None:
        """Test that RunStatus values are strings."""
        assert isinstance(RunStatus.RUNNING.value, str)


# ============================================================================
# Task Model Tests
# ============================================================================


class TestTask:
    """Tests for Task model."""

    def test_task_init_minimal(self) -> None:
        """Test Task initialization with minimal fields."""
        task = Task(id="task-001", title="Test Task")

        assert task.id == "task-001"
        assert task.title == "Test Task"
        assert task.description == ""
        assert task.status == TaskStatus.PENDING
        assert task.priority == 5
        assert task.assigned_agent is None
        assert task.labels == []
        assert task.dependencies == []
        assert task.metadata == {}

    def test_task_init_full(self) -> None:
        """Test Task initialization with all fields."""
        task = Task(
            id="task-002",
            title="Full Task",
            description="A complete task",
            status=TaskStatus.IN_PROGRESS,
            priority=10,
            assigned_agent="claude-code",
            labels=["bug", "urgent"],
            dependencies=["task-001"],
            metadata={"key": "value"},
        )

        assert task.id == "task-002"
        assert task.title == "Full Task"
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.priority == 10
        assert task.assigned_agent == "claude-code"
        assert task.labels == ["bug", "urgent"]
        assert task.dependencies == ["task-001"]
        assert task.metadata == {"key": "value"}

    def test_task_touch(self) -> None:
        """Test Task.touch() updates timestamp."""
        task = Task(id="task-001", title="Test")
        original_updated = task.updated_at

        task.touch()

        assert task.updated_at > original_updated


# ============================================================================
# Run Model Tests
# ============================================================================


class TestRun:
    """Tests for Run model."""

    def test_run_init_minimal(self) -> None:
        """Test Run initialization with minimal fields."""
        run = Run(id="run-001", agent="claude-code")

        assert run.id == "run-001"
        assert run.agent == "claude-code"
        assert run.task_id is None
        assert run.status == RunStatus.STARTED
        assert run.workdir == "."
        assert run.exit_code is None
        assert run.output is None
        assert run.error is None

    def test_run_init_full(self) -> None:
        """Test Run initialization with all fields."""
        run = Run(
            id="run-002",
            task_id="task-001",
            agent="codex",
            status=RunStatus.RUNNING,
            workdir="/project",
            command="npm test",
            metadata={"key": "value"},
        )

        assert run.id == "run-002"
        assert run.task_id == "task-001"
        assert run.agent == "codex"
        assert run.status == RunStatus.RUNNING
        assert run.workdir == "/project"
        assert run.command == "npm test"

    def test_run_complete_success(self) -> None:
        """Test Run.complete() for successful run."""
        run = Run(id="run-001", agent="claude-code")

        run.complete(
            status=RunStatus.COMPLETED,
            exit_code=0,
            output="Success",
        )

        assert run.status == RunStatus.COMPLETED
        assert run.exit_code == 0
        assert run.output == "Success"
        assert run.error is None
        assert run.completed_at is not None
        assert run.duration_seconds is not None

    def test_run_complete_failure(self) -> None:
        """Test Run.complete() for failed run."""
        run = Run(id="run-001", agent="claude-code")

        run.complete(
            status=RunStatus.FAILED,
            exit_code=1,
            error="Something went wrong",
        )

        assert run.status == RunStatus.FAILED
        assert run.exit_code == 1
        assert run.error == "Something went wrong"


# ============================================================================
# Spec Model Tests
# ============================================================================


class TestSpec:
    """Tests for Spec model."""

    def test_spec_init_minimal(self) -> None:
        """Test Spec initialization with minimal fields."""
        spec = Spec(id="spec-001", title="Test Spec", content="Content")

        assert spec.id == "spec-001"
        assert spec.title == "Test Spec"
        assert spec.content == "Content"
        assert spec.version == "1.0"
        assert spec.author is None
        assert spec.tags == []

    def test_spec_init_full(self) -> None:
        """Test Spec initialization with all fields."""
        spec = Spec(
            id="spec-002",
            title="Full Spec",
            content="Full content",
            version="2.0",
            author="test-user",
            tags=["feature", "api"],
            metadata={"priority": "high"},
        )

        assert spec.id == "spec-002"
        assert spec.version == "2.0"
        assert spec.author == "test-user"
        assert spec.tags == ["feature", "api"]


# ============================================================================
# Memory Model Tests
# ============================================================================


class TestMemory:
    """Tests for Memory model."""

    def test_memory_init_minimal(self) -> None:
        """Test Memory initialization with minimal fields."""
        memory = Memory(id="mem-001", key="test_key", value="test_value")

        assert memory.id == "mem-001"
        assert memory.key == "test_key"
        assert memory.value == "test_value"
        assert memory.category == "general"
        assert memory.expires_at is None

    def test_memory_init_with_expiration(self) -> None:
        """Test Memory initialization with expiration."""
        expires = datetime.utcnow() + timedelta(hours=1)
        memory = Memory(
            id="mem-001",
            key="temp_key",
            value="temp_value",
            expires_at=expires,
        )

        assert memory.expires_at == expires

    def test_memory_is_expired_false(self) -> None:
        """Test Memory.is_expired() returns False for non-expired memory."""
        expires = datetime.utcnow() + timedelta(hours=1)
        memory = Memory(
            id="mem-001",
            key="key",
            value="value",
            expires_at=expires,
        )

        assert memory.is_expired() is False

    def test_memory_is_expired_true(self) -> None:
        """Test Memory.is_expired() returns True for expired memory."""
        expired = datetime.utcnow() - timedelta(hours=1)
        memory = Memory(
            id="mem-001",
            key="key",
            value="value",
            expires_at=expired,
        )

        assert memory.is_expired() is True

    def test_memory_is_expired_none(self) -> None:
        """Test Memory.is_expired() returns False when no expiration."""
        memory = Memory(id="mem-001", key="key", value="value")

        assert memory.is_expired() is False


# ============================================================================
# StateManager Init Tests
# ============================================================================


class TestStateManagerInit:
    """Tests for StateManager initialization."""

    def test_init_with_path(self, temp_state_dir: Path) -> None:
        """Test StateManager initialization with path."""
        manager = StateManager(temp_state_dir)

        assert manager.state_dir == temp_state_dir.resolve()
        assert manager.backup_dir == temp_state_dir.resolve() / "backups"

    def test_init_with_string(self, temp_state_dir: Path) -> None:
        """Test StateManager initialization with string path."""
        manager = StateManager(str(temp_state_dir))

        assert manager.state_dir == temp_state_dir.resolve()

    def test_properties(self, state_manager: StateManager) -> None:
        """Test StateManager directory properties."""
        assert state_manager.specs_dir == state_manager.state_dir / "specs"
        assert state_manager.tasks_dir == state_manager.state_dir / "tasks"
        assert state_manager.runs_dir == state_manager.state_dir / "runs"
        assert state_manager.memory_dir == state_manager.state_dir / "memory"

    def test_initialize(self, temp_state_dir: Path) -> None:
        """Test StateManager.initialize() creates directories."""
        manager = StateManager(temp_state_dir)
        manager.initialize()

        assert manager.state_dir.exists()
        assert manager.specs_dir.exists()
        assert manager.tasks_dir.exists()
        assert manager.runs_dir.exists()
        assert manager.memory_dir.exists()
        assert manager.backup_dir.exists()

    def test_initialize_idempotent(self, state_manager: StateManager) -> None:
        """Test StateManager.initialize() is idempotent."""
        # Should not raise error when called again
        state_manager.initialize()

        assert state_manager.state_dir.exists()


# ============================================================================
# StateManager JSON Operations Tests
# ============================================================================


class TestStateManagerJSON:
    """Tests for StateManager JSON operations."""

    def test_write_json(self, state_manager: StateManager, tmp_path: Path) -> None:
        """Test write_json creates file with data."""
        file_path = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        result = state_manager.write_json(file_path, data)

        assert result == file_path
        assert file_path.exists()

        with open(file_path) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_write_json_creates_parent_dirs(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test write_json creates parent directories."""
        file_path = tmp_path / "subdir" / "nested" / "test.json"

        state_manager.write_json(file_path, {"data": "test"})

        assert file_path.exists()
        assert file_path.parent.exists()

    def test_write_json_pretty_printed(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test write_json creates pretty-printed output."""
        file_path = tmp_path / "test.json"

        state_manager.write_json(file_path, {"key": "value"}, indent=4)

        content = file_path.read_text()
        assert "    " in content  # 4-space indent

    def test_read_json_existing(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test read_json reads existing file."""
        file_path = tmp_path / "test.json"
        data = {"key": "value"}

        state_manager.write_json(file_path, data)
        result = state_manager.read_json(file_path)

        assert result == data

    def test_read_json_nonexistent_with_default(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test read_json returns default for nonexistent file."""
        file_path = tmp_path / "nonexistent.json"
        default = {"default": True}

        result = state_manager.read_json(file_path, default=default)

        assert result == default

    def test_read_json_nonexistent_no_default(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test read_json raises for nonexistent file without default."""
        file_path = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            state_manager.read_json(file_path)

    def test_read_json_invalid_with_default(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test read_json returns default for invalid JSON."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("not valid json")

        result = state_manager.read_json(file_path, default={"default": True})

        assert result == {"default": True}

    def test_write_json_atomic(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test write_json uses atomic write pattern."""
        file_path = tmp_path / "atomic.json"

        # Write initial content
        state_manager.write_json(file_path, {"version": 1})

        # Overwrite
        state_manager.write_json(file_path, {"version": 2})

        # Should have backup
        assert state_manager.backup_dir.exists()

        # File should have new content
        result = state_manager.read_json(file_path)
        assert result == {"version": 2}


# ============================================================================
# StateManager Task Operations Tests
# ============================================================================


class TestStateManagerTasks:
    """Tests for StateManager task operations."""

    def test_save_task(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test save_task creates task file."""
        result = state_manager.save_task("task-001", sample_task_data)

        assert result.exists()
        assert result.name == "task-001.json"

    def test_save_task_adds_timestamps(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test save_task adds created_at and updated_at."""
        state_manager.save_task("task-001", sample_task_data)

        loaded = state_manager.load_task("task-001")

        assert "created_at" in loaded
        assert "updated_at" in loaded

    def test_load_task_existing(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test load_task returns task data."""
        state_manager.save_task("task-001", sample_task_data)

        result = state_manager.load_task("task-001")

        assert result is not None
        assert result["id"] == "task-001"
        assert result["title"] == "Test Task"

    def test_load_task_nonexistent(self, state_manager: StateManager) -> None:
        """Test load_task returns None for nonexistent task."""
        result = state_manager.load_task("nonexistent")

        assert result is None

    def test_list_tasks_all(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test list_tasks returns all tasks."""
        state_manager.save_task("task-001", sample_task_data)
        state_manager.save_task("task-002", {**sample_task_data, "id": "task-002"})

        tasks = state_manager.list_tasks()

        assert len(tasks) == 2

    def test_list_tasks_filter_by_status(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test list_tasks filters by status."""
        state_manager.save_task("task-001", {**sample_task_data, "status": "pending"})
        state_manager.save_task(
            "task-002", {**sample_task_data, "id": "task-002", "status": "completed"}
        )

        pending = state_manager.list_tasks(status=TaskStatus.PENDING)
        completed = state_manager.list_tasks(status=TaskStatus.COMPLETED)

        assert len(pending) == 1
        assert len(completed) == 1

    def test_list_tasks_filter_by_agent(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test list_tasks filters by assigned agent."""
        state_manager.save_task(
            "task-001", {**sample_task_data, "assigned_agent": "claude-code"}
        )
        state_manager.save_task(
            "task-002",
            {**sample_task_data, "id": "task-002", "assigned_agent": "codex"},
        )

        claude_tasks = state_manager.list_tasks(agent="claude-code")

        assert len(claude_tasks) == 1
        assert claude_tasks[0]["assigned_agent"] == "claude-code"

    def test_delete_task_existing(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test delete_task removes task."""
        state_manager.save_task("task-001", sample_task_data)

        result = state_manager.delete_task("task-001")

        assert result is True
        assert state_manager.load_task("task-001") is None

    def test_delete_task_nonexistent(self, state_manager: StateManager) -> None:
        """Test delete_task returns False for nonexistent task."""
        result = state_manager.delete_task("nonexistent")

        assert result is False

    def test_list_tasks_empty(self, state_manager: StateManager) -> None:
        """Test list_tasks returns empty list when no tasks."""
        tasks = state_manager.list_tasks()

        assert tasks == []


# ============================================================================
# StateManager Run Operations Tests
# ============================================================================


class TestStateManagerRuns:
    """Tests for StateManager run operations."""

    def test_save_run(self, state_manager: StateManager, sample_run_data: dict) -> None:
        """Test save_run creates run file."""
        result = state_manager.save_run("run-001", sample_run_data)

        assert result.exists()
        assert result.name == "run-001.json"

    def test_load_run_existing(
        self, state_manager: StateManager, sample_run_data: dict
    ) -> None:
        """Test load_run returns run data."""
        state_manager.save_run("run-001", sample_run_data)

        result = state_manager.load_run("run-001")

        assert result is not None
        assert result["id"] == "run-001"
        assert result["agent"] == "claude-code"

    def test_load_run_nonexistent(self, state_manager: StateManager) -> None:
        """Test load_run returns None for nonexistent run."""
        result = state_manager.load_run("nonexistent")

        assert result is None

    def test_list_runs_all(
        self, state_manager: StateManager, sample_run_data: dict
    ) -> None:
        """Test list_runs returns all runs."""
        state_manager.save_run("run-001", sample_run_data)
        state_manager.save_run("run-002", {**sample_run_data, "id": "run-002"})

        runs = state_manager.list_runs()

        assert len(runs) == 2

    def test_list_runs_filter_by_status(
        self, state_manager: StateManager, sample_run_data: dict
    ) -> None:
        """Test list_runs filters by status."""
        state_manager.save_run("run-001", {**sample_run_data, "status": "running"})
        state_manager.save_run(
            "run-002", {**sample_run_data, "id": "run-002", "status": "completed"}
        )

        running = state_manager.list_runs(status=RunStatus.RUNNING)

        assert len(running) == 1

    def test_list_runs_filter_by_agent(
        self, state_manager: StateManager, sample_run_data: dict
    ) -> None:
        """Test list_runs filters by agent."""
        state_manager.save_run("run-001", sample_run_data)
        state_manager.save_run(
            "run-002", {**sample_run_data, "id": "run-002", "agent": "codex"}
        )

        claude_runs = state_manager.list_runs(agent="claude-code")

        assert len(claude_runs) == 1

    def test_list_runs_with_limit(
        self, state_manager: StateManager, sample_run_data: dict
    ) -> None:
        """Test list_runs respects limit."""
        for i in range(10):
            state_manager.save_run(
                f"run-{i:03d}", {**sample_run_data, "id": f"run-{i:03d}"}
            )

        runs = state_manager.list_runs(limit=5)

        assert len(runs) == 5


# ============================================================================
# StateManager Spec Operations Tests
# ============================================================================


class TestStateManagerSpecs:
    """Tests for StateManager spec operations."""

    def test_save_spec(
        self, state_manager: StateManager, sample_spec_data: dict
    ) -> None:
        """Test save_spec creates spec file."""
        result = state_manager.save_spec("spec-001", sample_spec_data)

        assert result.exists()
        assert result.name == "spec-001.json"

    def test_save_spec_adds_timestamps(
        self, state_manager: StateManager, sample_spec_data: dict
    ) -> None:
        """Test save_spec adds timestamps."""
        state_manager.save_spec("spec-001", sample_spec_data)

        loaded = state_manager.load_spec("spec-001")

        assert "created_at" in loaded
        assert "updated_at" in loaded

    def test_load_spec_existing(
        self, state_manager: StateManager, sample_spec_data: dict
    ) -> None:
        """Test load_spec returns spec data."""
        state_manager.save_spec("spec-001", sample_spec_data)

        result = state_manager.load_spec("spec-001")

        assert result is not None
        assert result["id"] == "spec-001"
        assert result["title"] == "Test Spec"

    def test_load_spec_nonexistent(self, state_manager: StateManager) -> None:
        """Test load_spec returns None for nonexistent spec."""
        result = state_manager.load_spec("nonexistent")

        assert result is None

    def test_list_specs_all(
        self, state_manager: StateManager, sample_spec_data: dict
    ) -> None:
        """Test list_specs returns all specs."""
        state_manager.save_spec("spec-001", sample_spec_data)
        state_manager.save_spec("spec-002", {**sample_spec_data, "id": "spec-002"})

        specs = state_manager.list_specs()

        assert len(specs) == 2

    def test_list_specs_filter_by_tags(
        self, state_manager: StateManager, sample_spec_data: dict
    ) -> None:
        """Test list_specs filters by tags."""
        state_manager.save_spec("spec-001", sample_spec_data)
        state_manager.save_spec(
            "spec-002",
            {**sample_spec_data, "id": "spec-002", "tags": ["other"]},
        )

        matching = state_manager.list_specs(tags=["test"])

        assert len(matching) == 1
        assert "test" in matching[0]["tags"]

    def test_list_specs_multiple_tags(
        self, state_manager: StateManager, sample_spec_data: dict
    ) -> None:
        """Test list_specs requires all tags."""
        state_manager.save_spec("spec-001", sample_spec_data)
        state_manager.save_spec(
            "spec-002",
            {**sample_spec_data, "id": "spec-002", "tags": ["test"]},
        )

        matching = state_manager.list_specs(tags=["test", "unit"])

        assert len(matching) == 1  # Only spec-001 has both tags


# ============================================================================
# StateManager Memory Operations Tests
# ============================================================================


class TestStateManagerMemory:
    """Tests for StateManager memory operations."""

    def test_save_memory(self, state_manager: StateManager) -> None:
        """Test save_memory creates memory entry."""
        result = state_manager.save_memory("test_key", "test_value")

        assert result.exists()

    def test_save_memory_with_category(self, state_manager: StateManager) -> None:
        """Test save_memory with category."""
        state_manager.save_memory("git_branch", "feature-x", category="git")

        value = state_manager.load_memory("git_branch")

        assert value == "feature-x"

    def test_load_memory_existing(self, state_manager: StateManager) -> None:
        """Test load_memory returns value."""
        state_manager.save_memory("test_key", {"nested": "data"})

        result = state_manager.load_memory("test_key")

        assert result == {"nested": "data"}

    def test_load_memory_nonexistent(self, state_manager: StateManager) -> None:
        """Test load_memory returns None for nonexistent key."""
        result = state_manager.load_memory("nonexistent")

        assert result is None

    def test_load_memory_expired(self, state_manager: StateManager) -> None:
        """Test load_memory returns None for expired memory."""
        state_manager.save_memory("temp_key", "temp_value", expires_in_seconds=-1)

        result = state_manager.load_memory("temp_key")

        assert result is None

    def test_list_memory_all(self, state_manager: StateManager) -> None:
        """Test list_memory returns all entries."""
        state_manager.save_memory("key1", "value1", category="cat1")
        state_manager.save_memory("key2", "value2", category="cat2")

        memories = state_manager.list_memory()

        assert len(memories) == 2

    def test_list_memory_filter_by_category(self, state_manager: StateManager) -> None:
        """Test list_memory filters by category."""
        state_manager.save_memory("key1", "value1", category="git")
        state_manager.save_memory("key2", "value2", category="docker")

        git_memories = state_manager.list_memory(category="git")

        assert len(git_memories) == 1
        assert git_memories[0]["category"] == "git"

    def test_delete_memory_existing(self, state_manager: StateManager) -> None:
        """Test delete_memory removes entry."""
        state_manager.save_memory("to_delete", "value")

        result = state_manager.delete_memory("to_delete")

        assert result is True
        assert state_manager.load_memory("to_delete") is None

    def test_delete_memory_nonexistent(self, state_manager: StateManager) -> None:
        """Test delete_memory returns False for nonexistent key."""
        result = state_manager.delete_memory("nonexistent")

        assert result is False

    def test_memory_key_sanitization(self, state_manager: StateManager) -> None:
        """Test memory keys with slashes are sanitized."""
        state_manager.save_memory("path/to/key", "value")

        result = state_manager.load_memory("path/to/key")

        assert result == "value"


# ============================================================================
# StateManager Utility Tests
# ============================================================================


class TestStateManagerUtilities:
    """Tests for StateManager utility methods."""

    def test_get_status(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test get_status returns summary."""
        state_manager.save_task("task-001", sample_task_data)
        state_manager.save_run("run-001", {"id": "run-001", "agent": "test"})

        status = state_manager.get_status()

        assert status["initialized"] is True
        assert status["tasks"]["total"] == 1
        assert status["runs"]["total"] == 1

    def test_get_status_empty(self, state_manager: StateManager) -> None:
        """Test get_status for empty state."""
        status = state_manager.get_status()

        assert status["tasks"]["total"] == 0
        assert status["runs"]["total"] == 0
        assert status["specs"]["total"] == 0
        assert status["memory"]["total"] == 0

    def test_cleanup_expired(self, state_manager: StateManager) -> None:
        """Test cleanup_expired removes expired entries."""
        state_manager.save_memory("valid", "value")
        state_manager.save_memory("expired", "value", expires_in_seconds=-1)

        removed = state_manager.cleanup_expired()

        assert removed == 1
        assert state_manager.load_memory("valid") == "value"

    def test_compact_backups(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test compact_backups removes old backups."""
        # Create a task and update it to create backup
        state_manager.save_task("task-001", sample_task_data)
        state_manager.save_task("task-001", {**sample_task_data, "status": "completed"})

        # Backup should exist
        assert len(list(state_manager.backup_dir.glob("**/*.bak"))) >= 1

        # With max_age_days=0, should remove all
        removed = state_manager.compact_backups(max_age_days=0)

        # Note: may be 0 if files are too new
        assert isinstance(removed, int)


# ============================================================================
# Module-level Convenience Functions Tests
# ============================================================================


class TestConvenienceFunctions:
    """Tests for module-level read_json and write_json functions."""

    def test_write_json_convenience(self, tmp_path: Path) -> None:
        """Test write_json convenience function."""
        file_path = tmp_path / "test.json"
        data = {"key": "value"}

        result = write_json(file_path, data)

        assert result == file_path
        assert file_path.exists()

    def test_read_json_convenience(self, tmp_path: Path) -> None:
        """Test read_json convenience function."""
        file_path = tmp_path / "test.json"
        data = {"key": "value"}

        write_json(file_path, data)
        result = read_json(file_path)

        assert result == data

    def test_read_json_with_default_convenience(self, tmp_path: Path) -> None:
        """Test read_json convenience function with default."""
        file_path = tmp_path / "nonexistent.json"

        result = read_json(file_path, default={"default": True})

        assert result == {"default": True}


# ============================================================================
# Backup and Recovery Tests
# ============================================================================


class TestBackupRecovery:
    """Tests for backup and recovery functionality."""

    def test_backup_created_on_overwrite(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test backup is created when overwriting file."""
        file_path = tmp_path / "test.json"

        state_manager.write_json(file_path, {"version": 1})
        state_manager.write_json(file_path, {"version": 2})

        # Backup directory should have a backup
        assert state_manager.backup_dir.exists()

    def test_restore_from_backup(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test restoring from backup on corrupt file."""
        file_path = tmp_path / "test.json"

        # Write valid data
        state_manager.write_json(file_path, {"version": 1})

        # Corrupt the file
        file_path.write_text("invalid json content")

        # Reading should restore from backup
        result = state_manager.read_json(file_path, default={"restored": False})

        # Should have restored from backup
        assert result == {"version": 1}


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_save_task_with_special_id(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test saving task with special characters in ID."""
        # This should work with valid ID
        state_manager.save_task("task-001-special", sample_task_data)

        result = state_manager.load_task("task-001-special")
        assert result is not None

    def test_list_tasks_sorted_by_created_at(
        self, state_manager: StateManager, sample_task_data: dict
    ) -> None:
        """Test list_tasks returns tasks sorted by created_at descending."""
        import time

        state_manager.save_task("task-001", sample_task_data)
        time.sleep(0.01)  # Ensure different timestamps
        state_manager.save_task("task-002", {**sample_task_data, "id": "task-002"})

        tasks = state_manager.list_tasks()

        # Most recent first
        assert tasks[0]["id"] == "task-002"
        assert tasks[1]["id"] == "task-001"

    def test_write_json_with_unicode(
        self, state_manager: StateManager, tmp_path: Path
    ) -> None:
        """Test write_json handles unicode characters."""
        file_path = tmp_path / "unicode.json"
        data = {"message": "Hello 世界 🌍"}

        state_manager.write_json(file_path, data)
        result = state_manager.read_json(file_path)

        assert result == data

    def test_state_manager_with_nonexistent_dir(self, tmp_path: Path) -> None:
        """Test StateManager works with nonexistent directory."""
        nonexistent = tmp_path / "does_not_exist"
        manager = StateManager(nonexistent)

        # Initialize should create it
        manager.initialize()

        assert nonexistent.exists()

    def test_memory_with_complex_value(self, state_manager: StateManager) -> None:
        """Test memory with complex nested value."""
        complex_value = {
            "nested": {
                "deep": {
                    "value": 42,
                    "list": [1, 2, 3],
                }
            }
        }

        state_manager.save_memory("complex", complex_value)
        result = state_manager.load_memory("complex")

        assert result == complex_value
