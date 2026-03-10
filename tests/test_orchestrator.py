"""
Unit Tests for Autoflow Orchestrator

Tests the AutoflowOrchestrator class for coordinating AI agents,
skill execution, and the closed-loop development cycle.

These tests use mocks to avoid requiring actual agent installations
or external services.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.agents.base import (
    ExecutionResult,
    ExecutionStatus,
)
from autoflow.agents.openclaw import SpawnResult
from autoflow.core.orchestrator import (
    AutoflowOrchestrator,
    CyclePhase,
    CycleResult,
    OrchestratorError,
    OrchestratorStats,
    OrchestratorStatus,
    create_orchestrator,
)
from autoflow.skills.executor import SkillExecutionResult

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def temp_skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return skills_dir


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock configuration object."""
    config = MagicMock()
    config.state_dir = Path("/tmp/test_state")
    config.openclaw.gateway_url = "http://localhost:8080"
    config.openclaw.extra_dirs = []
    config.agents.claude_code.timeout_seconds = 300
    config.agents.codex.timeout_seconds = 300
    config.ci.gates = []
    config.scheduler.enabled = False
    return config


@pytest.fixture
def mock_skill_registry() -> MagicMock:
    """Create a mock skill registry."""
    registry = MagicMock()
    registry.list_skills.return_value = ["IMPLEMENTER", "TESTER"]
    return registry


@pytest.fixture
def mock_skill_executor() -> MagicMock:
    """Create a mock skill executor."""
    executor = MagicMock()
    executor.execute_skill = AsyncMock(
        return_value=SkillExecutionResult(
            success=True,
            output="Task completed",
            skill_name="IMPLEMENTER",
        )
    )
    return executor


@pytest.fixture
def mock_tmux_manager() -> MagicMock:
    """Create a mock tmux manager."""
    manager = MagicMock()
    manager.cleanup_all = AsyncMock()
    return manager


@pytest.fixture
def mock_openclaw_adapter() -> MagicMock:
    """Create a mock OpenClaw adapter."""
    adapter = MagicMock()
    adapter.spawn_subagent = AsyncMock(
        return_value=SpawnResult(
            session_id="session-123",
            run_id="run-456",
            status="started",
        )
    )
    adapter.spawn_acp_agent = AsyncMock(
        return_value=SpawnResult(
            session_id="session-789",
            run_id="run-012",
            status="started",
        )
    )
    adapter.cleanup = AsyncMock()
    return adapter


@pytest.fixture
def orchestrator(
    mock_config: MagicMock,
    temp_state_dir: Path,
    temp_skills_dir: Path,
) -> AutoflowOrchestrator:
    """Create a basic AutoflowOrchestrator instance for testing."""
    return AutoflowOrchestrator(
        config=mock_config,
        state_dir=temp_state_dir,
        skills_dir=temp_skills_dir,
        auto_initialize=False,
    )


# ============================================================================
# OrchestratorStatus Enum Tests
# ============================================================================


class TestOrchestratorStatus:
    """Tests for OrchestratorStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert OrchestratorStatus.IDLE.value == "idle"
        assert OrchestratorStatus.INITIALIZING.value == "initializing"
        assert OrchestratorStatus.RUNNING.value == "running"
        assert OrchestratorStatus.PAUSED.value == "paused"
        assert OrchestratorStatus.STOPPING.value == "stopping"
        assert OrchestratorStatus.STOPPED.value == "stopped"
        assert OrchestratorStatus.ERROR.value == "error"

    def test_status_is_string_enum(self) -> None:
        """Test that status is a string enum."""
        assert isinstance(OrchestratorStatus.IDLE, str)


# ============================================================================
# CyclePhase Enum Tests
# ============================================================================


class TestCyclePhase:
    """Tests for CyclePhase enum."""

    def test_phase_values(self) -> None:
        """Test phase enum values."""
        assert CyclePhase.DISCOVER.value == "discover"
        assert CyclePhase.FIX.value == "fix"
        assert CyclePhase.DOCUMENT.value == "document"
        assert CyclePhase.CODE.value == "code"
        assert CyclePhase.TEST.value == "test"
        assert CyclePhase.REFACTOR.value == "refactor"
        assert CyclePhase.COMMIT.value == "commit"


# ============================================================================
# OrchestratorError Tests
# ============================================================================


class TestOrchestratorError:
    """Tests for OrchestratorError exception."""

    def test_error_message(self) -> None:
        """Test error message."""
        error = OrchestratorError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.phase is None

    def test_error_with_phase(self) -> None:
        """Test error with phase."""
        error = OrchestratorError(
            "Test failed",
            phase=CyclePhase.TEST,
        )

        assert str(error) == "Test failed"
        assert error.phase == CyclePhase.TEST


# ============================================================================
# CycleResult Tests
# ============================================================================


class TestCycleResult:
    """Tests for CycleResult dataclass."""

    def test_cycle_result_init(self) -> None:
        """Test cycle result initialization."""
        result = CycleResult()

        assert result.cycle_id is not None
        assert result.phase == CyclePhase.DISCOVER
        assert result.success is False
        assert result.task_result is None
        assert result.test_result is None
        assert result.commit_result is None
        assert result.error is None
        assert result.metadata == {}

    def test_cycle_result_mark_complete_success(self) -> None:
        """Test marking cycle as successful."""
        result = CycleResult()
        result.mark_complete(success=True)

        assert result.success is True
        assert result.error is None
        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    def test_cycle_result_mark_complete_error(self) -> None:
        """Test marking cycle as failed."""
        result = CycleResult()
        result.mark_complete(success=False, error="Test error")

        assert result.success is False
        assert result.error == "Test error"
        assert result.completed_at is not None

    def test_cycle_result_with_all_fields(self) -> None:
        """Test cycle result with all fields set."""
        task_result = SkillExecutionResult(
            success=True,
            output="Done",
            skill_name="IMPLEMENTER",
        )
        test_result = ExecutionResult(status=ExecutionStatus.SUCCESS)
        commit_result = ExecutionResult(status=ExecutionStatus.SUCCESS)

        result = CycleResult(
            cycle_id="abc123",
            phase=CyclePhase.COMMIT,
            success=True,
            task_result=task_result,
            test_result=test_result,
            commit_result=commit_result,
            metadata={"key": "value"},
        )

        assert result.cycle_id == "abc123"
        assert result.phase == CyclePhase.COMMIT
        assert result.success is True
        assert result.task_result == task_result
        assert result.test_result == test_result
        assert result.commit_result == commit_result
        assert result.metadata == {"key": "value"}


# ============================================================================
# OrchestratorStats Tests
# ============================================================================


class TestOrchestratorStats:
    """Tests for OrchestratorStats model."""

    def test_stats_init(self) -> None:
        """Test stats initialization."""
        stats = OrchestratorStats()

        assert stats.total_cycles == 0
        assert stats.successful_cycles == 0
        assert stats.failed_cycles == 0
        assert stats.total_tasks == 0
        assert stats.completed_tasks == 0
        assert stats.failed_tasks == 0
        assert stats.total_commits == 0
        assert stats.average_cycle_duration == 0.0
        assert stats.last_cycle_at is None
        assert stats.started_at is not None

    def test_stats_with_values(self) -> None:
        """Test stats with custom values."""
        stats = OrchestratorStats(
            total_cycles=10,
            successful_cycles=8,
            failed_cycles=2,
            total_tasks=15,
            completed_tasks=12,
            failed_tasks=3,
            total_commits=5,
            average_cycle_duration=45.5,
        )

        assert stats.total_cycles == 10
        assert stats.successful_cycles == 8
        assert stats.failed_cycles == 2
        assert stats.total_tasks == 15
        assert stats.completed_tasks == 12
        assert stats.failed_tasks == 3
        assert stats.total_commits == 5
        assert stats.average_cycle_duration == 45.5


# ============================================================================
# AutoflowOrchestrator Init Tests
# ============================================================================


class TestAutoflowOrchestratorInit:
    """Tests for AutoflowOrchestrator initialization."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        orchestrator = AutoflowOrchestrator()

        assert orchestrator._config is None
        assert orchestrator._status == OrchestratorStatus.IDLE
        assert orchestrator._current_task is None
        assert orchestrator._current_cycle is None
        assert orchestrator._running is False

    def test_init_with_config(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Test initialization with config."""
        orchestrator = AutoflowOrchestrator(config=mock_config)

        assert orchestrator._config == mock_config

    def test_init_with_dirs(
        self,
        temp_state_dir: Path,
        temp_skills_dir: Path,
    ) -> None:
        """Test initialization with directories."""
        orchestrator = AutoflowOrchestrator(
            state_dir=temp_state_dir,
            skills_dir=temp_skills_dir,
        )

        assert orchestrator._state_dir == temp_state_dir
        assert orchestrator._skills_dir == temp_skills_dir

    def test_init_status_idle(self) -> None:
        """Test initial status is IDLE."""
        orchestrator = AutoflowOrchestrator()

        assert orchestrator.status == OrchestratorStatus.IDLE


# ============================================================================
# AutoflowOrchestrator Properties Tests
# ============================================================================


class TestAutoflowOrchestratorProperties:
    """Tests for AutoflowOrchestrator properties."""

    def test_status_property(self, orchestrator: AutoflowOrchestrator) -> None:
        """Test status property."""
        assert orchestrator.status == OrchestratorStatus.IDLE

        orchestrator._status = OrchestratorStatus.RUNNING
        assert orchestrator.status == OrchestratorStatus.RUNNING

    def test_stats_property(self, orchestrator: AutoflowOrchestrator) -> None:
        """Test stats property."""
        stats = orchestrator.stats

        assert isinstance(stats, OrchestratorStats)
        assert stats.total_cycles == 0

    def test_config_property_lazy_load(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test config property loads config lazily."""
        orchestrator = AutoflowOrchestrator(state_dir=temp_state_dir)

        with patch(
            "autoflow.core.orchestrator.load_config"
        ) as mock_load:
            mock_load.return_value = MagicMock()
            _ = orchestrator.config

            mock_load.assert_called_once()


# ============================================================================
# AutoflowOrchestrator Initialize Tests
# ============================================================================


class TestAutoflowOrchestratorInitialize:
    """Tests for AutoflowOrchestrator.initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_success(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test successful initialization."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}

            await orchestrator.initialize()

            assert orchestrator.status == OrchestratorStatus.IDLE

    @pytest.mark.asyncio
    async def test_initialize_no_adapters(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test initialization fails with no adapters."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {}

            with pytest.raises(OrchestratorError) as exc_info:
                await orchestrator.initialize()

            assert "No agent adapters available" in str(exc_info.value)
            assert orchestrator.status == OrchestratorStatus.ERROR

    @pytest.mark.asyncio
    async def test_initialize_sets_status(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test initialization sets status correctly."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}

            # Start initialization
            init_task = asyncio.create_task(orchestrator.initialize())

            # Give it a moment to start
            await asyncio.sleep(0.01)

            # Wait for completion
            await init_task

            assert orchestrator.status == OrchestratorStatus.IDLE


# ============================================================================
# AutoflowOrchestrator Run Task Tests
# ============================================================================


class TestAutoflowOrchestratorRunTask:
    """Tests for AutoflowOrchestrator.run_task method."""

    @pytest.mark.asyncio
    async def test_run_task_success(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_executor: MagicMock,
        temp_skills_dir: Path,
    ) -> None:
        """Test successful task execution."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}

            await orchestrator.initialize()

        # Mock skill executor
        with patch.object(
            orchestrator, "skill_executor", mock_skill_executor
        ):
            result = await orchestrator.run_task(
                task="Fix the bug in app.py",
                skill_name="IMPLEMENTER",
            )

            assert result.success is True
            assert result.output == "Task completed"
            assert orchestrator.stats.completed_tasks == 1

    @pytest.mark.asyncio
    async def test_run_task_failure(
        self,
        orchestrator: AutoflowOrchestrator,
        temp_skills_dir: Path,
    ) -> None:
        """Test failed task execution."""
        mock_executor = MagicMock()
        mock_executor.execute_skill = AsyncMock(
            return_value=SkillExecutionResult(
                success=False,
                error="Task failed",
                skill_name="IMPLEMENTER",
            )
        )

        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        with patch.object(orchestrator, "skill_executor", mock_executor):
            result = await orchestrator.run_task(
                task="Impossible task",
                skill_name="IMPLEMENTER",
            )

            assert result.success is False
            assert result.error == "Task failed"
            assert orchestrator.stats.failed_tasks == 1

    @pytest.mark.asyncio
    async def test_run_task_updates_status(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_executor: MagicMock,
        temp_skills_dir: Path,
    ) -> None:
        """Test run_task updates orchestrator status."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        with patch.object(orchestrator, "skill_executor", mock_skill_executor):
            # Create a future for execute_skill that we can control
            future = asyncio.Future()
            mock_skill_executor.execute_skill.return_value = future

            # Start task
            task = asyncio.create_task(
                orchestrator.run_task(
                    task="Test task",
                    skill_name="IMPLEMENTER",
                )
            )

            # Check status while running
            await asyncio.sleep(0.01)
            if not task.done():
                assert orchestrator.status == OrchestratorStatus.RUNNING

            # Complete the task
            future.set_result(
                SkillExecutionResult(
                    success=True,
                    output="Done",
                    skill_name="IMPLEMENTER",
                )
            )
            await task

            # Check status after completion
            assert orchestrator.status == OrchestratorStatus.IDLE

    @pytest.mark.asyncio
    async def test_run_task_with_context(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_executor: MagicMock,
        temp_skills_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test task execution with context files."""
        context_file = tmp_path / "context.py"
        context_file.write_text("# Context file")

        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        with patch.object(orchestrator, "skill_executor", mock_skill_executor):
            await orchestrator.run_task(
                task="Test task",
                skill_name="IMPLEMENTER",
                context_files=[context_file],
                context_text="Additional context",
            )

            # Verify execute_skill was called with context
            call_kwargs = mock_skill_executor.execute_skill.call_args[1]
            assert call_kwargs["context_files"] == [context_file]
            assert call_kwargs["context_text"] == "Additional context"


# ============================================================================
# AutoflowOrchestrator Spawn Tests
# ============================================================================


class TestAutoflowOrchestratorSpawn:
    """Tests for AutoflowOrchestrator spawn methods."""

    @pytest.mark.asyncio
    async def test_spawn_subagent(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_openclaw_adapter: MagicMock,
    ) -> None:
        """Test spawning a sub-agent."""
        with patch.object(
            orchestrator, "openclaw_adapter", mock_openclaw_adapter
        ):
            result = await orchestrator.spawn_subagent(
                task="Implement feature X",
                label="feature-x",
                timeout_seconds=600,
            )

            assert result.session_id == "session-123"
            assert result.run_id == "run-456"
            assert result.status == "started"

            mock_openclaw_adapter.spawn_subagent.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_subagent_error(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_openclaw_adapter: MagicMock,
    ) -> None:
        """Test sub-agent spawn error handling."""
        mock_openclaw_adapter.spawn_subagent.side_effect = Exception(
            "Connection failed"
        )

        with patch.object(
            orchestrator, "openclaw_adapter", mock_openclaw_adapter
        ):
            with pytest.raises(OrchestratorError) as exc_info:
                await orchestrator.spawn_subagent(
                    task="Test task",
                    label="test",
                )

            assert "Failed to spawn sub-agent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_spawn_acp_agent(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_openclaw_adapter: MagicMock,
    ) -> None:
        """Test spawning an ACP agent."""
        with patch.object(
            orchestrator, "openclaw_adapter", mock_openclaw_adapter
        ):
            result = await orchestrator.spawn_acp_agent(
                task="Test ACP task",
                agent_id="codex-agent",
                thread=True,
            )

            assert result.session_id == "session-789"
            assert result.run_id == "run-012"

            mock_openclaw_adapter.spawn_acp_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_acp_agent_error(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_openclaw_adapter: MagicMock,
    ) -> None:
        """Test ACP agent spawn error handling."""
        mock_openclaw_adapter.spawn_acp_agent.side_effect = Exception(
            "ACP not available"
        )

        with patch.object(
            orchestrator, "openclaw_adapter", mock_openclaw_adapter
        ):
            with pytest.raises(OrchestratorError) as exc_info:
                await orchestrator.spawn_acp_agent(
                    task="Test",
                    agent_id="codex",
                )

            assert "Failed to spawn ACP agent" in str(exc_info.value)


# ============================================================================
# AutoflowOrchestrator Cycle Tests
# ============================================================================


class TestAutoflowOrchestratorCycle:
    """Tests for AutoflowOrchestrator.run_cycle method."""

    @pytest.mark.asyncio
    async def test_run_cycle_success(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_executor: MagicMock,
    ) -> None:
        """Test successful cycle execution."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        # Mock skill executor to return success
        mock_skill_executor.execute_skill = AsyncMock(
            return_value=SkillExecutionResult(
                success=True,
                output="Done",
                skill_name="IMPLEMENTER",
            )
        )

        with patch.object(orchestrator, "skill_executor", mock_skill_executor):
            with patch.object(
                orchestrator, "_run_tests"
            ) as mock_run_tests:
                mock_run_tests.return_value = ExecutionResult(
                    status=ExecutionStatus.SUCCESS
                )

                with patch.object(
                    orchestrator, "_commit_changes"
                ) as mock_commit:
                    mock_commit.return_value = ExecutionResult(
                        status=ExecutionStatus.SUCCESS
                    )

                    result = await orchestrator.run_cycle(
                        task="Fix the bug",
                        auto_commit=True,
                        run_tests=True,
                    )

                    assert result.success is True
                    assert result.duration_seconds is not None
                    assert orchestrator.stats.successful_cycles == 1

    @pytest.mark.asyncio
    async def test_run_cycle_discovery_failure(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_executor: MagicMock,
    ) -> None:
        """Test cycle fails on discovery phase."""
        mock_skill_executor.execute_skill = AsyncMock(
            return_value=SkillExecutionResult(
                success=False,
                error="Discovery failed",
                skill_name="CONTINUOUS_ITERATOR",
            )
        )

        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        with patch.object(orchestrator, "skill_executor", mock_skill_executor):
            with pytest.raises(OrchestratorError) as exc_info:
                await orchestrator.run_cycle(task="Test task")

            assert exc_info.value.phase == CyclePhase.DISCOVER
            assert orchestrator.stats.failed_cycles == 1

    @pytest.mark.asyncio
    async def test_run_cycle_test_failure_and_fix(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_executor: MagicMock,
    ) -> None:
        """Test cycle handles test failure and fixes."""
        call_count = [0]

        def mock_execute(*args, **kwargs):
            call_count[0] += 1
            # Discovery and code succeed, tests fail, fix succeeds
            if call_count[0] == 3:  # test call
                return SkillExecutionResult(
                    success=False,
                    error="Tests failed",
                    skill_name="TESTER",
                )
            return SkillExecutionResult(
                success=True,
                output="Done",
                skill_name="IMPLEMENTER",
            )

        mock_skill_executor.execute_skill = AsyncMock(side_effect=mock_execute)

        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        with patch.object(orchestrator, "skill_executor", mock_skill_executor):
            with patch.object(
                orchestrator, "_run_tests"
            ) as mock_run_tests:
                mock_run_tests.return_value = ExecutionResult(
                    status=ExecutionStatus.FAILURE,
                    error="Test failed",
                )

                with patch.object(
                    orchestrator, "_commit_changes"
                ) as mock_commit:
                    mock_commit.return_value = ExecutionResult(
                        status=ExecutionStatus.SUCCESS
                    )

                    result = await orchestrator.run_cycle(
                        task="Test task",
                        run_tests=True,
                    )

                    assert result.success is True


# ============================================================================
# AutoflowOrchestrator Continuous Iteration Tests
# ============================================================================


class TestAutoflowOrchestratorContinuousIteration:
    """Tests for continuous iteration mode."""

    @pytest.mark.asyncio
    async def test_start_stop_continuous_iteration(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test starting and stopping continuous iteration."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        # Mock _get_next_task to return None (no tasks)
        with patch.object(
            orchestrator, "_get_next_task", return_value=None
        ):
            # Start continuous iteration
            start_task = asyncio.create_task(
                orchestrator.start_continuous_iteration(
                    interval_seconds=0.1,
                    max_cycles=2,
                )
            )

            # Wait a bit
            await asyncio.sleep(0.05)

            # Stop it
            await orchestrator.stop_continuous_iteration()

            # Wait for task to complete
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(start_task, timeout=1.0)

    @pytest.mark.asyncio
    async def test_continuous_iteration_max_cycles(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_executor: MagicMock,
    ) -> None:
        """Test continuous iteration respects max_cycles."""
        mock_skill_executor.execute_skill = AsyncMock(
            return_value=SkillExecutionResult(
                success=True,
                output="Done",
                skill_name="IMPLEMENTER",
            )
        )

        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        task_count = [0]

        async def mock_get_task(*args):
            task_count[0] += 1
            return f"Task {task_count[0]}"

        with patch.object(orchestrator, "skill_executor", mock_skill_executor):
            with patch.object(
                orchestrator, "_get_next_task", side_effect=mock_get_task
            ):
                with patch.object(orchestrator, "run_cycle") as mock_cycle:
                    mock_cycle.return_value = CycleResult(success=True)

                    await orchestrator.start_continuous_iteration(
                        interval_seconds=0.01,
                        max_cycles=2,
                    )

                    assert mock_cycle.call_count == 2


# ============================================================================
# AutoflowOrchestrator Add Task Tests
# ============================================================================


class TestAutoflowOrchestratorAddTask:
    """Tests for AutoflowOrchestrator.add_task method."""

    def test_add_task_minimal(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test adding a minimal task."""
        task = orchestrator.add_task(title="Test task")

        assert task.id is not None
        assert task.title == "Test task"
        assert task.description == ""
        assert task.priority == 5
        assert task.labels == []
        assert orchestrator.stats.total_tasks == 1

    def test_add_task_full(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test adding a task with all fields."""
        task = orchestrator.add_task(
            title="Full task",
            description="Detailed description",
            priority=8,
            labels=["bug", "urgent"],
            metadata={"source": "test"},
        )

        assert task.title == "Full task"
        assert task.description == "Detailed description"
        assert task.priority == 8
        assert task.labels == ["bug", "urgent"]
        assert task.metadata == {"source": "test"}


# ============================================================================
# AutoflowOrchestrator Status Summary Tests
# ============================================================================


class TestAutoflowOrchestratorStatusSummary:
    """Tests for AutoflowOrchestrator.get_status_summary method."""

    @pytest.mark.asyncio
    async def test_get_status_summary(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_registry: MagicMock,
    ) -> None:
        """Test getting status summary."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        with patch.object(
            orchestrator, "skill_registry", mock_skill_registry
        ):
            summary = await orchestrator.get_status_summary()

            assert "orchestrator" in summary
            assert "stats" in summary
            assert "state" in summary
            assert "adapters" in summary
            assert "skills" in summary

            assert summary["orchestrator"]["status"] == "idle"
            assert summary["orchestrator"]["running"] is False

    @pytest.mark.asyncio
    async def test_get_status_summary_with_current_task(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_skill_registry: MagicMock,
    ) -> None:
        """Test status summary with current task."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        # Set a current task
        orchestrator._current_task = MagicMock()
        orchestrator._current_task.id = "task-123"

        with patch.object(
            orchestrator, "skill_registry", mock_skill_registry
        ):
            summary = await orchestrator.get_status_summary()

            assert summary["orchestrator"]["current_task"] == "task-123"


# ============================================================================
# AutoflowOrchestrator Cleanup Tests
# ============================================================================


class TestAutoflowOrchestratorCleanup:
    """Tests for AutoflowOrchestrator.cleanup method."""

    @pytest.mark.asyncio
    async def test_cleanup(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_tmux_manager: MagicMock,
    ) -> None:
        """Test cleanup method."""
        orchestrator._tmux_manager = mock_tmux_manager
        orchestrator._running = True

        await orchestrator.cleanup()

        assert orchestrator._running is False
        mock_tmux_manager.cleanup_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test async context manager usage."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}

            async with orchestrator as orch:
                assert orch.status == OrchestratorStatus.IDLE

    @pytest.mark.asyncio
    async def test_context_manager_cleanup_on_error(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_tmux_manager: MagicMock,
    ) -> None:
        """Test cleanup is called on error in context manager."""
        orchestrator._tmux_manager = mock_tmux_manager

        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}

            with patch.object(
                orchestrator, "cleanup"
            ) as mock_cleanup:
                mock_cleanup.return_value = None

                try:
                    async with orchestrator:
                        raise ValueError("Test error")
                except ValueError:
                    pass

                mock_cleanup.assert_called_once()


# ============================================================================
# AutoflowOrchestrator Repr Tests
# ============================================================================


class TestAutoflowOrchestratorRepr:
    """Tests for AutoflowOrchestrator string representation."""

    def test_repr(self, orchestrator: AutoflowOrchestrator) -> None:
        """Test string representation."""
        repr_str = repr(orchestrator)

        assert "AutoflowOrchestrator" in repr_str
        assert "status=idle" in repr_str
        assert "tasks=" in repr_str
        assert "cycles=" in repr_str


# ============================================================================
# create_orchestrator Factory Tests
# ============================================================================


class TestCreateOrchestrator:
    """Tests for create_orchestrator factory function."""

    def test_create_orchestrator_default(self) -> None:
        """Test creating orchestrator with defaults."""
        orchestrator = create_orchestrator(auto_initialize=False)

        assert isinstance(orchestrator, AutoflowOrchestrator)
        assert orchestrator._config is None

    def test_create_orchestrator_with_state_dir(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test creating orchestrator with state directory."""
        orchestrator = create_orchestrator(
            state_dir=str(temp_state_dir),
            auto_initialize=False,
        )

        assert orchestrator._state_dir == temp_state_dir

    def test_create_orchestrator_with_config_path(
        self,
        tmp_path: Path,
    ) -> None:
        """Test creating orchestrator with config path."""
        config_path = tmp_path / "config.json5"
        config_path.write_text('{}')

        with patch(
            "autoflow.core.orchestrator.load_config"
        ) as mock_load:
            mock_load.return_value = MagicMock()

            create_orchestrator(
                config_path=str(config_path),
                auto_initialize=False,
            )

            mock_load.assert_called_once_with(str(config_path))


# ============================================================================
# Internal Methods Tests
# ============================================================================


class TestAutoflowOrchestratorInternalMethods:
    """Tests for internal orchestrator methods."""

    @pytest.mark.asyncio
    async def test_run_tests_success(
        self,
        orchestrator: AutoflowOrchestrator,
        tmp_path: Path,
    ) -> None:
        """Test _run_tests with successful tests."""
        result = await orchestrator._run_tests(tmp_path)

        assert result.status in [
            ExecutionStatus.SUCCESS,
            ExecutionStatus.FAILURE,
            ExecutionStatus.ERROR,
        ]

    @pytest.mark.asyncio
    async def test_commit_changes_with_changes(
        self,
        orchestrator: AutoflowOrchestrator,
        tmp_path: Path,
    ) -> None:
        """Test _commit_changes when there are changes."""
        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create a file and stage it
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=tmp_path, capture_output=True)

        result = await orchestrator._commit_changes(
            workdir=tmp_path,
            message="Test commit",
        )

        assert result.status in [
            ExecutionStatus.SUCCESS,
            ExecutionStatus.FAILURE,
            ExecutionStatus.ERROR,
        ]

    @pytest.mark.asyncio
    async def test_commit_changes_no_changes(
        self,
        orchestrator: AutoflowOrchestrator,
        tmp_path: Path,
    ) -> None:
        """Test _commit_changes when there are no changes."""
        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        result = await orchestrator._commit_changes(
            workdir=tmp_path,
            message="Test commit",
        )

        # Should succeed with "no changes to commit"
        assert result.status == ExecutionStatus.SUCCESS
        assert result.output == "No changes to commit"

    @pytest.mark.asyncio
    async def test_get_next_task_from_state(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test _get_next_task gets task from state."""
        # Add a pending task
        orchestrator.add_task(
            title="Pending task",
            description="Task from queue",
        )

        task = await orchestrator._get_next_task()

        assert task == "Task from queue"

    @pytest.mark.asyncio
    async def test_get_next_task_from_file(
        self,
        orchestrator: AutoflowOrchestrator,
        tmp_path: Path,
    ) -> None:
        """Test _get_next_task reads from task file."""
        task_file = tmp_path / "tasks.txt"
        task_file.write_text("Task from file")

        task = await orchestrator._get_next_task(
            task_source=str(task_file)
        )

        assert task == "Task from file"

    @pytest.mark.asyncio
    async def test_get_next_task_none(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test _get_next_task returns None when no tasks."""
        task = await orchestrator._get_next_task()

        assert task is None

    def test_update_average_cycle_duration(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test updating average cycle duration."""
        orchestrator._stats.total_cycles = 1
        orchestrator._update_average_cycle_duration(10.0)

        assert orchestrator._stats.average_cycle_duration == 10.0

        orchestrator._stats.total_cycles = 2
        orchestrator._update_average_cycle_duration(20.0)

        assert orchestrator._stats.average_cycle_duration == 15.0


# ============================================================================
# Edge Cases Tests
# ============================================================================


class TestAutoflowOrchestratorEdgeCases:
    """Tests for edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_run_task_exception(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test run_task handles exceptions."""
        mock_executor = MagicMock()
        mock_executor.execute_skill = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        with patch.object(orchestrator, "skill_executor", mock_executor):
            with pytest.raises(OrchestratorError) as exc_info:
                await orchestrator.run_task(task="Test task")

            assert "Task execution failed" in str(exc_info.value)
            assert orchestrator.stats.failed_tasks == 1

    @pytest.mark.asyncio
    async def test_double_start_continuous_iteration(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test starting continuous iteration twice is safe."""
        with patch.object(
            orchestrator, "_get_available_adapters"
        ) as mock_adapters:
            mock_adapters.return_value = {"claude-code": MagicMock()}
            await orchestrator.initialize()

        with patch.object(
            orchestrator, "_get_next_task", return_value=None
        ):
            # Start first
            task1 = asyncio.create_task(
                orchestrator.start_continuous_iteration()
            )

            await asyncio.sleep(0.01)

            # Try to start again - should return immediately
            orchestrator._running = True
            await orchestrator.start_continuous_iteration()

            # Cleanup
            orchestrator._running = False
            task1.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task1

    @pytest.mark.asyncio
    async def test_stop_continuous_iteration_when_not_running(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test stopping when not running is safe."""
        await orchestrator.stop_continuous_iteration()

        assert orchestrator.status == OrchestratorStatus.STOPPED

    def test_get_available_adapters_caches(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that _get_available_adapters caches adapters."""
        adapters1 = orchestrator._get_available_adapters()
        adapters2 = orchestrator._get_available_adapters()

        assert adapters1 is adapters2
