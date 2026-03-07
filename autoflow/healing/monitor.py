"""Health monitoring system for workflow-level metrics.

This module provides comprehensive health monitoring for workflows, tracking metrics
such as task failure rates, execution time, resource usage, and error patterns.
It follows the severity-based categorization pattern from the rollback/recovery system.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autoflow.healing.config import HealingConfig


class WorkflowHealthStatus(Enum):
    """Health status levels for workflow monitoring."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass
class MetricReading:
    """A single metric reading with timestamp.

    Attributes:
        value: The metric value.
        timestamp: When the reading was taken.
        metadata: Optional additional context about the reading.
    """

    value: float
    timestamp: datetime
    metadata: dict | None = None


@dataclass
class HealthAssessment:
    """Complete health assessment for a workflow.

    Attributes:
        status: Overall health status.
        timestamp: When the assessment was made.
        metrics: Dictionary of metric names to their current readings.
        violations: List of threshold violations detected.
        recommendations: List of recommended actions.
    """

    status: WorkflowHealthStatus
    timestamp: datetime
    metrics: dict[str, MetricReading]
    violations: list[dict]
    recommendations: list[str]


@dataclass
class TaskExecution:
    """Record of a task execution for metrics tracking.

    Attributes:
        task_id: Identifier for the task.
        success: Whether the task completed successfully.
        duration: Execution time in seconds.
        timestamp: When the task executed.
        error_message: Error message if the task failed.
    """

    task_id: str
    success: bool
    duration: float
    timestamp: datetime
    error_message: str | None = None


class WorkflowHealthMonitor:
    """Monitor workflow health with comprehensive metrics tracking.

    This monitor tracks workflow-level health metrics including task failure rates,
    execution time trends, resource usage patterns, and error frequencies. It maintains
    rolling windows of historical data for trend analysis and degradation detection.

    The monitor uses severity-based thresholds to categorize health issues and
    provides actionable recommendations for healing interventions.

    Example:
        monitor = WorkflowHealthMonitor(config=healing_config)
        monitor.record_task_execution(
            task_id="build-123",
            success=True,
            duration=45.2
        )
        assessment = monitor.assess_health()
        if assessment.status != WorkflowHealthStatus.HEALTHY:
            # Trigger healing workflow
            pass
    """

    def __init__(
        self,
        config: "HealingConfig | None" = None,
        window_size: int = 100,
    ) -> None:
        """Initialize the workflow health monitor.

        Args:
            config: Healing configuration with thresholds. If None, uses defaults.
            window_size: Maximum number of executions to keep in rolling window.
        """
        from autoflow.healing.config import HealingConfig

        self.config = config or HealingConfig()
        self.window_size = window_size

        # Rolling windows for metrics
        self._task_executions: deque[TaskExecution] = deque(maxlen=window_size)
        self._metric_history: dict[str, deque[MetricReading]] = {}

        # Baseline metrics for comparison
        self._baseline_duration: float | None = None
        self._baseline_samples: int = 0

    def record_task_execution(
        self,
        task_id: str,
        success: bool,
        duration: float,
        timestamp: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        """Record a task execution for metrics tracking.

        Args:
            task_id: Identifier for the task.
            success: Whether the task completed successfully.
            duration: Execution time in seconds.
            timestamp: When the task executed. Defaults to now.
            error_message: Error message if the task failed.
        """
        if timestamp is None:
            timestamp = datetime.now()

        execution = TaskExecution(
            task_id=task_id,
            success=success,
            duration=duration,
            timestamp=timestamp,
            error_message=error_message,
        )

        self._task_executions.append(execution)

        # Update baseline if this is a successful execution
        if success and self._baseline_samples < 10:
            if self._baseline_duration is None:
                self._baseline_duration = duration
            else:
                # Moving average for baseline
                self._baseline_duration = (
                    self._baseline_duration * 0.9 + duration * 0.1
                )
            self._baseline_samples += 1

    def get_task_failure_rate(
        self, window: int | None = None
    ) -> float:
        """Calculate the task failure rate over a window.

        Args:
            window: Number of recent executions to consider.
                    None uses all available data.

        Returns:
            Failure rate as a fraction (0.0 to 1.0).
        """
        if not self._task_executions:
            return 0.0

        executions = list(self._task_executions)
        if window is not None and window < len(executions):
            executions = executions[-window:]

        failed = sum(1 for e in executions if not e.success)
        return failed / len(executions)

    def get_average_execution_time(
        self, window: int | None = None
    ) -> float:
        """Calculate average execution time over a window.

        Args:
            window: Number of recent executions to consider.
                    None uses all available data.

        Returns:
            Average execution time in seconds.
        """
        if not self._task_executions:
            return 0.0

        executions = list(self._task_executions)
        if window is not None and window < len(executions):
            executions = executions[-window:]

        successful = [e.duration for e in executions if e.success]
        if not successful:
            return 0.0

        return sum(successful) / len(successful)

    def get_execution_time_ratio(self) -> float:
        """Get current execution time relative to baseline.

        Returns:
            Ratio of current avg time to baseline (1.0 = baseline,
            >1.0 = slower, <1.0 = faster).
        """
        if self._baseline_duration is None or self._baseline_duration == 0:
            return 1.0

        current_avg = self.get_average_execution_time()
        if current_avg == 0:
            return 1.0

        return current_avg / self._baseline_duration

    def get_error_patterns(self) -> dict[str, int]:
        """Analyze error patterns from failed executions.

        Returns:
            Dictionary mapping error messages to occurrence counts.
        """
        patterns: dict[str, int] = {}

        for execution in self._task_executions:
            if not execution.success and execution.error_message:
                # Simplify error messages for pattern matching
                error_key = self._normalize_error_message(execution.error_message)
                patterns[error_key] = patterns.get(error_key, 0) + 1

        return patterns

    def _normalize_error_message(self, error: str) -> str:
        """Normalize error message for pattern matching.

        Args:
            error: Raw error message.

        Returns:
            Normalized error key.
        """
        # Remove file paths, line numbers, and specific values
        normalized = error
        normalized = normalized.split(":")[0]  # Get first part
        normalized = normalized.strip()
        return normalized or "unknown_error"

    def check_thresholds(self) -> list[dict]:
        """Check all configured thresholds for violations.

        Returns:
            List of violation dictionaries with keys:
                - metric_type: Type of metric that violated.
                - severity: Severity level (warning or critical).
                - current_value: Current metric value.
                - threshold_value: Threshold that was exceeded.
        """
        violations = []

        # Check task failure rate
        failure_rate = self.get_task_failure_rate()
        failure_threshold = self.config.get_threshold(
            HealingThresholdType.TASK_FAILURE_RATE
        )
        if failure_threshold:
            if failure_threshold.is_critical(failure_rate):
                violations.append({
                    "metric_type": HealingThresholdType.TASK_FAILURE_RATE,
                    "severity": "critical",
                    "current_value": failure_rate,
                    "threshold_value": failure_threshold.critical_threshold,
                })
            elif failure_threshold.is_warning(failure_rate):
                violations.append({
                    "metric_type": HealingThresholdType.TASK_FAILURE_RATE,
                    "severity": "warning",
                    "current_value": failure_rate,
                    "threshold_value": failure_threshold.warning_threshold,
                })

        # Check execution time
        time_ratio = self.get_execution_time_ratio()
        time_threshold = self.config.get_threshold(
            HealingThresholdType.EXECUTION_TIME
        )
        if time_threshold:
            if time_threshold.is_critical(time_ratio):
                violations.append({
                    "metric_type": HealingThresholdType.EXECUTION_TIME,
                    "severity": "critical",
                    "current_value": time_ratio,
                    "threshold_value": time_threshold.critical_threshold,
                })
            elif time_threshold.is_warning(time_ratio):
                violations.append({
                    "metric_type": HealingThresholdType.EXECUTION_TIME,
                    "severity": "warning",
                    "current_value": time_ratio,
                    "threshold_value": time_threshold.warning_threshold,
                })

        return violations

    def generate_recommendations(
        self, violations: list[dict]
    ) -> list[str]:
        """Generate healing recommendations based on violations.

        Args:
            violations: List of threshold violations.

        Returns:
            List of recommended actions.
        """
        recommendations = []

        for violation in violations:
            metric_type = violation["metric_type"]
            severity = violation["severity"]

            if metric_type == HealingThresholdType.TASK_FAILURE_RATE:
                if severity == "critical":
                    recommendations.append(
                        "Critical task failure rate detected. "
                        "Investigate recent changes and consider rollback."
                    )
                else:
                    recommendations.append(
                        "Elevated task failure rate. "
                        "Review error patterns and task configurations."
                    )

            elif metric_type == HealingThresholdType.EXECUTION_TIME:
                if severity == "critical":
                    recommendations.append(
                        "Severe execution time degradation. "
                        "Check for resource contention or inefficient code paths."
                    )
                else:
                    recommendations.append(
                        "Execution time increased. "
                        "Review recent changes for performance impact."
                    )

        # Check for recurring error patterns
        error_patterns = self.get_error_patterns()
        if error_patterns:
            top_error = max(error_patterns.items(), key=lambda x: x[1])
            recommendations.append(
                f"Most common error: '{top_error[0]}' "
                f"(occurred {top_error[1]} times)"
            )

        return recommendations

    def assess_health(self) -> HealthAssessment:
        """Perform comprehensive health assessment.

        Returns:
            HealthAssessment with current status, metrics, violations,
            and recommendations.
        """
        violations = self.check_thresholds()
        recommendations = self.generate_recommendations(violations)

        # Determine overall status
        has_critical = any(v["severity"] == "critical" for v in violations)
        has_warning = any(v["severity"] == "warning" for v in violations)

        if has_critical:
            status = WorkflowHealthStatus.CRITICAL
        elif has_warning:
            status = WorkflowHealthStatus.DEGRADED
        else:
            status = WorkflowHealthStatus.HEALTHY

        # Collect current metrics
        metrics = {
            "task_failure_rate": MetricReading(
                value=self.get_task_failure_rate(),
                timestamp=datetime.now(),
            ),
            "execution_time_ratio": MetricReading(
                value=self.get_execution_time_ratio(),
                timestamp=datetime.now(),
            ),
            "avg_execution_time": MetricReading(
                value=self.get_average_execution_time(),
                timestamp=datetime.now(),
            ),
        }

        return HealthAssessment(
            status=status,
            timestamp=datetime.now(),
            metrics=metrics,
            violations=violations,
            recommendations=recommendations,
        )

    def is_degraded(self) -> bool:
        """Quick check if workflow is degraded or critical.

        Returns:
            True if health status is DEGRADED or CRITICAL.
        """
        assessment = self.assess_health()
        return assessment.status != WorkflowHealthStatus.HEALTHY

    def get_statistics(self) -> dict:
        """Get current monitoring statistics.

        Returns:
            Dictionary with statistics about the monitored data.
        """
        executions = list(self._task_executions)

        if not executions:
            return {
                "total_executions": 0,
                "successful_executions": 0,
                "failed_executions": 0,
                "failure_rate": 0.0,
                "avg_duration": 0.0,
                "window_size": self.window_size,
                "window_utilization": 0.0,
            }

        successful = [e for e in executions if e.success]
        failed = [e for e in executions if not e.success]

        return {
            "total_executions": len(executions),
            "successful_executions": len(successful),
            "failed_executions": len(failed),
            "failure_rate": len(failed) / len(executions) if executions else 0.0,
            "avg_duration": (
                sum(e.duration for e in successful) / len(successful)
                if successful
                else 0.0
            ),
            "window_size": self.window_size,
            "window_utilization": len(executions) / self.window_size,
        }

    def reset(self) -> None:
        """Reset all monitoring data and baselines."""
        self._task_executions.clear()
        self._metric_history.clear()
        self._baseline_duration = None
        self._baseline_samples = 0


# Import for type checking
from autoflow.healing.config import HealthMetricType as HealingThresholdType
