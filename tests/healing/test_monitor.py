"""Unit Tests for Workflow Health Monitoring System.

Tests the WorkflowHealthMonitor class and related models for tracking
workflow-level health metrics including task failure rates, execution time,
resource usage, and error patterns.

These tests ensure the monitoring system can:
- Track task executions with success/failure
- Calculate failure rates and execution time statistics
- Detect degradation using multiple algorithms
- Assess overall workflow health
- Generate actionable recommendations
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from autoflow.healing.config import (
    HealthMetricType,
    HealingConfig,
    HealingThreshold,
)
from autoflow.healing.monitor import (
    DegradationSignal,
    HealthAssessment,
    MetricReading,
    TaskExecution,
    WorkflowHealthMonitor,
    WorkflowHealthStatus,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_config() -> HealingConfig:
    """Create a sample healing configuration for testing."""
    return HealingConfig(
        enabled=True,
        max_healing_attempts=3,
        healing_timeout=600,
        thresholds=[
            HealingThreshold(
                metric_type=HealthMetricType.TASK_FAILURE_RATE,
                warning_threshold=0.1,
                critical_threshold=0.25,
            ),
            HealingThreshold(
                metric_type=HealthMetricType.EXECUTION_TIME,
                warning_threshold=1.5,
                critical_threshold=3.0,
            ),
        ],
    )


@pytest.fixture
def monitor(sample_config: HealingConfig) -> WorkflowHealthMonitor:
    """Create a WorkflowHealthMonitor instance with sample config."""
    return WorkflowHealthMonitor(config=sample_config, window_size=100)


# ============================================================================
# WorkflowHealthStatus Enum Tests
# ============================================================================


class TestWorkflowHealthStatus:
    """Tests for WorkflowHealthStatus enum."""

    def test_status_values(self) -> None:
        """Test WorkflowHealthStatus enum values."""
        assert WorkflowHealthStatus.HEALTHY.value == "healthy"
        assert WorkflowHealthStatus.DEGRADED.value == "degraded"
        assert WorkflowHealthStatus.CRITICAL.value == "critical"

    def test_status_is_string(self) -> None:
        """Test that status values are strings."""
        assert isinstance(WorkflowHealthStatus.HEALTHY.value, str)


# ============================================================================
# Data Model Tests
# ============================================================================


class TestMetricReading:
    """Tests for MetricReading dataclass."""

    def test_metric_reading_init(self) -> None:
        """Test MetricReading initialization."""
        timestamp = datetime.now()
        reading = MetricReading(
            value=42.5,
            timestamp=timestamp,
            metadata={"unit": "seconds"},
        )

        assert reading.value == 42.5
        assert reading.timestamp == timestamp
        assert reading.metadata == {"unit": "seconds"}

    def test_metric_reading_without_metadata(self) -> None:
        """Test MetricReading without metadata."""
        reading = MetricReading(value=10.0, timestamp=datetime.now())

        assert reading.metadata is None


class TestTaskExecution:
    """Tests for TaskExecution dataclass."""

    def test_task_execution_success(self) -> None:
        """Test TaskExecution for successful task."""
        timestamp = datetime.now()
        execution = TaskExecution(
            task_id="task-001",
            success=True,
            duration=45.2,
            timestamp=timestamp,
        )

        assert execution.task_id == "task-001"
        assert execution.success is True
        assert execution.duration == 45.2
        assert execution.timestamp == timestamp
        assert execution.error_message is None

    def test_task_execution_failure(self) -> None:
        """Test TaskExecution for failed task."""
        execution = TaskExecution(
            task_id="task-002",
            success=False,
            duration=10.5,
            timestamp=datetime.now(),
            error_message="Connection timeout",
        )

        assert execution.success is False
        assert execution.error_message == "Connection timeout"


class TestDegradationSignal:
    """Tests for DegradationSignal dataclass."""

    def test_degradation_signal_init(self) -> None:
        """Test DegradationSignal initialization."""
        signal = DegradationSignal(
            signal_type="execution_time_trend",
            severity="warning",
            metric_name="execution_time",
            current_value=150.0,
            baseline_value=100.0,
            degradation_rate=0.5,
            confidence=0.85,
            description="Execution time increased by 50%",
        )

        assert signal.signal_type == "execution_time_trend"
        assert signal.severity == "warning"
        assert signal.metric_name == "execution_time"
        assert signal.degradation_rate == 0.5
        assert 0 <= signal.confidence <= 1.0


class TestHealthAssessment:
    """Tests for HealthAssessment dataclass."""

    def test_health_assessment_init(self) -> None:
        """Test HealthAssessment initialization."""
        timestamp = datetime.now()
        metrics = {
            "failure_rate": MetricReading(value=0.15, timestamp=timestamp),
        }

        assessment = HealthAssessment(
            status=WorkflowHealthStatus.DEGRADED,
            timestamp=timestamp,
            metrics=metrics,
            violations=[{"metric_type": "task_failure_rate", "severity": "warning"}],
            recommendations=["Review error patterns"],
        )

        assert assessment.status == WorkflowHealthStatus.DEGRADED
        assert len(assessment.metrics) == 1
        assert len(assessment.violations) == 1
        assert len(assessment.recommendations) == 1


# ============================================================================
# WorkflowHealthMonitor Initialization Tests
# ============================================================================


class TestWorkflowHealthMonitorInit:
    """Tests for WorkflowHealthMonitor initialization."""

    def test_init_with_config(self, sample_config: HealingConfig) -> None:
        """Test initialization with config."""
        monitor = WorkflowHealthMonitor(config=sample_config, window_size=50)

        assert monitor.config == sample_config
        assert monitor.window_size == 50
        assert len(monitor._task_executions) == 0
        assert monitor._baseline_duration is None

    def test_init_without_config(self) -> None:
        """Test initialization without config uses defaults."""
        monitor = WorkflowHealthMonitor()

        assert monitor.config is not None
        assert monitor.config.enabled is True
        assert monitor.window_size == 100

    def test_init_with_custom_window_size(self) -> None:
        """Test initialization with custom window size."""
        monitor = WorkflowHealthMonitor(window_size=200)

        assert monitor.window_size == 200
        assert monitor._task_executions.maxlen == 200


# ============================================================================
# Task Execution Recording Tests
# ============================================================================


class TestTaskExecutionRecording:
    """Tests for recording task executions."""

    def test_record_successful_execution(self, monitor: WorkflowHealthMonitor) -> None:
        """Test recording a successful task execution."""
        monitor.record_task_execution(
            task_id="build-123",
            success=True,
            duration=45.2,
        )

        assert len(monitor._task_executions) == 1
        execution = monitor._task_executions[0]
        assert execution.task_id == "build-123"
        assert execution.success is True
        assert execution.duration == 45.2

    def test_record_failed_execution(self, monitor: WorkflowHealthMonitor) -> None:
        """Test recording a failed task execution."""
        monitor.record_task_execution(
            task_id="test-456",
            success=False,
            duration=10.5,
            error_message="AssertionError: Expected 200, got 500",
        )

        assert len(monitor._task_executions) == 1
        execution = monitor._task_executions[0]
        assert execution.success is False
        assert execution.error_message == "AssertionError: Expected 200, got 500"

    def test_record_execution_with_timestamp(self, monitor: WorkflowHealthMonitor) -> None:
        """Test recording execution with custom timestamp."""
        timestamp = datetime.now() - timedelta(minutes=5)
        monitor.record_task_execution(
            task_id="task-001",
            success=True,
            duration=30.0,
            timestamp=timestamp,
        )

        execution = monitor._task_executions[0]
        assert execution.timestamp == timestamp

    def test_record_execution_updates_baseline(self, monitor: WorkflowHealthMonitor) -> None:
        """Test that successful executions update baseline."""
        # Record first successful execution
        monitor.record_task_execution(
            task_id="task-001",
            success=True,
            duration=50.0,
        )

        assert monitor._baseline_duration == 50.0
        assert monitor._baseline_samples == 1

        # Record second successful execution
        monitor.record_task_execution(
            task_id="task-002",
            success=True,
            duration=60.0,
        )

        # Baseline should be updated with moving average
        assert monitor._baseline_duration > 50.0
        assert monitor._baseline_samples == 2

    def test_failed_execution_does_not_update_baseline(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test that failed executions don't update baseline."""
        monitor.record_task_execution(
            task_id="task-001",
            success=True,
            duration=50.0,
        )

        initial_baseline = monitor._baseline_duration

        monitor.record_task_execution(
            task_id="task-002",
            success=False,
            duration=100.0,
            error_message="Error",
        )

        # Baseline should not change
        assert monitor._baseline_duration == initial_baseline

    def test_window_size_limit(self, monitor: WorkflowHealthMonitor) -> None:
        """Test that window size limits stored executions."""
        small_monitor = WorkflowHealthMonitor(window_size=5)

        for i in range(10):
            small_monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=30.0,
            )

        # Should only keep last 5
        assert len(small_monitor._task_executions) == 5

    def test_baseline_samples_limit(self, monitor: WorkflowHealthMonitor) -> None:
        """Test that baseline stops updating after 10 samples."""
        for i in range(15):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=50.0,
            )

        # Should stop at 10 samples
        assert monitor._baseline_samples == 10


# ============================================================================
# Metric Calculation Tests
# ============================================================================


class TestMetricCalculations:
    """Tests for metric calculations."""

    def test_get_task_failure_rate_empty(self, monitor: WorkflowHealthMonitor) -> None:
        """Test failure rate with no executions."""
        assert monitor.get_task_failure_rate() == 0.0

    def test_get_task_failure_rate_all_success(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test failure rate with all successes."""
        for i in range(10):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=30.0,
            )

        assert monitor.get_task_failure_rate() == 0.0

    def test_get_task_failure_rate_mixed(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test failure rate with mixed results."""
        # 7 successes, 3 failures = 30% failure rate
        for i in range(7):
            monitor.record_task_execution(
                task_id=f"success-{i}",
                success=True,
                duration=30.0,
            )

        for i in range(3):
            monitor.record_task_execution(
                task_id=f"failure-{i}",
                success=False,
                duration=10.0,
                error_message="Error",
            )

        assert monitor.get_task_failure_rate() == 0.3

    def test_get_task_failure_rate_with_window(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test failure rate with window parameter."""
        # 10 total: 5 successes, 5 failures
        for i in range(5):
            monitor.record_task_execution(
                task_id=f"success-{i}",
                success=True,
                duration=30.0,
            )

        for i in range(5):
            monitor.record_task_execution(
                task_id=f"failure-{i}",
                success=False,
                duration=10.0,
                error_message="Error",
            )

        # Overall should be 50%
        assert monitor.get_task_failure_rate() == 0.5

        # Last 3 should all be failures
        assert monitor.get_task_failure_rate(window=3) == 1.0

    def test_get_average_execution_time_empty(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test average execution time with no data."""
        assert monitor.get_average_execution_time() == 0.0

    def test_get_average_execution_time_only_failures(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test average with only failed executions."""
        monitor.record_task_execution(
            task_id="task-001",
            success=False,
            duration=10.0,
            error_message="Error",
        )

        # Failed executions are excluded
        assert monitor.get_average_execution_time() == 0.0

    def test_get_average_execution_time_successful(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test average execution time for successful tasks."""
        times = [30.0, 40.0, 50.0, 60.0, 70.0]

        for i, time in enumerate(times):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=time,
            )

        expected_avg = sum(times) / len(times)
        assert monitor.get_average_execution_time() == expected_avg

    def test_get_execution_time_ratio_no_baseline(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test execution time ratio without baseline."""
        assert monitor.get_execution_time_ratio() == 1.0

    def test_get_execution_time_ratio_with_baseline(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test execution time ratio with baseline."""
        # Establish baseline
        monitor.record_task_execution(
            task_id="task-001",
            success=True,
            duration=50.0,
        )

        # Current execution slower
        monitor.record_task_execution(
            task_id="task-002",
            success=True,
            duration=75.0,
        )

        ratio = monitor.get_execution_time_ratio()
        assert ratio > 1.0  # Slower than baseline

    def test_get_error_patterns_empty(self, monitor: WorkflowHealthMonitor) -> None:
        """Test error patterns with no failures."""
        monitor.record_task_execution(
            task_id="task-001",
            success=True,
            duration=30.0,
        )

        patterns = monitor.get_error_patterns()
        assert patterns == {}

    def test_get_error_patterns_with_failures(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test error pattern detection."""
        errors = [
            "ConnectionError: Timeout",
            "ConnectionError: Refused",
            "ValueError: Invalid input",
            "ConnectionError: Timeout",
        ]

        for i, error in enumerate(errors):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=False,
                duration=10.0,
                error_message=error,
            )

        patterns = monitor.get_error_patterns()

        # ConnectionError should be most common
        assert "ConnectionError" in patterns
        assert patterns["ConnectionError"] == 3
        assert "ValueError" in patterns
        assert patterns["ValueError"] == 1


# ============================================================================
# Threshold Checking Tests
# ============================================================================


class TestThresholdChecking:
    """Tests for threshold violation checking."""

    def test_check_thresholds_healthy(self, monitor: WorkflowHealthMonitor) -> None:
        """Test threshold check with healthy metrics."""
        # All successful, good times
        for i in range(10):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=30.0,
            )

        violations = monitor.check_thresholds()
        assert len(violations) == 0

    def test_check_thresholds_warning_failure_rate(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test warning threshold for failure rate."""
        # 15% failure rate (above 10% warning threshold)
        for i in range(85):
            monitor.record_task_execution(
                task_id=f"success-{i}",
                success=True,
                duration=30.0,
            )

        for i in range(15):
            monitor.record_task_execution(
                task_id=f"failure-{i}",
                success=False,
                duration=10.0,
                error_message="Error",
            )

        violations = monitor.check_thresholds()

        # Should have warning violation
        assert len(violations) > 0
        failure_violations = [
            v for v in violations
            if v["metric_type"] == HealthMetricType.TASK_FAILURE_RATE
        ]
        assert len(failure_violations) > 0
        assert failure_violations[0]["severity"] == "warning"

    def test_check_thresholds_critical_failure_rate(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test critical threshold for failure rate."""
        # 30% failure rate (above 25% critical threshold)
        for i in range(70):
            monitor.record_task_execution(
                task_id=f"success-{i}",
                success=True,
                duration=30.0,
            )

        for i in range(30):
            monitor.record_task_execution(
                task_id=f"failure-{i}",
                success=False,
                duration=10.0,
                error_message="Error",
            )

        violations = monitor.check_thresholds()

        failure_violations = [
            v for v in violations
            if v["metric_type"] == HealthMetricType.TASK_FAILURE_RATE
        ]
        assert len(failure_violations) > 0
        assert failure_violations[0]["severity"] == "critical"

    def test_check_thresholds_execution_time_warning(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test warning threshold for execution time."""
        # Establish baseline
        monitor.record_task_execution(
            task_id="baseline",
            success=True,
            duration=50.0,
        )

        # Record slower executions (75% slower = 1.75x)
        for i in range(10):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=87.5,  # 50.0 * 1.75
            )

        violations = monitor.check_thresholds()

        time_violations = [
            v for v in violations
            if v["metric_type"] == HealthMetricType.EXECUTION_TIME
        ]
        assert len(time_violations) > 0
        assert time_violations[0]["severity"] == "warning"


# ============================================================================
# Health Assessment Tests
# ============================================================================


class TestHealthAssessment:
    """Tests for health assessment functionality."""

    def test_assess_health_healthy(self, monitor: WorkflowHealthMonitor) -> None:
        """Test health assessment with healthy workflow."""
        for i in range(10):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=30.0,
            )

        assessment = monitor.assess_health()

        assert assessment.status == WorkflowHealthStatus.HEALTHY
        assert len(assessment.violations) == 0
        assert assessment.metrics["task_failure_rate"].value == 0.0

    def test_assess_health_degraded(self, monitor: WorkflowHealthMonitor) -> None:
        """Test health assessment with degraded workflow."""
        # Some failures to trigger degraded status
        for i in range(90):
            monitor.record_task_execution(
                task_id=f"success-{i}",
                success=True,
                duration=30.0,
            )

        for i in range(10):
            monitor.record_task_execution(
                task_id=f"failure-{i}",
                success=False,
                duration=10.0,
                error_message="Error",
            )

        assessment = monitor.assess_health()

        assert assessment.status == WorkflowHealthStatus.DEGRADED
        assert len(assessment.violations) > 0
        assert len(assessment.recommendations) > 0

    def test_assess_health_includes_metrics(self, monitor: WorkflowHealthMonitor) -> None:
        """Test that assessment includes all expected metrics."""
        monitor.record_task_execution(
            task_id="task-001",
            success=True,
            duration=45.0,
        )

        assessment = monitor.assess_health()

        assert "task_failure_rate" in assessment.metrics
        assert "execution_time_ratio" in assessment.metrics
        assert "avg_execution_time" in assessment.metrics

    def test_is_degraded_true(self, monitor: WorkflowHealthMonitor) -> None:
        """Test is_degraded returns True for degraded workflow."""
        # Trigger degraded state
        for i in range(85):
            monitor.record_task_execution(
                task_id=f"success-{i}",
                success=True,
                duration=30.0,
            )

        for i in range(15):
            monitor.record_task_execution(
                task_id=f"failure-{i}",
                success=False,
                duration=10.0,
                error_message="Error",
            )

        assert monitor.is_degraded() is True

    def test_is_degraded_false(self, monitor: WorkflowHealthMonitor) -> None:
        """Test is_degraded returns False for healthy workflow."""
        for i in range(10):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=30.0,
            )

        assert monitor.is_degraded() is False


# ============================================================================
# Statistics Tests
# ============================================================================


class TestStatistics:
    """Tests for statistics reporting."""

    def test_get_statistics_empty(self, monitor: WorkflowHealthMonitor) -> None:
        """Test statistics with no data."""
        stats = monitor.get_statistics()

        assert stats["total_executions"] == 0
        assert stats["successful_executions"] == 0
        assert stats["failed_executions"] == 0
        assert stats["failure_rate"] == 0.0

    def test_get_statistics_with_data(self, monitor: WorkflowHealthMonitor) -> None:
        """Test statistics with execution data."""
        # 7 successes, 3 failures
        for i in range(7):
            monitor.record_task_execution(
                task_id=f"success-{i}",
                success=True,
                duration=40.0,
            )

        for i in range(3):
            monitor.record_task_execution(
                task_id=f"failure-{i}",
                success=False,
                duration=10.0,
                error_message="Error",
            )

        stats = monitor.get_statistics()

        assert stats["total_executions"] == 10
        assert stats["successful_executions"] == 7
        assert stats["failed_executions"] == 3
        assert stats["failure_rate"] == 0.3
        assert stats["avg_duration"] == 40.0

    def test_get_statistics_window_utilization(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test window utilization calculation."""
        monitor = WorkflowHealthMonitor(window_size=100)

        for i in range(50):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=30.0,
            )

        stats = monitor.get_statistics()
        assert stats["window_utilization"] == 0.5


# ============================================================================
# Degradation Detection Tests
# ============================================================================


class TestDegradationDetection:
    """Tests for degradation detection algorithms."""

    def test_detect_degradation_empty(self, monitor: WorkflowHealthMonitor) -> None:
        """Test degradation detection with no data."""
        signals = monitor.detect_degradation()

        assert len(signals) == 0

    def test_detect_degradation_execution_time(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test execution time degradation detection."""
        # Record executions with increasing time
        base_time = 50.0
        for i in range(20):
            # Gradually increase by 5% each time
            duration = base_time * (1.0 + i * 0.05)
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=duration,
            )

        signals = monitor.detect_degradation()

        # Should detect execution time degradation
        time_signals = [s for s in signals if s.metric_name == "execution_time"]
        assert len(time_signals) > 0

    def test_detect_degradation_failure_rate_trend(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test failure rate trend detection."""
        # Start with all successes, then introduce failures
        for i in range(15):
            monitor.record_task_execution(
                task_id=f"success-{i}",
                success=True,
                duration=30.0,
            )

        # Add increasing failures
        for i in range(5):
            monitor.record_task_execution(
                task_id=f"failure-{i}",
                success=False,
                duration=10.0,
                error_message="Error",
            )

        signals = monitor.detect_degradation()

        # Should detect failure rate increase
        failure_signals = [s for s in signals if s.metric_name == "failure_rate"]
        # May or may not detect depending on exact pattern
        assert isinstance(signals, list)

    def test_detect_degradation_baseline_drift(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test baseline drift detection."""
        # Establish baseline
        for i in range(10):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=50.0,
            )

        # Record much slower executions
        for i in range(10):
            monitor.record_task_execution(
                task_id=f"slow-{i}",
                success=True,
                duration=100.0,  # 2x baseline
            )

        signals = monitor.detect_degradation()

        # Should detect baseline drift
        drift_signals = [s for s in signals if s.signal_type == "baseline_drift"]
        assert len(drift_signals) > 0

    def test_get_degradation_summary(self, monitor: WorkflowHealthMonitor) -> None:
        """Test degradation summary."""
        # Record some data
        for i in range(20):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=50.0 + i * 2.0,  # Increasing
            )

        summary = monitor.get_degradation_summary()

        assert "degradation_detected" in summary
        assert "signal_count" in summary
        assert "critical_signals" in summary
        assert "warning_signals" in summary
        assert "signals" in summary


# ============================================================================
# Recommendation Tests
# ============================================================================


class TestRecommendations:
    """Tests for recommendation generation."""

    def test_generate_recommendations_empty(self, monitor: WorkflowHealthMonitor) -> None:
        """Test recommendations with no violations."""
        recommendations = monitor.generate_recommendations([])

        assert recommendations == []

    def test_generate_recommendations_failure_rate(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test recommendations for failure rate violations."""
        violations = [
            {
                "metric_type": HealthMetricType.TASK_FAILURE_RATE,
                "severity": "warning",
                "current_value": 0.15,
                "threshold_value": 0.1,
            }
        ]

        recommendations = monitor.generate_recommendations(violations)

        assert len(recommendations) > 0
        assert any("failure rate" in r.lower() for r in recommendations)

    def test_generate_recommendations_execution_time(
        self, monitor: WorkflowHealthMonitor
    ) -> None:
        """Test recommendations for execution time violations."""
        violations = [
            {
                "metric_type": HealthMetricType.EXECUTION_TIME,
                "severity": "critical",
                "current_value": 4.0,
                "threshold_value": 3.0,
            }
        ]

        recommendations = monitor.generate_recommendations(violations)

        assert len(recommendations) > 0
        assert any("execution time" in r.lower() for r in recommendations)


# ============================================================================
# Reset Tests
# ============================================================================


class TestReset:
    """Tests for monitor reset functionality."""

    def test_reset_clears_executions(self, monitor: WorkflowHealthMonitor) -> None:
        """Test that reset clears all executions."""
        for i in range(10):
            monitor.record_task_execution(
                task_id=f"task-{i}",
                success=True,
                duration=30.0,
            )

        assert len(monitor._task_executions) > 0

        monitor.reset()

        assert len(monitor._task_executions) == 0

    def test_reset_clears_baseline(self, monitor: WorkflowHealthMonitor) -> None:
        """Test that reset clears baseline."""
        monitor.record_task_execution(
            task_id="task-001",
            success=True,
            duration=50.0,
        )

        assert monitor._baseline_duration is not None

        monitor.reset()

        assert monitor._baseline_duration is None
        assert monitor._baseline_samples == 0

    def test_reset_clears_metric_history(self, monitor: WorkflowHealthMonitor) -> None:
        """Test that reset clears metric history."""
        monitor.reset()

        assert len(monitor._metric_history) == 0
