"""Velocity metrics tracking for task completion rates and cycle times.

This module provides comprehensive velocity tracking for development workflows,
tracking metrics such as task completion rates, cycle times, throughput trends,
and velocity forecasting. It follows the patterns from the health monitoring system
to provide consistent analytics.

The velocity tracker helps answer questions like:
- How many tasks are we completing per day/week/sprint?
- What is the average cycle time for tasks?
- Is our velocity improving or declining?
- What can we expect to complete in the next sprint?
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autoflow.analytics.metrics import MetricsCollector


class VelocityTrend(Enum):
    """Velocity trend direction."""

    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    UNKNOWN = "unknown"


class TaskStatus(Enum):
    """Status of a task in the velocity tracking."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    """A record of a task for velocity tracking.

    Attributes:
        task_id: Unique identifier for the task.
        status: Current status of the task.
        created_at: When the task was created.
        started_at: When work on the task began.
        completed_at: When the task was completed.
        cycle_time: Time from start to completion (in seconds).
        lead_time: Time from creation to completion (in seconds).
        task_type: Type/category of task.
        complexity: Complexity score (1-5).
        metadata: Additional context about the task.
    """

    task_id: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cycle_time: float | None = None
    lead_time: float | None = None
    task_type: str | None = None
    complexity: int | None = None
    metadata: dict | None = None


@dataclass
class VelocityMetrics:
    """Velocity metrics for a time period.

    Attributes:
        period_start: Start of the time period.
        period_end: End of the time period.
        tasks_completed: Number of tasks completed.
        tasks_started: Number of tasks started.
        completion_rate: Ratio of completed to started tasks.
        avg_cycle_time: Average cycle time in seconds.
        avg_lead_time: Average lead time in seconds.
        throughput: Tasks completed per day.
        trend: Velocity trend direction.
        forecasted_completion: Expected tasks to complete next period.
    """

    period_start: datetime
    period_end: datetime
    tasks_completed: int
    tasks_started: int
    completion_rate: float
    avg_cycle_time: float
    avg_lead_time: float
    throughput: float
    trend: VelocityTrend
    forecasted_completion: int | None = None


@dataclass
class CycleTimeDistribution:
    """Distribution of cycle times.

    Attributes:
        min: Fastest cycle time.
        max: Slowest cycle time.
        mean: Average cycle time.
        median: Median cycle time.
        percentile_85: 85th percentile cycle time.
        percentile_95: 95th percentile cycle time.
        std_dev: Standard deviation of cycle times.
    """

    min: float
    max: float
    mean: float
    median: float
    percentile_85: float
    percentile_95: float
    std_dev: float


@dataclass
class VelocitySignal:
    """A signal indicating change in velocity.

    Attributes:
        signal_type: Type of velocity signal.
        severity: Severity level (info, warning, critical).
        metric_name: Name of the velocity metric.
        current_value: Current metric value.
        baseline_value: Expected/baseline value.
        change_rate: Rate of change (e.g., 0.15 for 15% increase).
        confidence: Confidence score (0.0 to 1.0).
        description: Human-readable description.
    """

    signal_type: str
    severity: str
    metric_name: str
    current_value: float
    baseline_value: float
    change_rate: float
    confidence: float
    description: str


class VelocityTracker:
    """Track velocity metrics for development workflows.

    This tracker monitors task completion rates, cycle times, throughput trends,
    and provides velocity forecasting. It maintains rolling windows of historical
    data for trend analysis and change detection.

    The tracker uses statistical methods to detect:
    - Velocity improvements or declines
    - Cycle time anomalies
    - Throughput trends
    - Forecasting for upcoming periods

    Example:
        tracker = VelocityTracker()
        tracker.record_task_creation("task-1", task_type="feature")
        tracker.record_task_start("task-1")
        tracker.record_task_completion("task-1")

        metrics = tracker.get_velocity_metrics(period_days=7)
        print(f"Throughput: {metrics.throughput:.2f} tasks/day")
        print(f"Avg cycle time: {metrics.avg_cycle_time/3600:.2f} hours")
    """

    def __init__(
        self,
        metrics_collector: MetricsCollector | None = None,
        window_size: int = 100,
    ) -> None:
        """Initialize the velocity tracker.

        Args:
            metrics_collector: Optional metrics collector for persistence.
            window_size: Maximum number of task records to keep in rolling window.
        """
        self.metrics_collector = metrics_collector
        self.window_size = window_size

        # Rolling window of task records
        self._tasks: dict[str, TaskRecord] = {}
        self._task_queue: deque[str] = deque(maxlen=window_size)

        # Baseline metrics for comparison
        self._baseline_throughput: float | None = None
        self._baseline_cycle_time: float | None = None
        self._baseline_samples: int = 0

    def record_task_creation(
        self,
        task_id: str,
        task_type: str | None = None,
        complexity: int | None = None,
        metadata: dict | None = None,
        created_at: datetime | None = None,
    ) -> None:
        """Record the creation of a new task.

        Args:
            task_id: Unique identifier for the task.
            task_type: Type/category of task.
            complexity: Complexity score (1-5).
            metadata: Additional context about the task.
            created_at: When the task was created. Defaults to now.
        """
        if created_at is None:
            created_at = datetime.now()

        # Remove oldest task if at capacity
        if len(self._task_queue) >= self.window_size and task_id not in self._tasks:
            oldest_id = self._task_queue[0]
            if oldest_id in self._tasks:
                del self._tasks[oldest_id]

        self._tasks[task_id] = TaskRecord(
            task_id=task_id,
            status=TaskStatus.PENDING,
            created_at=created_at,
            task_type=task_type,
            complexity=complexity,
            metadata=metadata,
        )

        # Only add to queue if it's a new task
        if task_id not in self._task_queue or self._task_queue[-1] != task_id:
            self._task_queue.append(task_id)

        # Record metric if collector available
        if self.metrics_collector:
            self.metrics_collector.record_metric(
                metric_name="task_created",
                value=1.0,
                metadata={
                    "task_id": task_id,
                    "task_type": task_type,
                    "complexity": complexity,
                },
            )

    def record_task_start(
        self,
        task_id: str,
        started_at: datetime | None = None,
    ) -> None:
        """Record when work on a task begins.

        Args:
            task_id: Unique identifier for the task.
            started_at: When work began. Defaults to now.

        Raises:
            ValueError: If task not found.
        """
        if task_id not in self._tasks:
            raise ValueError(f"Task not found: {task_id}")

        if started_at is None:
            started_at = datetime.now()

        task = self._tasks[task_id]
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = started_at

        # Record metric if collector available
        if self.metrics_collector:
            self.metrics_collector.record_metric(
                metric_name="task_started",
                value=1.0,
                metadata={"task_id": task_id, "task_type": task.task_type},
            )

    def record_task_completion(
        self,
        task_id: str,
        completed_at: datetime | None = None,
    ) -> None:
        """Record the completion of a task.

        Args:
            task_id: Unique identifier for the task.
            completed_at: When the task was completed. Defaults to now.

        Raises:
            ValueError: If task not found or already completed.
        """
        if task_id not in self._tasks:
            raise ValueError(f"Task not found: {task_id}")

        if completed_at is None:
            completed_at = datetime.now()

        task = self._tasks[task_id]

        if task.status == TaskStatus.COMPLETED:
            raise ValueError(f"Task already completed: {task_id}")

        task.status = TaskStatus.COMPLETED
        task.completed_at = completed_at

        # Calculate cycle and lead time
        if task.started_at:
            task.cycle_time = (completed_at - task.started_at).total_seconds()
        if task.created_at:
            task.lead_time = (completed_at - task.created_at).total_seconds()

        # Update baseline if we have enough samples
        if task.cycle_time and self._baseline_samples < 10:
            if self._baseline_cycle_time is None:
                self._baseline_cycle_time = task.cycle_time
            else:
                self._baseline_cycle_time = (
                    self._baseline_cycle_time * 0.9 + task.cycle_time * 0.1
                )
            self._baseline_samples += 1

        # Record metric if collector available
        if self.metrics_collector:
            self.metrics_collector.record_metric(
                metric_name="task_completed",
                value=1.0,
                metadata={"task_id": task_id, "task_type": task.task_type},
            )
            if task.cycle_time:
                self.metrics_collector.record_metric(
                    metric_name="cycle_time",
                    value=task.cycle_time,
                    metadata={"task_id": task_id, "task_type": task.task_type},
                )

    def record_task_cancellation(
        self,
        task_id: str,
        cancelled_at: datetime | None = None,
    ) -> None:
        """Record the cancellation of a task.

        Args:
            task_id: Unique identifier for the task.
            cancelled_at: When the task was cancelled. Defaults to now.

        Raises:
            ValueError: If task not found.
        """
        if task_id not in self._tasks:
            raise ValueError(f"Task not found: {task_id}")

        if cancelled_at is None:
            cancelled_at = datetime.now()

        task = self._tasks[task_id]
        task.status = TaskStatus.CANCELLED

        # Record metric if collector available
        if self.metrics_collector:
            self.metrics_collector.record_metric(
                metric_name="task_cancelled",
                value=1.0,
                metadata={"task_id": task_id, "task_type": task.task_type},
            )

    def get_task(self, task_id: str) -> TaskRecord | None:
        """Get a task record by ID.

        Args:
            task_id: Unique identifier for the task.

        Returns:
            TaskRecord if found, None otherwise.
        """
        return self._tasks.get(task_id)

    def get_tasks_by_status(self, status: TaskStatus) -> list[TaskRecord]:
        """Get all tasks with a specific status.

        Args:
            status: Status to filter by.

        Returns:
            List of tasks with the specified status.
        """
        return [task for task in self._tasks.values() if task.status == status]

    def get_cycle_time_distribution(
        self,
        task_type: str | None = None,
        period_days: int | None = None,
    ) -> CycleTimeDistribution | None:
        """Calculate cycle time distribution.

        Args:
            task_type: Filter by task type. If None, includes all types.
            period_days: Only include tasks completed in the last N days.
                        If None, includes all completed tasks.

        Returns:
            CycleTimeDistribution with statistics, or None if no completed tasks.
        """
        # Filter completed tasks with cycle times
        cycle_times = []
        cutoff_date = None

        if period_days:
            cutoff_date = datetime.now() - timedelta(days=period_days)

        for task in self._tasks.values():
            if task.status != TaskStatus.COMPLETED or task.cycle_time is None:
                continue

            if task_type and task.task_type != task_type:
                continue

            if cutoff_date and task.completed_at and task.completed_at < cutoff_date:
                continue

            cycle_times.append(task.cycle_time)

        if not cycle_times:
            return None

        # Calculate statistics
        cycle_times_sorted = sorted(cycle_times)
        n = len(cycle_times_sorted)

        p85_idx = int(n * 0.85)
        p95_idx = int(n * 0.95)

        return CycleTimeDistribution(
            min=min(cycle_times),
            max=max(cycle_times),
            mean=statistics.mean(cycle_times),
            median=statistics.median(cycle_times),
            percentile_85=cycle_times_sorted[p85_idx],
            percentile_95=cycle_times_sorted[p95_idx],
            std_dev=statistics.stdev(cycle_times) if n > 1 else 0.0,
        )

    def get_throughput(
        self,
        period_days: int = 7,
        task_type: str | None = None,
    ) -> float:
        """Calculate throughput (tasks completed per day).

        Args:
            period_days: Number of days to look back.
            task_type: Filter by task type. If None, includes all types.

        Returns:
            Throughput as tasks completed per day.
        """
        cutoff_date = datetime.now() - timedelta(days=period_days)

        completed_count = 0
        for task in self._tasks.values():
            if task.status != TaskStatus.COMPLETED:
                continue

            if task_type and task.task_type != task_type:
                continue

            if task.completed_at and task.completed_at >= cutoff_date:
                completed_count += 1

        return completed_count / period_days if period_days > 0 else 0.0

    def get_completion_rate(
        self,
        period_days: int | None = None,
    ) -> float:
        """Calculate task completion rate.

        Args:
            period_days: Only consider tasks in the last N days.
                        If None, considers all tasks.

        Returns:
            Completion rate as a fraction (0.0 to 1.0).
        """
        cutoff_date = None

        if period_days:
            cutoff_date = datetime.now() - timedelta(days=period_days)

        started = 0
        completed = 0

        for task in self._tasks.values():
            # Filter by period if specified
            if cutoff_date and task.created_at < cutoff_date:
                continue

            # Count started tasks (pending + in_progress + completed)
            if task.status in [TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED]:
                started += 1
                if task.status == TaskStatus.COMPLETED:
                    completed += 1

        return completed / started if started > 0 else 0.0

    def get_average_cycle_time(
        self,
        task_type: str | None = None,
        period_days: int | None = None,
    ) -> float:
        """Calculate average cycle time.

        Args:
            task_type: Filter by task type. If None, includes all types.
            period_days: Only include tasks completed in the last N days.
                        If None, includes all completed tasks.

        Returns:
            Average cycle time in seconds.
        """
        distribution = self.get_cycle_time_distribution(
            task_type=task_type,
            period_days=period_days,
        )

        return distribution.mean if distribution else 0.0

    def get_average_lead_time(
        self,
        task_type: str | None = None,
        period_days: int | None = None,
    ) -> float:
        """Calculate average lead time.

        Args:
            task_type: Filter by task type. If None, includes all types.
            period_days: Only include tasks completed in the last N days.
                        If None, includes all completed tasks.

        Returns:
            Average lead time in seconds.
        """
        cutoff_date = None

        if period_days:
            cutoff_date = datetime.now() - timedelta(days=period_days)

        lead_times = []

        for task in self._tasks.values():
            if task.status != TaskStatus.COMPLETED or task.lead_time is None:
                continue

            if task_type and task.task_type != task_type:
                continue

            if cutoff_date and task.completed_at and task.completed_at < cutoff_date:
                continue

            lead_times.append(task.lead_time)

        return statistics.mean(lead_times) if lead_times else 0.0

    def detect_velocity_trend(
        self,
        period_days: int = 7,
        min_samples: int = 5,
    ) -> VelocityTrend:
        """Detect velocity trend using throughput analysis.

        Compares recent throughput to historical baseline to determine
        if velocity is improving, stable, or declining.

        Args:
            period_days: Number of days to analyze.
            min_samples: Minimum number of data points required for trend detection.

        Returns:
            VelocityTrend indicating direction.
        """
        if len(self._tasks) < min_samples:
            return VelocityTrend.UNKNOWN

        # Calculate recent throughput
        recent_throughput = self.get_throughput(period_days=period_days)

        # Calculate baseline throughput if not set
        if self._baseline_throughput is None:
            # Use throughput from older period as baseline
            baseline_start = datetime.now() - timedelta(days=period_days * 2)
            baseline_end = datetime.now() - timedelta(days=period_days)

            baseline_completed = 0
            for task in self._tasks.values():
                if (
                    task.status == TaskStatus.COMPLETED
                    and task.completed_at
                    and baseline_start <= task.completed_at < baseline_end
                ):
                    baseline_completed += 1

            self._baseline_throughput = baseline_completed / period_days if period_days > 0 else 0.0

        # If no baseline, can't determine trend
        if self._baseline_throughput is None or self._baseline_throughput == 0:
            return VelocityTrend.UNKNOWN

        # Calculate change rate
        change_rate = (recent_throughput - self._baseline_throughput) / self._baseline_throughput

        # Determine trend based on change rate
        if change_rate > 0.15:  # 15% improvement
            return VelocityTrend.IMPROVING
        elif change_rate < -0.15:  # 15% decline
            return VelocityTrend.DECLINING
        else:
            return VelocityTrend.STABLE

    def forecast_velocity(
        self,
        forecast_days: int = 7,
        task_type: str | None = None,
    ) -> int:
        """Forecast expected task completions for upcoming period.

        Uses recent throughput trends to forecast expected completions.

        Args:
            forecast_days: Number of days to forecast.
            task_type: Filter by task type. If None, includes all types.

        Returns:
            Expected number of task completions.
        """
        # Get recent throughput
        throughput = self.get_throughput(period_days=7, task_type=task_type)

        # Simple forecast: throughput * days
        # Could be enhanced with trend analysis, seasonality, etc.
        forecast = int(throughput * forecast_days)

        return max(0, forecast)

    def get_velocity_metrics(
        self,
        period_days: int = 7,
    ) -> VelocityMetrics:
        """Get comprehensive velocity metrics for a time period.

        Args:
            period_days: Number of days to analyze.

        Returns:
            VelocityMetrics with all key metrics.
        """
        period_end = datetime.now()
        period_start = period_end - timedelta(days=period_days)

        # Count tasks started and completed in period
        tasks_started = 0
        tasks_completed = 0

        cycle_times = []
        lead_times = []

        for task in self._tasks.values():
            # Check if task was started in period
            if task.started_at and task.started_at >= period_start:
                tasks_started += 1

            # Check if task was completed in period
            if (
                task.status == TaskStatus.COMPLETED
                and task.completed_at
                and task.completed_at >= period_start
            ):
                tasks_completed += 1
                if task.cycle_time:
                    cycle_times.append(task.cycle_time)
                if task.lead_time:
                    lead_times.append(task.lead_time)

        # Calculate metrics
        completion_rate = (
            tasks_completed / tasks_started if tasks_started > 0 else 0.0
        )
        avg_cycle_time = (
            statistics.mean(cycle_times) if cycle_times else 0.0
        )
        avg_lead_time = (
            statistics.mean(lead_times) if lead_times else 0.0
        )
        throughput = tasks_completed / period_days if period_days > 0 else 0.0

        # Detect trend
        trend = self.detect_velocity_trend(period_days=period_days)

        # Forecast next period
        forecasted_completion = self.forecast_velocity(
            forecast_days=period_days,
        )

        return VelocityMetrics(
            period_start=period_start,
            period_end=period_end,
            tasks_completed=tasks_completed,
            tasks_started=tasks_started,
            completion_rate=completion_rate,
            avg_cycle_time=avg_cycle_time,
            avg_lead_time=avg_lead_time,
            throughput=throughput,
            trend=trend,
            forecasted_completion=forecasted_completion,
        )

    def detect_velocity_signals(self) -> list[VelocitySignal]:
        """Detect significant velocity changes and anomalies.

        Analyzes trends, anomalies, and patterns to identify velocity signals
        that may require attention or investigation.

        Returns:
            List of velocity signals ordered by severity.
        """
        signals = []

        # Detect throughput changes
        throughput_signal = self._detect_throughput_change()
        if throughput_signal:
            signals.append(throughput_signal)

        # Detect cycle time changes
        cycle_time_signal = self._detect_cycle_time_change()
        if cycle_time_signal:
            signals.append(cycle_time_signal)

        # Detect completion rate changes
        completion_rate_signal = self._detect_completion_rate_change()
        if completion_rate_signal:
            signals.append(completion_rate_signal)

        # Sort by severity (critical > warning > info)
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        signals.sort(key=lambda s: severity_order.get(s.severity, 3))

        return signals

    def _detect_throughput_change(self) -> VelocitySignal | None:
        """Detect significant throughput changes.

        Returns:
            VelocitySignal if significant change detected, None otherwise.
        """
        if len(self._tasks) < 10:
            return None

        recent_throughput = self.get_throughput(period_days=7)

        if self._baseline_throughput is None or self._baseline_throughput == 0:
            return None

        change_rate = (recent_throughput - self._baseline_throughput) / self._baseline_throughput

        # Determine severity
        severity = "info"
        if change_rate < -0.3:  # 30% decline
            severity = "critical"
        elif change_rate < -0.15:  # 15% decline
            severity = "warning"
        elif change_rate > 0.2:  # 20% improvement
            severity = "info"

        confidence = min(abs(change_rate) * 2, 1.0)

        # Only return signal if there's meaningful change
        if abs(change_rate) > 0.15:
            direction = "decreased" if change_rate < 0 else "increased"
            return VelocitySignal(
                signal_type="throughput_change",
                severity=severity,
                metric_name="throughput",
                current_value=recent_throughput,
                baseline_value=self._baseline_throughput,
                change_rate=change_rate,
                confidence=confidence,
                description=(
                    f"Throughput {direction} by {abs(change_rate) * 100:.1f}%. "
                    f"Current: {recent_throughput:.2f} tasks/day, "
                    f"Baseline: {self._baseline_throughput:.2f} tasks/day"
                ),
            )

        return None

    def _detect_cycle_time_change(self) -> VelocitySignal | None:
        """Detect significant cycle time changes.

        Returns:
            VelocitySignal if significant change detected, None otherwise.
        """
        if len(self._tasks) < 10:
            return None

        recent_cycle_time = self.get_average_cycle_time(period_days=7)

        if self._baseline_cycle_time is None or self._baseline_cycle_time == 0:
            return None

        change_rate = (
            (recent_cycle_time - self._baseline_cycle_time) / self._baseline_cycle_time
            if recent_cycle_time > 0
            else 0.0
        )

        # Determine severity (cycle time increasing is bad)
        severity = "info"
        if change_rate > 0.3:  # 30% slower
            severity = "critical"
        elif change_rate > 0.15:  # 15% slower
            severity = "warning"
        elif change_rate < -0.15:  # 15% faster (improvement)
            severity = "info"

        confidence = min(abs(change_rate) * 2, 1.0) if recent_cycle_time > 0 else 0.0

        # Only return signal if there's meaningful change
        if abs(change_rate) > 0.15 and recent_cycle_time > 0:
            direction = "increased" if change_rate > 0 else "decreased"
            return VelocitySignal(
                signal_type="cycle_time_change",
                severity=severity,
                metric_name="cycle_time",
                current_value=recent_cycle_time,
                baseline_value=self._baseline_cycle_time,
                change_rate=change_rate,
                confidence=confidence,
                description=(
                    f"Cycle time {direction} by {abs(change_rate) * 100:.1f}%. "
                    f"Current: {recent_cycle_time/3600:.2f} hours, "
                    f"Baseline: {self._baseline_cycle_time/3600:.2f} hours"
                ),
            )

        return None

    def _detect_completion_rate_change(self) -> VelocitySignal | None:
        """Detect significant completion rate changes.

        Returns:
            VelocitySignal if significant change detected, None otherwise.
        """
        if len(self._tasks) < 10:
            return None

        recent_rate = self.get_completion_rate(period_days=7)

        # Calculate historical completion rate for comparison
        historical_start = datetime.now() - timedelta(days=14)
        historical_end = datetime.now() - timedelta(days=7)

        historical_started = 0
        historical_completed = 0

        for task in self._tasks.values():
            if task.started_at and historical_start <= task.started_at < historical_end:
                historical_started += 1
                if task.status == TaskStatus.COMPLETED:
                    historical_completed += 1

        historical_rate = (
            historical_completed / historical_started if historical_started > 0 else 0.0
        )

        if historical_rate == 0:
            return None

        change_rate = (recent_rate - historical_rate) / historical_rate

        # Determine severity (completion rate decreasing is bad)
        severity = "info"
        if change_rate < -0.25:  # 25% decline
            severity = "critical"
        elif change_rate < -0.1:  # 10% decline
            severity = "warning"
        elif change_rate > 0.1:  # 10% improvement
            severity = "info"

        confidence = min(abs(change_rate) * 3, 1.0)

        # Only return signal if there's meaningful change
        if abs(change_rate) > 0.1:
            direction = "decreased" if change_rate < 0 else "increased"
            return VelocitySignal(
                signal_type="completion_rate_change",
                severity=severity,
                metric_name="completion_rate",
                current_value=recent_rate,
                baseline_value=historical_rate,
                change_rate=change_rate,
                confidence=confidence,
                description=(
                    f"Completion rate {direction} by {abs(change_rate) * 100:.1f}%. "
                    f"Current: {recent_rate*100:.1f}%, "
                    f"Historical: {historical_rate*100:.1f}%"
                ),
            )

        return None

    def get_statistics(self) -> dict:
        """Get current tracking statistics.

        Returns:
            Dictionary with statistics about tracked tasks.
        """
        total_tasks = len(self._tasks)
        status_counts = {
            TaskStatus.PENDING: 0,
            TaskStatus.IN_PROGRESS: 0,
            TaskStatus.COMPLETED: 0,
            TaskStatus.CANCELLED: 0,
        }

        cycle_times = []
        lead_times = []

        for task in self._tasks.values():
            status_counts[task.status] += 1
            if task.cycle_time:
                cycle_times.append(task.cycle_time)
            if task.lead_time:
                lead_times.append(task.lead_time)

        return {
            "total_tasks": total_tasks,
            "pending_tasks": status_counts[TaskStatus.PENDING],
            "in_progress_tasks": status_counts[TaskStatus.IN_PROGRESS],
            "completed_tasks": status_counts[TaskStatus.COMPLETED],
            "cancelled_tasks": status_counts[TaskStatus.CANCELLED],
            "avg_cycle_time": (
                statistics.mean(cycle_times) if cycle_times else 0.0
            ),
            "avg_lead_time": (
                statistics.mean(lead_times) if lead_times else 0.0
            ),
            "window_size": self.window_size,
            "window_utilization": total_tasks / self.window_size if self.window_size > 0 else 0.0,
        }

    def reset(self) -> None:
        """Reset all tracking data and baselines."""
        self._tasks.clear()
        self._task_queue.clear()
        self._baseline_throughput = None
        self._baseline_cycle_time = None
        self._baseline_samples = 0
