"""
Unit Tests for Scheduler Daemon

Tests the SchedulerDaemon, JobResult, and job handler classes
for background task scheduling.

These tests mock APScheduler and external dependencies to avoid
requiring actual tmux or agent installations.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.scheduler import (
    JOB_REGISTRY,
    DaemonStats,
    DaemonStatus,
    JobExecutionResult,
    JobInfo,
    JobResult,
    JobStatus,
    SchedulerDaemon,
    SchedulerDaemonError,
    cleanup_sessions,
    distribute_tasks,
    get_orchestrator,
    health_check,
    monitor_agents,
    set_orchestrator,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock configuration object."""
    config = MagicMock()
    config.state_dir = "/tmp/test_state"
    config.scheduler.enabled = True
    config.scheduler.jobs = []

    # Mock agent config
    config.agents.claude_code.timeout_seconds = 600

    return config


@pytest.fixture
def mock_state_manager() -> MagicMock:
    """Create a mock StateManager."""
    state = MagicMock()
    state.initialize.return_value = None
    state.state_dir = Path("/tmp/test_state")
    state.state_dir.exists.return_value = True
    state.list_runs.return_value = []
    state.list_tasks.return_value = []
    state.save_memory.return_value = None
    state.cleanup_expired.return_value = 0
    state.compact_backups.return_value = 0
    state.save_task.return_value = None
    state.save_run.return_value = None
    state.delete_task.return_value = None
    return state


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """Create a mock orchestrator."""
    orchestrator = MagicMock()
    orchestrator.tmux_manager = MagicMock()
    orchestrator.tmux_manager.get_session = AsyncMock(return_value=None)
    orchestrator.tmux_manager.kill_session = AsyncMock(return_value=True)
    orchestrator.tmux_manager.list_sessions = AsyncMock(return_value=[])
    orchestrator.state = MagicMock()
    orchestrator.run_task = AsyncMock(return_value=MagicMock(success=True))
    return orchestrator


@pytest.fixture
def daemon(mock_config: MagicMock) -> SchedulerDaemon:
    """Create a SchedulerDaemon instance for testing."""
    return SchedulerDaemon(config=mock_config, auto_start=False)


# ============================================================================
# JobResult Tests
# ============================================================================


class TestJobResult:
    """Tests for JobResult model."""

    def test_job_result_init(self) -> None:
        """Test JobResult initialization."""
        result = JobResult(job_name="test_job")

        assert result.job_name == "test_job"
        assert result.success is False
        assert result.started_at is not None
        assert result.completed_at is None
        assert result.output is None
        assert result.error is None
        assert result.metrics == {}

    def test_job_result_mark_complete_success(self) -> None:
        """Test marking JobResult as complete successfully."""
        result = JobResult(job_name="test_job")
        result.mark_complete(success=True, output="Done")

        assert result.success is True
        assert result.output == "Done"
        assert result.error is None
        assert result.completed_at is not None

    def test_job_result_mark_complete_error(self) -> None:
        """Test marking JobResult as complete with error."""
        result = JobResult(job_name="test_job")
        result.mark_complete(success=False, error="Failed")

        assert result.success is False
        assert result.output is None
        assert result.error == "Failed"
        assert result.completed_at is not None

    def test_job_result_with_metrics(self) -> None:
        """Test JobResult with custom metrics."""
        result = JobResult(
            job_name="test_job",
            metrics={"count": 10, "duration": 5.5},
        )

        assert result.metrics["count"] == 10
        assert result.metrics["duration"] == 5.5


# ============================================================================
# JobExecutionResult Tests
# ============================================================================


class TestJobExecutionResult:
    """Tests for JobExecutionResult model."""

    def test_execution_result_init(self) -> None:
        """Test JobExecutionResult initialization."""
        result = JobExecutionResult(job_id="job-123")

        assert result.job_id == "job-123"
        assert result.success is False
        assert result.started_at is not None
        assert result.completed_at is None
        assert result.duration_seconds is None

    def test_execution_result_mark_complete(self) -> None:
        """Test marking execution result complete."""
        result = JobExecutionResult(job_id="job-123")
        result.mark_complete(success=True, output="Completed")

        assert result.success is True
        assert result.output == "Completed"
        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0


# ============================================================================
# JobInfo Tests
# ============================================================================


class TestJobInfo:
    """Tests for JobInfo model."""

    def test_job_info_init(self) -> None:
        """Test JobInfo initialization."""
        info = JobInfo(
            id="job-1",
            handler="test.module:handler",
            cron="*/5 * * * *",
        )

        assert info.id == "job-1"
        assert info.handler == "test.module:handler"
        assert info.cron == "*/5 * * * *"
        assert info.status == JobStatus.ENABLED
        assert info.total_runs == 0
        assert info.successful_runs == 0
        assert info.failed_runs == 0

    def test_job_info_success_rate_zero(self) -> None:
        """Test success rate when no runs."""
        info = JobInfo(
            id="job-1",
            handler="test:handler",
            cron="* * * * *",
        )

        assert info.success_rate == 0.0

    def test_job_info_success_rate_calculated(self) -> None:
        """Test success rate calculation."""
        info = JobInfo(
            id="job-1",
            handler="test:handler",
            cron="* * * * *",
            total_runs=10,
            successful_runs=8,
        )

        assert info.success_rate == 0.8


# ============================================================================
# DaemonStats Tests
# ============================================================================


class TestDaemonStats:
    """Tests for DaemonStats model."""

    def test_daemon_stats_init(self) -> None:
        """Test DaemonStats initialization."""
        stats = DaemonStats()

        assert stats.started_at is None
        assert stats.total_jobs == 0
        assert stats.active_jobs == 0
        assert stats.total_executions == 0

    def test_daemon_stats_with_values(self) -> None:
        """Test DaemonStats with values."""
        now = datetime.utcnow()
        stats = DaemonStats(
            started_at=now,
            total_jobs=5,
            active_jobs=3,
            total_executions=100,
            successful_executions=95,
            failed_executions=5,
        )

        assert stats.started_at == now
        assert stats.total_jobs == 5
        assert stats.active_jobs == 3
        assert stats.total_executions == 100


# ============================================================================
# SchedulerDaemon Init Tests
# ============================================================================


class TestSchedulerDaemonInit:
    """Tests for SchedulerDaemon initialization."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        daemon = SchedulerDaemon()

        assert daemon.status == DaemonStatus.STOPPED
        assert daemon.is_running is False
        assert daemon._graceful_timeout == 10

    def test_init_with_config(self, mock_config: MagicMock) -> None:
        """Test initialization with config."""
        daemon = SchedulerDaemon(config=mock_config)

        assert daemon._config == mock_config
        assert daemon.status == DaemonStatus.STOPPED

    def test_init_custom_timeout(self) -> None:
        """Test initialization with custom timeout."""
        daemon = SchedulerDaemon(graceful_timeout=30)

        assert daemon._graceful_timeout == 30

    def test_config_property_lazy_load(self) -> None:
        """Test config property loads config lazily."""
        daemon = SchedulerDaemon()

        with patch("autoflow.scheduler.daemon.load_config") as mock_load:
            mock_load.return_value = MagicMock()
            _ = daemon.config
            mock_load.assert_called_once()


# ============================================================================
# SchedulerDaemon Lifecycle Tests
# ============================================================================


class TestSchedulerDaemonLifecycle:
    """Tests for SchedulerDaemon lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_creates_scheduler(self, daemon: SchedulerDaemon) -> None:
        """Test start creates APScheduler."""
        await daemon.start()

        assert daemon.status == DaemonStatus.RUNNING
        assert daemon._scheduler is not None
        assert daemon.stats.started_at is not None

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, daemon: SchedulerDaemon) -> None:
        """Test start is idempotent."""
        await daemon.start()
        first_status = daemon.status

        await daemon.start()  # Second call

        assert daemon.status == first_status

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_scheduler(self, daemon: SchedulerDaemon) -> None:
        """Test stop clears scheduler."""
        await daemon.start()
        await daemon.stop()

        assert daemon.status == DaemonStatus.STOPPED
        assert daemon._scheduler is None

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, daemon: SchedulerDaemon) -> None:
        """Test stop is idempotent."""
        await daemon.start()
        await daemon.stop()

        await daemon.stop()  # Second call

        assert daemon.status == DaemonStatus.STOPPED

    @pytest.mark.asyncio
    async def test_pause_and_resume(self, daemon: SchedulerDaemon) -> None:
        """Test pause and resume."""
        await daemon.start()

        await daemon.pause()
        assert daemon.status == DaemonStatus.PAUSED

        await daemon.resume()
        assert daemon.status == DaemonStatus.RUNNING

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_config: MagicMock) -> None:
        """Test async context manager usage."""
        async with SchedulerDaemon(config=mock_config) as daemon:
            assert daemon.status == DaemonStatus.RUNNING

        assert daemon.status == DaemonStatus.STOPPED


# ============================================================================
# SchedulerDaemon Job Management Tests
# ============================================================================


class TestSchedulerDaemonJobManagement:
    """Tests for SchedulerDaemon job management."""

    @pytest.mark.asyncio
    async def test_add_job(self, daemon: SchedulerDaemon) -> None:
        """Test adding a job."""
        await daemon.start()

        async def handler():
            pass

        job_id = await daemon.add_job(
            handler=handler,
            cron="*/5 * * * *",
            job_id="test-job",
        )

        assert job_id == "test-job"
        assert "test-job" in daemon._jobs
        assert daemon.get_job_info("test-job") is not None

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_add_job_auto_id(self, daemon: SchedulerDaemon) -> None:
        """Test adding a job with auto-generated ID."""
        await daemon.start()

        async def handler():
            pass

        job_id = await daemon.add_job(handler=handler, cron="* * * * *")

        assert job_id.startswith("job-")
        assert len(job_id) == 12  # "job-" + 8 hex chars

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_remove_job(self, daemon: SchedulerDaemon) -> None:
        """Test removing a job."""
        await daemon.start()

        async def handler():
            pass

        await daemon.add_job(handler=handler, cron="* * * * *", job_id="test-job")
        assert "test-job" in daemon._jobs

        result = await daemon.remove_job("test-job")

        assert result is True
        assert "test-job" not in daemon._jobs

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_remove_job_not_found(self, daemon: SchedulerDaemon) -> None:
        """Test removing non-existent job."""
        await daemon.start()

        result = await daemon.remove_job("nonexistent")

        assert result is False

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_pause_job(self, daemon: SchedulerDaemon) -> None:
        """Test pausing a job."""
        await daemon.start()

        async def handler():
            pass

        await daemon.add_job(handler=handler, cron="* * * * *", job_id="test-job")
        result = await daemon.pause_job("test-job")

        assert result is True
        assert daemon._jobs["test-job"].status == JobStatus.PAUSED

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_resume_job(self, daemon: SchedulerDaemon) -> None:
        """Test resuming a paused job."""
        await daemon.start()

        async def handler():
            pass

        await daemon.add_job(handler=handler, cron="* * * * *", job_id="test-job")
        await daemon.pause_job("test-job")
        result = await daemon.resume_job("test-job")

        assert result is True
        assert daemon._jobs["test-job"].status == JobStatus.ENABLED

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_list_jobs(self, daemon: SchedulerDaemon) -> None:
        """Test listing jobs."""
        await daemon.start()

        async def handler():
            pass

        await daemon.add_job(handler=handler, cron="* * * * *", job_id="job-1")
        await daemon.add_job(handler=handler, cron="*/5 * * * *", job_id="job-2")

        jobs = daemon.list_jobs()

        assert len(jobs) == 2
        job_ids = [j.id for j in jobs]
        assert "job-1" in job_ids
        assert "job-2" in job_ids

        await daemon.stop()


# ============================================================================
# SchedulerDaemon Job Execution Tests
# ============================================================================


class TestSchedulerDaemonJobExecution:
    """Tests for SchedulerDaemon job execution."""

    @pytest.mark.asyncio
    async def test_run_job_now(self, daemon: SchedulerDaemon) -> None:
        """Test running a job immediately."""
        await daemon.start()

        call_count = 0

        async def handler():
            nonlocal call_count
            call_count += 1
            return "done"

        await daemon.add_job(handler=handler, cron="* * * * *", job_id="test-job")

        result = await daemon.run_job_now("test-job")

        assert result is not None
        assert result.success is True
        assert call_count == 1

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_run_job_now_not_found(self, daemon: SchedulerDaemon) -> None:
        """Test running non-existent job."""
        await daemon.start()

        result = await daemon.run_job_now("nonexistent")

        assert result is None

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_job_execution_tracks_stats(self, daemon: SchedulerDaemon) -> None:
        """Test job execution updates stats."""
        await daemon.start()

        async def handler():
            return "result"

        await daemon.add_job(handler=handler, cron="* * * * *", job_id="test-job")
        await daemon.run_job_now("test-job")

        job_info = daemon.get_job_info("test-job")
        assert job_info is not None
        assert job_info.total_runs == 1
        assert job_info.successful_runs == 1
        assert job_info.last_result is not None
        assert job_info.last_result.success is True

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_job_execution_handles_error(self, daemon: SchedulerDaemon) -> None:
        """Test job execution handles errors."""
        await daemon.start()

        async def failing_handler():
            raise ValueError("Test error")

        await daemon.add_job(
            handler=failing_handler,
            cron="* * * * *",
            job_id="test-job",
        )
        result = await daemon.run_job_now("test-job")

        assert result is not None
        assert result.success is False
        assert "Test error" in result.error

        job_info = daemon.get_job_info("test-job")
        assert job_info is not None
        assert job_info.failed_runs == 1

        await daemon.stop()

    @pytest.mark.asyncio
    async def test_sync_handler_execution(self, daemon: SchedulerDaemon) -> None:
        """Test synchronous handler execution."""
        await daemon.start()

        call_count = 0

        def sync_handler():
            nonlocal call_count
            call_count += 1
            return "sync result"

        await daemon.add_job(
            handler=sync_handler,
            cron="* * * * *",
            job_id="sync-job",
        )
        result = await daemon.run_job_now("sync-job")

        assert result is not None
        assert result.success is True
        assert call_count == 1

        await daemon.stop()


# ============================================================================
# SchedulerDaemon Status Tests
# ============================================================================


class TestSchedulerDaemonStatus:
    """Tests for SchedulerDaemon status methods."""

    @pytest.mark.asyncio
    async def test_get_status_summary(self, daemon: SchedulerDaemon) -> None:
        """Test getting status summary."""
        await daemon.start()

        async def handler():
            pass

        await daemon.add_job(handler=handler, cron="* * * * *", job_id="test-job")

        summary = daemon.get_status_summary()

        assert "daemon" in summary
        assert summary["daemon"]["status"] == "running"
        assert summary["daemon"]["is_running"] is True
        assert "stats" in summary
        assert "jobs" in summary
        assert "test-job" in summary["jobs"]

        await daemon.stop()

    def test_repr(self, daemon: SchedulerDaemon) -> None:
        """Test string representation."""
        repr_str = repr(daemon)

        assert "SchedulerDaemon" in repr_str
        assert "stopped" in repr_str


# ============================================================================
# SchedulerDaemon Error Handling Tests
# ============================================================================


class TestSchedulerDaemonErrorHandling:
    """Tests for SchedulerDaemon error handling."""

    def test_scheduler_daemon_error(self) -> None:
        """Test SchedulerDaemonError exception."""
        error = SchedulerDaemonError("Test error", job_id="job-1")

        assert str(error) == "Test error"
        assert error.job_id == "job-1"

    @pytest.mark.asyncio
    async def test_add_job_without_scheduler(self, daemon: SchedulerDaemon) -> None:
        """Test adding job without initialized scheduler."""
        # Don't start the daemon
        async def handler():
            pass

        with pytest.raises(SchedulerDaemonError):
            await daemon.add_job(handler=handler, cron="* * * * *")

    def test_resolve_handler_invalid_path(self, daemon: SchedulerDaemon) -> None:
        """Test resolving invalid handler path."""
        with pytest.raises(SchedulerDaemonError):
            daemon._resolve_handler("invalid_path")

    def test_resolve_handler_module_not_found(self, daemon: SchedulerDaemon) -> None:
        """Test resolving handler from non-existent module."""
        with pytest.raises(SchedulerDaemonError):
            daemon._resolve_handler("nonexistent.module:handler")


# ============================================================================
# Orchestrator Reference Tests
# ============================================================================


class TestOrchestratorReference:
    """Tests for orchestrator reference management."""

    def test_set_and_get_orchestrator(self, mock_orchestrator: MagicMock) -> None:
        """Test setting and getting orchestrator reference."""
        set_orchestrator(mock_orchestrator)

        result = get_orchestrator()

        assert result == mock_orchestrator

        # Clean up
        set_orchestrator(None)

    def test_get_orchestrator_none(self) -> None:
        """Test getting orchestrator when not set."""
        set_orchestrator(None)

        result = get_orchestrator()

        assert result is None

    def test_daemon_set_orchestrator(
        self,
        daemon: SchedulerDaemon,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Test setting orchestrator on daemon."""
        daemon.set_orchestrator(mock_orchestrator)

        assert daemon._orchestrator == mock_orchestrator


# ============================================================================
# Job Handlers Tests
# ============================================================================


class TestMonitorAgentsJob:
    """Tests for monitor_agents job handler."""

    @pytest.mark.asyncio
    async def test_monitor_agents_no_runs(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test monitor_agents with no active runs."""
        with patch("autoflow.scheduler.jobs.StateManager", return_value=mock_state_manager):
            with patch("autoflow.scheduler.jobs.load_config", return_value=mock_config):
                result = await monitor_agents()

        assert result.success is True
        assert result.metrics["agents_checked"] == 0

    @pytest.mark.asyncio
    async def test_monitor_agents_with_healthy_run(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test monitor_agents with a healthy run."""
        mock_state_manager.list_runs.return_value = [
            {
                "id": "run-1",
                "agent": "claude-code",
                "status": "running",
                "started_at": datetime.utcnow().isoformat(),
            }
        ]

        with patch("autoflow.scheduler.jobs.StateManager", return_value=mock_state_manager):
            with patch("autoflow.scheduler.jobs.load_config", return_value=mock_config):
                result = await monitor_agents()

        assert result.success is True
        assert result.metrics["agents_checked"] == 1
        assert result.metrics["healthy_agents"] == 1

    @pytest.mark.asyncio
    async def test_monitor_agents_with_timeout(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Test monitor_agents detects timed out agent."""
        old_time = datetime.utcnow() - timedelta(seconds=1200)  # 20 mins ago
        mock_state_manager.list_runs.return_value = [
            {
                "id": "run-1",
                "agent": "claude-code",
                "status": "running",
                "started_at": old_time.isoformat(),
            }
        ]

        set_orchestrator(mock_orchestrator)

        with patch("autoflow.scheduler.jobs.StateManager", return_value=mock_state_manager):
            with patch("autoflow.scheduler.jobs.load_config", return_value=mock_config):
                result = await monitor_agents()

        assert result.success is True
        assert result.metrics["unhealthy_agents"] == 1

        set_orchestrator(None)


class TestDistributeTasksJob:
    """Tests for distribute_tasks job handler."""

    @pytest.mark.asyncio
    async def test_distribute_tasks_no_pending(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test distribute_tasks with no pending tasks."""
        with patch("autoflow.scheduler.jobs.StateManager", return_value=mock_state_manager):
            with patch("autoflow.scheduler.jobs.load_config", return_value=mock_config):
                result = await distribute_tasks()

        assert result.success is True
        assert result.metrics["tasks_distributed"] == 0
        assert result.metrics["tasks_pending"] == 0

    @pytest.mark.asyncio
    async def test_distribute_tasks_with_pending(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test distribute_tasks with pending tasks."""
        mock_state_manager.list_tasks.return_value = [
            {
                "id": "task-1",
                "title": "Test task",
                "description": "Test description",
                "status": "pending",
                "priority": 5,
            }
        ]

        with patch("autoflow.scheduler.jobs.StateManager", return_value=mock_state_manager):
            with patch("autoflow.scheduler.jobs.load_config", return_value=mock_config):
                result = await distribute_tasks()

        assert result.success is True
        assert result.metrics["tasks_pending"] == 1


class TestCleanupSessionsJob:
    """Tests for cleanup_sessions job handler."""

    @pytest.mark.asyncio
    async def test_cleanup_sessions(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test cleanup_sessions job."""
        with patch("autoflow.scheduler.jobs.StateManager", return_value=mock_state_manager):
            with patch("autoflow.scheduler.jobs.load_config", return_value=mock_config):
                result = await cleanup_sessions()

        assert result.success is True
        assert "sessions_cleaned" in result.metrics
        assert "memory_cleaned" in result.metrics


class TestHealthCheckJob:
    """Tests for health_check job handler."""

    @pytest.mark.asyncio
    async def test_health_check(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test health_check job."""
        mock_state_manager.state_dir.exists.return_value = True

        with patch("autoflow.scheduler.jobs.StateManager", return_value=mock_state_manager):
            with patch("autoflow.scheduler.jobs.load_config", return_value=mock_config):
                with patch("autoflow.tmux.manager.TmuxManager.check_tmux_available", return_value=False):
                    result = await health_check()

        assert "state_accessible" in result.metrics
        assert "tmux_available" in result.metrics


# ============================================================================
# Job Registry Tests
# ============================================================================


class TestJobRegistry:
    """Tests for JOB_REGISTRY."""

    def test_registry_contains_expected_jobs(self) -> None:
        """Test registry contains expected jobs."""
        assert "monitor_agents" in JOB_REGISTRY
        assert "distribute_tasks" in JOB_REGISTRY
        assert "cleanup_sessions" in JOB_REGISTRY
        assert "health_check" in JOB_REGISTRY

    def test_registry_entries_have_handlers(self) -> None:
        """Test registry entries have callable handlers."""
        for _job_name, job_config in JOB_REGISTRY.items():
            assert "handler" in job_config
            assert callable(job_config["handler"])
            assert "default_cron" in job_config
            assert "description" in job_config


# ============================================================================
# Integration Tests
# ============================================================================


class TestSchedulerIntegration:
    """Integration tests for scheduler components."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_jobs(self, mock_config: MagicMock) -> None:
        """Test full daemon lifecycle with job management."""
        async with SchedulerDaemon(config=mock_config) as daemon:
            # Add jobs
            async def handler1():
                return "result1"

            async def handler2():
                return "result2"

            await daemon.add_job(
                handler=handler1,
                cron="*/5 * * * *",
                job_id="job-1",
            )
            await daemon.add_job(
                handler=handler2,
                cron="*/10 * * * *",
                job_id="job-2",
            )

            assert len(daemon.list_jobs()) == 2

            # Run a job
            result = await daemon.run_job_now("job-1")
            assert result is not None
            assert result.success is True

            # Pause and resume
            await daemon.pause_job("job-2")
            assert daemon._jobs["job-2"].status == JobStatus.PAUSED

            await daemon.resume_job("job-2")
            assert daemon._jobs["job-2"].status == JobStatus.ENABLED

            # Remove a job
            await daemon.remove_job("job-1")
            assert len(daemon.list_jobs()) == 1

        # Verify daemon is stopped
        assert daemon.status == DaemonStatus.STOPPED

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_running_job(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Test graceful shutdown waits for running job."""
        daemon = SchedulerDaemon(config=mock_config, graceful_timeout=5)
        await daemon.start()

        execution_complete = asyncio.Event()

        async def slow_handler():
            await asyncio.sleep(0.5)
            execution_complete.set()
            return "done"

        await daemon.add_job(handler=slow_handler, cron="* * * * *", job_id="slow-job")

        # Trigger job execution
        task = asyncio.create_task(daemon.run_job_now("slow-job"))

        # Small delay to let job start
        await asyncio.sleep(0.1)

        # Stop daemon (should wait for job)
        await daemon.stop()

        # Job should have completed
        assert execution_complete.is_set()

        await task
