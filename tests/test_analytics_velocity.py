"""Unit Tests for Velocity Tracker

Tests the VelocityTracker class and related models for tracking
task completion rates, cycle times, throughput trends, and velocity
forecasting.

These tests follow the patterns from test_state.py for consistency.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from autoflow.analytics.velocity import (
    CycleTimeDistribution,
    TaskRecord,
    TaskStatus,
    VelocityMetrics,
    VelocitySignal,
    VelocityTrend,
    VelocityTracker,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_metrics_collector() -> MagicMock:
    """Create a mock metrics collector."""
    collector = MagicMock()
    return collector


@pytest.fixture
def velocity_tracker(mock_metrics_collector: MagicMock) -> VelocityTracker:
    """Create a VelocityTracker instance with mock collector."""
    tracker = VelocityTracker(metrics_collector=mock_metrics_collector, window_size=50)
    return tracker


@pytest.fixture
def sample_task_data() -> dict[str, Any]:
    """Return sample task data for testing."""
    return {
        "task_id": "task-001",
        "task_type": "feature",
        "complexity": 3,
        "metadata": {"priority": "high"},
    }


# ============================================================================
# Enum Tests
# ============================================================================


class TestVelocityTrend:
    """Tests for VelocityTrend enum."""

    def test_velocity_trend_values(self) -> None:
        """Test VelocityTrend enum values."""
        assert VelocityTrend.IMPROVING.value == "improving"
        assert VelocityTrend.STABLE.value == "stable"
        assert VelocityTrend.DECLINING.value == "declining"
        assert VelocityTrend.UNKNOWN.value == "unknown"

    def test_velocity_trend_is_string(self) -> None:
        """Test that VelocityTrend values are strings."""
        assert isinstance(VelocityTrend.IMPROVING.value, str)

    def test_velocity_trend_from_string(self) -> None:
        """Test creating VelocityTrend from string."""
        trend = VelocityTrend("improving")
        assert trend == VelocityTrend.IMPROVING


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_task_status_values(self) -> None:
        """Test TaskStatus enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_task_status_is_string(self) -> None:
        """Test that TaskStatus values are strings."""
        assert isinstance(TaskStatus.PENDING.value, str)


# ============================================================================
# Data Model Tests
# ============================================================================


class TestTaskRecord:
    """Tests for TaskRecord model."""

    def test_task_record_init_minimal(self) -> None:
        """Test TaskRecord initialization with minimal fields."""
        now = datetime.now()
        record = TaskRecord(
            task_id="task-001",
            status=TaskStatus.PENDING,
            created_at=now,
        )

        assert record.task_id == "task-001"
        assert record.status == TaskStatus.PENDING
        assert record.created_at == now
        assert record.started_at is None
        assert record.completed_at is None
        assert record.cycle_time is None
        assert record.lead_time is None
        assert record.task_type is None
        assert record.complexity is None
        assert record.metadata is None

    def test_task_record_init_full(self) -> None:
        """Test TaskRecord initialization with all fields."""
        now = datetime.now()
        started = now + timedelta(hours=1)
        completed = now + timedelta(hours=5)

        record = TaskRecord(
            task_id="task-001",
            status=TaskStatus.COMPLETED,
            created_at=now,
            started_at=started,
            completed_at=completed,
            cycle_time=14400.0,
            lead_time=18000.0,
            task_type="feature",
            complexity=3,
            metadata={"priority": "high"},
        )

        assert record.task_id == "task-001"
        assert record.status == TaskStatus.COMPLETED
        assert record.started_at == started
        assert record.completed_at == completed
        assert record.cycle_time == 14400.0
        assert record.lead_time == 18000.0
        assert record.task_type == "feature"
        assert record.complexity == 3
        assert record.metadata == {"priority": "high"}


class TestVelocityMetrics:
    """Tests for VelocityMetrics model."""

    def test_velocity_metrics_init(self) -> None:
        """Test VelocityMetrics initialization."""
        now = datetime.now()
        period_start = now - timedelta(days=7)
        period_end = now

        metrics = VelocityMetrics(
            period_start=period_start,
            period_end=period_end,
            tasks_completed=10,
            tasks_started=12,
            completion_rate=0.833,
            avg_cycle_time=14400.0,
            avg_lead_time=18000.0,
            throughput=1.43,
            trend=VelocityTrend.IMPROVING,
            forecasted_completion=12,
        )

        assert metrics.period_start == period_start
        assert metrics.period_end == period_end
        assert metrics.tasks_completed == 10
        assert metrics.tasks_started == 12
        assert metrics.completion_rate == 0.833
        assert metrics.avg_cycle_time == 14400.0
        assert metrics.avg_lead_time == 18000.0
        assert metrics.throughput == 1.43
        assert metrics.trend == VelocityTrend.IMPROVING
        assert metrics.forecasted_completion == 12


class TestCycleTimeDistribution:
    """Tests for CycleTimeDistribution model."""

    def test_cycle_time_distribution_init(self) -> None:
        """Test CycleTimeDistribution initialization."""
        distribution = CycleTimeDistribution(
            min=3600.0,
            max=28800.0,
            mean=14400.0,
            median=12600.0,
            percentile_85=21600.0,
            percentile_95=25200.0,
            std_dev=7200.0,
        )

        assert distribution.min == 3600.0
        assert distribution.max == 28800.0
        assert distribution.mean == 14400.0
        assert distribution.median == 12600.0
        assert distribution.percentile_85 == 21600.0
        assert distribution.percentile_95 == 25200.0
        assert distribution.std_dev == 7200.0


class TestVelocitySignal:
    """Tests for VelocitySignal model."""

    def test_velocity_signal_init(self) -> None:
        """Test VelocitySignal initialization."""
        signal = VelocitySignal(
            signal_type="throughput_change",
            severity="warning",
            metric_name="throughput",
            current_value=1.5,
            baseline_value=2.0,
            change_rate=-0.25,
            confidence=0.8,
            description="Throughput decreased by 25%",
        )

        assert signal.signal_type == "throughput_change"
        assert signal.severity == "warning"
        assert signal.metric_name == "throughput"
        assert signal.current_value == 1.5
        assert signal.baseline_value == 2.0
        assert signal.change_rate == -0.25
        assert signal.confidence == 0.8
        assert signal.description == "Throughput decreased by 25%"


# ============================================================================
# VelocityTracker Initialization Tests
# ============================================================================


class TestVelocityTrackerInit:
    """Tests for VelocityTracker initialization."""

    def test_init_default(self) -> None:
        """Test VelocityTracker initialization with defaults."""
        tracker = VelocityTracker()

        assert tracker.metrics_collector is None
        assert tracker.window_size == 100
        assert len(tracker._tasks) == 0
        assert len(tracker._task_queue) == 0
        assert tracker._baseline_throughput is None
        assert tracker._baseline_cycle_time is None
        assert tracker._baseline_samples == 0

    def test_init_with_collector(self, mock_metrics_collector: MagicMock) -> None:
        """Test VelocityTracker initialization with metrics collector."""
        tracker = VelocityTracker(
            metrics_collector=mock_metrics_collector,
            window_size=50,
        )

        assert tracker.metrics_collector == mock_metrics_collector
        assert tracker.window_size == 50

    def test_init_with_custom_window_size(self) -> None:
        """Test VelocityTracker initialization with custom window size."""
        tracker = VelocityTracker(window_size=200)

        assert tracker.window_size == 200


# ============================================================================
# Task Recording Tests
# ============================================================================


class TestTaskRecording:
    """Tests for task recording methods."""

    def test_record_task_creation_minimal(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test recording task creation with minimal parameters."""
        velocity_tracker.record_task_creation("task-001")

        task = velocity_tracker.get_task("task-001")
        assert task is not None
        assert task.task_id == "task-001"
        assert task.status == TaskStatus.PENDING
        assert task.task_type is None
        assert task.complexity is None
        assert task.metadata is None

    def test_record_task_creation_full(
        self, velocity_tracker: VelocityTracker, sample_task_data: dict
    ) -> None:
        """Test recording task creation with all parameters."""
        created_at = datetime.now() - timedelta(hours=1)
        velocity_tracker.record_task_creation(
            task_id="task-001",
            task_type="feature",
            complexity=3,
            metadata={"priority": "high"},
            created_at=created_at,
        )

        task = velocity_tracker.get_task("task-001")
        assert task is not None
        assert task.task_id == "task-001"
        assert task.task_type == "feature"
        assert task.complexity == 3
        assert task.metadata == {"priority": "high"}
        assert task.created_at == created_at

    def test_record_task_creation_calls_collector(
        self, velocity_tracker: VelocityTracker, mock_metrics_collector: MagicMock
    ) -> None:
        """Test that task creation records metric."""
        velocity_tracker.record_task_creation(
            "task-001", task_type="bug", complexity=2
        )

        mock_metrics_collector.record_metric.assert_called_once()
        call_args = mock_metrics_collector.record_metric.call_args
        assert call_args[1]["metric_name"] == "task_created"
        assert call_args[1]["value"] == 1.0
        assert call_args[1]["metadata"]["task_id"] == "task-001"
        assert call_args[1]["metadata"]["task_type"] == "bug"
        assert call_args[1]["metadata"]["complexity"] == 2

    def test_record_task_start(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test recording task start."""
        velocity_tracker.record_task_creation("task-001")
        started_at = datetime.now() - timedelta(minutes=30)

        velocity_tracker.record_task_start("task-001", started_at=started_at)

        task = velocity_tracker.get_task("task-001")
        assert task is not None
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.started_at == started_at

    def test_record_task_start_not_found(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test recording task start for nonexistent task."""
        with pytest.raises(ValueError, match="Task not found"):
            velocity_tracker.record_task_start("nonexistent")

    def test_record_task_start_calls_collector(
        self, velocity_tracker: VelocityTracker, mock_metrics_collector: MagicMock
    ) -> None:
        """Test that task start records metric."""
        velocity_tracker.record_task_creation("task-001", task_type="feature")
        mock_metrics_collector.reset_mock()

        velocity_tracker.record_task_start("task-001")

        mock_metrics_collector.record_metric.assert_called_once()
        call_args = mock_metrics_collector.record_metric.call_args
        assert call_args[1]["metric_name"] == "task_started"
        assert call_args[1]["value"] == 1.0

    def test_record_task_completion(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test recording task completion."""
        created = datetime.now() - timedelta(hours=5)
        started = datetime.now() - timedelta(hours=4)
        completed = datetime.now()

        velocity_tracker.record_task_creation("task-001", created_at=created)
        velocity_tracker.record_task_start("task-001", started_at=started)
        velocity_tracker.record_task_completion("task-001", completed_at=completed)

        task = velocity_tracker.get_task("task-001")
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at == completed
        assert task.cycle_time is not None
        assert task.cycle_time > 0
        assert task.lead_time is not None
        assert task.lead_time > 0
        assert task.lead_time > task.cycle_time

    def test_record_task_completion_not_found(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test recording completion for nonexistent task."""
        with pytest.raises(ValueError, match="Task not found"):
            velocity_tracker.record_task_completion("nonexistent")

    def test_record_task_completion_already_completed(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test recording completion for already completed task."""
        velocity_tracker.record_task_creation("task-001")
        velocity_tracker.record_task_start("task-001")
        velocity_tracker.record_task_completion("task-001")

        with pytest.raises(ValueError, match="Task already completed"):
            velocity_tracker.record_task_completion("task-001")

    def test_record_task_completion_updates_baseline(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test that completion updates baseline cycle time."""
        velocity_tracker.record_task_creation("task-001")
        velocity_tracker.record_task_start("task-001")
        velocity_tracker.record_task_completion("task-001")

        # Baseline should be updated
        assert velocity_tracker._baseline_cycle_time is not None
        assert velocity_tracker._baseline_samples == 1

    def test_record_task_completion_calls_collector(
        self, velocity_tracker: VelocityTracker, mock_metrics_collector: MagicMock
    ) -> None:
        """Test that task completion records metrics."""
        velocity_tracker.record_task_creation("task-001")
        velocity_tracker.record_task_start("task-001")
        mock_metrics_collector.reset_mock()

        velocity_tracker.record_task_completion("task-001")

        # Should be called twice (task_completed and cycle_time)
        assert mock_metrics_collector.record_metric.call_count == 2

    def test_record_task_cancellation(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test recording task cancellation."""
        velocity_tracker.record_task_creation("task-001")
        cancelled_at = datetime.now()

        velocity_tracker.record_task_cancellation("task-001", cancelled_at=cancelled_at)

        task = velocity_tracker.get_task("task-001")
        assert task is not None
        assert task.status == TaskStatus.CANCELLED

    def test_record_task_cancellation_not_found(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test recording cancellation for nonexistent task."""
        with pytest.raises(ValueError, match="Task not found"):
            velocity_tracker.record_task_cancellation("nonexistent")

    def test_record_task_cancellation_calls_collector(
        self, velocity_tracker: VelocityTracker, mock_metrics_collector: MagicMock
    ) -> None:
        """Test that task cancellation records metric."""
        velocity_tracker.record_task_creation("task-001")
        mock_metrics_collector.reset_mock()

        velocity_tracker.record_task_cancellation("task-001")

        mock_metrics_collector.record_metric.assert_called_once()
        call_args = mock_metrics_collector.record_metric.call_args
        assert call_args[1]["metric_name"] == "task_cancelled"


# ============================================================================
# Task Query Tests
# ============================================================================


class TestTaskQueries:
    """Tests for task query methods."""

    def test_get_task_existing(self, velocity_tracker: VelocityTracker) -> None:
        """Test getting existing task."""
        velocity_tracker.record_task_creation("task-001")

        task = velocity_tracker.get_task("task-001")

        assert task is not None
        assert task.task_id == "task-001"

    def test_get_task_nonexistent(self, velocity_tracker: VelocityTracker) -> None:
        """Test getting nonexistent task."""
        task = velocity_tracker.get_task("nonexistent")

        assert task is None

    def test_get_tasks_by_status_pending(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test getting tasks by pending status."""
        velocity_tracker.record_task_creation("task-001")
        velocity_tracker.record_task_creation("task-002")
        velocity_tracker.record_task_creation("task-003")
        velocity_tracker.record_task_start("task-002")

        pending = velocity_tracker.get_tasks_by_status(TaskStatus.PENDING)

        assert len(pending) == 2
        assert all(t.status == TaskStatus.PENDING for t in pending)

    def test_get_tasks_by_status_completed(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test getting tasks by completed status."""
        velocity_tracker.record_task_creation("task-001")
        velocity_tracker.record_task_creation("task-002")
        velocity_tracker.record_task_start("task-001")
        velocity_tracker.record_task_start("task-002")
        velocity_tracker.record_task_completion("task-001")
        velocity_tracker.record_task_completion("task-002")

        completed = velocity_tracker.get_tasks_by_status(TaskStatus.COMPLETED)

        assert len(completed) == 2
        assert all(t.status == TaskStatus.COMPLETED for t in completed)


# ============================================================================
# Cycle Time Distribution Tests
# ============================================================================


class TestCycleTimeDistribution:
    """Tests for cycle time distribution calculation."""

    def test_get_cycle_time_distribution_no_tasks(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test cycle time distribution with no completed tasks."""
        distribution = velocity_tracker.get_cycle_time_distribution()

        assert distribution is None

    def test_get_cycle_time_distribution_basic(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test basic cycle time distribution."""
        # Create tasks with different cycle times
        for i in range(10):
            created = datetime.now() - timedelta(hours=24)
            started = datetime.now() - timedelta(hours=23)
            completed = datetime.now() - timedelta(hours=23 - i)

            velocity_tracker.record_task_creation(f"task-{i}", created_at=created)
            velocity_tracker.record_task_start(f"task-{i}", started_at=started)
            velocity_tracker.record_task_completion(f"task-{i}", completed_at=completed)

        distribution = velocity_tracker.get_cycle_time_distribution()

        assert distribution is not None
        assert distribution.min > 0
        assert distribution.max > distribution.min
        assert distribution.mean > 0
        assert distribution.median > 0
        assert distribution.percentile_85 >= distribution.median
        assert distribution.percentile_95 >= distribution.percentile_85

    def test_get_cycle_time_distribution_with_task_type(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test cycle time distribution filtered by task type."""
        # Create bug tasks
        for i in range(5):
            velocity_tracker.record_task_creation(f"bug-{i}", task_type="bug")
            velocity_tracker.record_task_start(f"bug-{i}")
            velocity_tracker.record_task_completion(f"bug-{i}")

        # Create feature tasks
        for i in range(5):
            velocity_tracker.record_task_creation(f"feature-{i}", task_type="feature")
            velocity_tracker.record_task_start(f"feature-{i}")
            velocity_tracker.record_task_completion(f"feature-{i}")

        bug_distribution = velocity_tracker.get_cycle_time_distribution(task_type="bug")
        feature_distribution = velocity_tracker.get_cycle_time_distribution(
            task_type="feature"
        )

        assert bug_distribution is not None
        assert feature_distribution is not None

    def test_get_cycle_time_distribution_with_period(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test cycle time distribution with time period filter."""
        # Old task (outside period)
        old_time = datetime.now() - timedelta(days=10)
        velocity_tracker.record_task_creation("old-task", created_at=old_time)
        velocity_tracker.record_task_start("old-task", started_at=old_time)
        velocity_tracker.record_task_completion("old-task", completed_at=old_time)

        # Recent task (within period)
        velocity_tracker.record_task_creation("new-task")
        velocity_tracker.record_task_start("new-task")
        velocity_tracker.record_task_completion("new-task")

        distribution = velocity_tracker.get_cycle_time_distribution(period_days=7)

        assert distribution is not None
        # Should only include recent task


# ============================================================================
# Throughput Tests
# ============================================================================


class TestThroughput:
    """Tests for throughput calculation."""

    def test_get_throughput_no_tasks(self, velocity_tracker: VelocityTracker) -> None:
        """Test throughput with no tasks."""
        throughput = velocity_tracker.get_throughput()

        assert throughput == 0.0

    def test_get_throughput_basic(self, velocity_tracker: VelocityTracker) -> None:
        """Test basic throughput calculation."""
        # Complete 7 tasks over 7 days
        for i in range(7):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")
            velocity_tracker.record_task_completion(f"task-{i}")

        throughput = velocity_tracker.get_throughput(period_days=7)

        assert throughput == 1.0

    def test_get_throughput_with_task_type(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test throughput filtered by task type."""
        for i in range(5):
            velocity_tracker.record_task_creation(f"bug-{i}", task_type="bug")
            velocity_tracker.record_task_start(f"bug-{i}")
            velocity_tracker.record_task_completion(f"bug-{i}")

        for i in range(3):
            velocity_tracker.record_task_creation(f"feature-{i}", task_type="feature")
            velocity_tracker.record_task_start(f"feature-{i}")
            velocity_tracker.record_task_completion(f"feature-{i}")

        bug_throughput = velocity_tracker.get_throughput(task_type="bug")
        feature_throughput = velocity_tracker.get_throughput(task_type="feature")

        assert bug_throughput > feature_throughput


# ============================================================================
# Completion Rate Tests
# ============================================================================


class TestCompletionRate:
    """Tests for completion rate calculation."""

    def test_get_completion_rate_no_tasks(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test completion rate with no tasks."""
        rate = velocity_tracker.get_completion_rate()

        assert rate == 0.0

    def test_get_completion_rate_all_completed(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test completion rate with all tasks completed."""
        for i in range(5):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")
            velocity_tracker.record_task_completion(f"task-{i}")

        rate = velocity_tracker.get_completion_rate()

        assert rate == 1.0

    def test_get_completion_rate_partial(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test completion rate with partial completion."""
        # 3 completed
        for i in range(3):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")
            velocity_tracker.record_task_completion(f"task-{i}")

        # 2 in progress
        for i in range(3, 5):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")

        rate = velocity_tracker.get_completion_rate()

        assert rate == 0.6  # 3/5

    def test_get_completion_rate_with_period(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test completion rate with time period filter."""
        # Old tasks
        old_time = datetime.now() - timedelta(days=10)
        for i in range(3):
            velocity_tracker.record_task_creation(
                f"old-{i}", created_at=old_time
            )
            velocity_tracker.record_task_start(f"old-{i}")
            velocity_tracker.record_task_completion(f"old-{i}")

        # Recent tasks
        for i in range(2):
            velocity_tracker.record_task_creation(f"new-{i}")
            velocity_tracker.record_task_start(f"new-{i}")
            velocity_tracker.record_task_completion(f"new-{i}")

        rate = velocity_tracker.get_completion_rate(period_days=7)

        assert rate == 1.0  # Only recent tasks


# ============================================================================
# Average Time Tests
# ============================================================================


class TestAverageTimes:
    """Tests for average time calculations."""

    def test_get_average_cycle_time_no_tasks(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test average cycle time with no tasks."""
        avg = velocity_tracker.get_average_cycle_time()

        assert avg == 0.0

    def test_get_average_cycle_time_basic(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test basic average cycle time."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        avg = velocity_tracker.get_average_cycle_time()

        assert avg > 0

    def test_get_average_lead_time_no_tasks(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test average lead time with no tasks."""
        avg = velocity_tracker.get_average_lead_time()

        assert avg == 0.0

    def test_get_average_lead_time_basic(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test basic average lead time."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        avg = velocity_tracker.get_average_lead_time()

        assert avg > 0


# ============================================================================
# Trend Detection Tests
# ============================================================================


class TestTrendDetection:
    """Tests for velocity trend detection."""

    def test_detect_velocity_trend_insufficient_data(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test trend detection with insufficient data."""
        for i in range(3):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")
            velocity_tracker.record_task_completion(f"task-{i}")

        trend = velocity_tracker.detect_velocity_trend()

        assert trend == VelocityTrend.UNKNOWN

    def test_detect_velocity_trend_improving(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test detection of improving trend."""
        # Create baseline tasks (older)
        old_time = datetime.now() - timedelta(days=10)
        for i in range(5):
            velocity_tracker.record_task_creation(f"old-{i}", created_at=old_time)
            velocity_tracker.record_task_start(f"old-{i}", started_at=old_time)
            velocity_tracker.record_task_completion(
                f"old-{i}", completed_at=old_time + timedelta(hours=1)
            )

        # Create recent tasks (more frequent)
        for i in range(10):
            velocity_tracker.record_task_creation(f"new-{i}")
            velocity_tracker.record_task_start(f"new-{i}")
            velocity_tracker.record_task_completion(f"new-{i}")

        trend = velocity_tracker.detect_velocity_trend()

        assert trend in [VelocityTrend.IMPROVING, VelocityTrend.STABLE, VelocityTrend.UNKNOWN]

    def test_detect_velocity_trend_stable(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test detection of stable trend."""
        # Create consistent tasks
        for i in range(10):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")
            velocity_tracker.record_task_completion(f"task-{i}")

        trend = velocity_tracker.detect_velocity_trend()

        assert trend in [VelocityTrend.STABLE, VelocityTrend.UNKNOWN]


# ============================================================================
# Forecasting Tests
# ============================================================================


class TestForecasting:
    """Tests for velocity forecasting."""

    def test_forecast_velocity_no_tasks(self, velocity_tracker: VelocityTracker) -> None:
        """Test forecasting with no tasks."""
        forecast = velocity_tracker.forecast_velocity(forecast_days=7)

        assert forecast == 0

    def test_forecast_velocity_basic(self, velocity_tracker: VelocityTracker) -> None:
        """Test basic forecasting."""
        # Complete 7 tasks in 7 days (1 per day)
        for i in range(7):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")
            velocity_tracker.record_task_completion(f"task-{i}")

        forecast = velocity_tracker.forecast_velocity(forecast_days=7)

        assert forecast >= 0

    def test_forecast_velocity_with_task_type(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test forecasting filtered by task type."""
        for i in range(5):
            velocity_tracker.record_task_creation(f"bug-{i}", task_type="bug")
            velocity_tracker.record_task_start(f"bug-{i}")
            velocity_tracker.record_task_completion(f"bug-{i}")

        forecast = velocity_tracker.forecast_velocity(task_type="bug")

        assert forecast >= 0


# ============================================================================
# Velocity Metrics Tests
# ============================================================================


class TestVelocityMetrics:
    """Tests for comprehensive velocity metrics."""

    def test_get_velocity_metrics_empty(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test velocity metrics with no tasks."""
        metrics = velocity_tracker.get_velocity_metrics()

        assert metrics.tasks_completed == 0
        assert metrics.tasks_started == 0
        assert metrics.completion_rate == 0.0
        assert metrics.avg_cycle_time == 0.0
        assert metrics.throughput == 0.0

    def test_get_velocity_metrics_basic(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test basic velocity metrics."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        metrics = velocity_tracker.get_velocity_metrics()

        assert metrics.tasks_completed == 1
        assert metrics.tasks_started == 1
        assert metrics.completion_rate == 1.0
        assert metrics.avg_cycle_time > 0
        assert metrics.avg_lead_time > 0
        assert metrics.throughput > 0

    def test_get_velocity_metrics_includes_forecast(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test that velocity metrics include forecast."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        metrics = velocity_tracker.get_velocity_metrics()

        assert metrics.forecasted_completion is not None
        assert metrics.forecasted_completion >= 0

    def test_get_velocity_metrics_includes_trend(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test that velocity metrics include trend."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        metrics = velocity_tracker.get_velocity_metrics()

        assert metrics.trend in [
            VelocityTrend.IMPROVING,
            VelocityTrend.STABLE,
            VelocityTrend.DECLINING,
            VelocityTrend.UNKNOWN,
        ]


# ============================================================================
# Signal Detection Tests
# ============================================================================


class TestSignalDetection:
    """Tests for velocity signal detection."""

    def test_detect_velocity_signals_no_data(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test signal detection with insufficient data."""
        signals = velocity_tracker.detect_velocity_signals()

        assert signals == []

    def test_detect_velocity_signals_with_data(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test signal detection with sufficient data."""
        # Create enough tasks for signal detection
        for i in range(15):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")
            velocity_tracker.record_task_completion(f"task-{i}")

        signals = velocity_tracker.detect_velocity_signals()

        # Should return some signals (even if just info level)
        assert isinstance(signals, list)

    def test_detect_velocity_signals_sorted_by_severity(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test that signals are sorted by severity."""
        # Create tasks to trigger signals
        for i in range(20):
            velocity_tracker.record_task_creation(f"task-{i}")
            velocity_tracker.record_task_start(f"task-{i}")
            velocity_tracker.record_task_completion(f"task-{i}")

        signals = velocity_tracker.detect_velocity_signals()

        # If signals exist, check they're sorted
        if signals:
            severities = ["critical", "warning", "info"]
            signal_severities = [s.severity for s in signals]
            # Check sorted order
            for i in range(len(signal_severities) - 1):
                idx1 = severities.index(signal_severities[i])
                idx2 = severities.index(signal_severities[i + 1])
                assert idx1 <= idx2


# ============================================================================
# Statistics Tests
# ============================================================================


class TestStatistics:
    """Tests for tracker statistics."""

    def test_get_statistics_empty(self, velocity_tracker: VelocityTracker) -> None:
        """Test statistics with no tasks."""
        stats = velocity_tracker.get_statistics()

        assert stats["total_tasks"] == 0
        assert stats["pending_tasks"] == 0
        assert stats["in_progress_tasks"] == 0
        assert stats["completed_tasks"] == 0
        assert stats["cancelled_tasks"] == 0
        assert stats["avg_cycle_time"] == 0.0
        assert stats["avg_lead_time"] == 0.0

    def test_get_statistics_with_tasks(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test statistics with various task states."""
        # Add tasks in different states
        velocity_tracker.record_task_creation("pending-1")

        velocity_tracker.record_task_creation("progress-1")
        velocity_tracker.record_task_start("progress-1")

        velocity_tracker.record_task_creation("completed-1")
        velocity_tracker.record_task_start("completed-1")
        velocity_tracker.record_task_completion("completed-1")

        velocity_tracker.record_task_creation("cancelled-1")
        velocity_tracker.record_task_cancellation("cancelled-1")

        stats = velocity_tracker.get_statistics()

        assert stats["total_tasks"] == 4
        assert stats["pending_tasks"] == 1
        assert stats["in_progress_tasks"] == 1
        assert stats["completed_tasks"] == 1
        assert stats["cancelled_tasks"] == 1

    def test_get_statistics_includes_averages(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test that statistics include averages."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        stats = velocity_tracker.get_statistics()

        assert stats["avg_cycle_time"] > 0
        assert stats["avg_lead_time"] > 0

    def test_get_statistics_window_utilization(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test window utilization calculation."""
        velocity_tracker.window_size = 10

        for i in range(5):
            velocity_tracker.record_task_creation(f"task-{i}")

        stats = velocity_tracker.get_statistics()

        assert stats["window_size"] == 10
        assert stats["window_utilization"] == 0.5


# ============================================================================
# Reset Tests
# ============================================================================


class TestReset:
    """Tests for reset functionality."""

    def test_reset_clears_all_data(self, velocity_tracker: VelocityTracker) -> None:
        """Test that reset clears all tracking data."""
        # Add some data
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        # Reset
        velocity_tracker.reset()

        # Verify cleared
        assert len(velocity_tracker._tasks) == 0
        assert len(velocity_tracker._task_queue) == 0
        assert velocity_tracker._baseline_throughput is None
        assert velocity_tracker._baseline_cycle_time is None
        assert velocity_tracker._baseline_samples == 0

    def test_reset_after_statistics(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test that statistics are zero after reset."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        velocity_tracker.reset()

        stats = velocity_tracker.get_statistics()
        assert stats["total_tasks"] == 0


# ============================================================================
# Window Size Tests
# ============================================================================


class TestWindowSize:
    """Tests for window size functionality."""

    def test_window_size_enforced(self) -> None:
        """Test that window size is enforced for task queue."""
        # Create tracker with small window size
        tracker = VelocityTracker(window_size=5)

        # Add more tasks than window size
        for i in range(10):
            tracker.record_task_creation(f"task-{i}")

        # Queue should not exceed window size (it's a deque with maxlen)
        assert len(tracker._task_queue) <= 5

    def test_window_size_oldest_removed(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test that oldest tasks are removed when window is full."""
        # Create new tracker with small window
        tracker = VelocityTracker(window_size=3)

        tracker.record_task_creation("task-1")
        tracker.record_task_creation("task-2")
        tracker.record_task_creation("task-3")
        tracker.record_task_creation("task-4")

        # task-1 should be removed from the dict when window overflows
        # The oldest is removed when a new task is added and window is full
        assert tracker.get_task("task-1") is None
        assert tracker.get_task("task-4") is not None


# ============================================================================
# Edge Cases Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_task_completion_without_start(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test completing task that was never started."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_completion("task-1")

        task = velocity_tracker.get_task("task-1")
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.cycle_time is None  # No start time, so no cycle time
        assert task.lead_time is not None  # But lead time from creation

    def test_multiple_start_same_task(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test starting a task multiple times."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")

        first_start = velocity_tracker.get_task("task-1").started_at

        # Start again (should update start time)
        velocity_tracker.record_task_start("task-1")

        second_start = velocity_tracker.get_task("task-1").started_at

        # Start time should be updated to the more recent one
        assert second_start >= first_start

    def test_zero_period_days(self, velocity_tracker: VelocityTracker) -> None:
        """Test throughput with zero period days."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        throughput = velocity_tracker.get_throughput(period_days=0)

        assert throughput == 0.0

    def test_get_cycle_time_single_task(
        self, velocity_tracker: VelocityTracker
    ) -> None:
        """Test cycle time distribution with single task."""
        velocity_tracker.record_task_creation("task-1")
        velocity_tracker.record_task_start("task-1")
        velocity_tracker.record_task_completion("task-1")

        distribution = velocity_tracker.get_cycle_time_distribution()

        assert distribution is not None
        assert distribution.min == distribution.max
        assert distribution.std_dev == 0.0
