"""Health monitoring system for workflow-level metrics.

This module provides comprehensive health monitoring for workflows, tracking metrics
such as task failure rates, execution time, resource usage, and error patterns.
It follows the severity-based categorization pattern from the rollback/recovery system.
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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


@dataclass
class DegradationSignal:
    """A signal indicating potential workflow degradation.

    Attributes:
        signal_type: Type of degradation detected.
        severity: Severity level (info, warning, critical).
        metric_name: Name of the metric showing degradation.
        current_value: Current metric value.
        baseline_value: Expected/baseline value.
        degradation_rate: Rate of degradation (e.g., -0.15 for 15% decline).
        confidence: Confidence score (0.0 to 1.0).
        description: Human-readable description.
    """

    signal_type: str
    severity: str
    metric_name: str
    current_value: float
    baseline_value: float
    degradation_rate: float
    confidence: float
    description: str


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
        config: HealingConfig | None = None,
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
            violations: List of threshold violations and degradation signals.

        Returns:
            List of recommended actions.
        """
        recommendations = []

        for violation in violations:
            metric_type = violation.get("metric_type", violation.get("metric_name", ""))
            severity = violation.get("severity", "info")

            # Handle degradation signals
            if "description" in violation and "degradation_rate" in violation:
                # This is a degradation signal
                recommendations.append(f"Degradation detected: {violation['description']}")
                continue

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

            elif metric_type == HealingThresholdType.EXECUTION_TIME or metric_type == "execution_time":
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

            elif metric_type == "execution_time_volatility":
                recommendations.append(
                    "Execution time volatility increased. "
                    "Check for resource contention or intermittent failures."
                )

        # Check for recurring error patterns
        error_patterns = self.get_error_patterns()
        if error_patterns:
            top_error = max(error_patterns.items(), key=lambda x: x[1])
            recommendations.append(
                f"Most common error: '{top_error[0]}' "
                f"(occurred {top_error[1]} times)"
            )

        # Add proactive recommendation if degradation detected but no critical violations
        degradation_summary = self.get_degradation_summary()
        if degradation_summary["degradation_detected"] and degradation_summary["critical_signals"] == 0:
            recommendations.append(
                "Early degradation detected. Consider proactive investigation "
                "before performance further degrades."
            )

        return recommendations

    def assess_health(self) -> HealthAssessment:
        """Perform comprehensive health assessment.

        Returns:
            HealthAssessment with current status, metrics, violations,
            and recommendations.
        """
        violations = self.check_thresholds()
        degradation_signals = self.detect_degradation()

        # Combine violations and degradation signals for recommendations
        all_issues = violations.copy()
        for signal in degradation_signals:
            all_issues.append({
                "metric_type": signal.metric_name,
                "severity": signal.severity,
                "current_value": signal.current_value,
                "threshold_value": signal.baseline_value,
                "degradation_rate": signal.degradation_rate,
                "description": signal.description,
            })

        recommendations = self.generate_recommendations(all_issues)

        # Determine overall status (degradation can lower status even without threshold violations)
        has_critical = any(
            v.get("severity") == "critical" or
            (isinstance(v, dict) and v.get("severity") == "critical")
            for v in all_issues
        )
        has_warning = any(
            v.get("severity") == "warning" or
            (isinstance(v, dict) and v.get("severity") == "warning")
            for v in all_issues
        )

        if has_critical:
            status = WorkflowHealthStatus.CRITICAL
        elif has_warning or any(s.severity in ["warning", "info"] for s in degradation_signals):
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

    def detect_degradation(self) -> list[DegradationSignal]:
        """Detect workflow degradation using multiple algorithms.

        Analyzes trends, anomalies, and patterns to identify degradation before
        it reaches critical levels. Uses statistical methods to detect:
        - Gradual performance decline
        - Sudden metric changes
        - Baseline drift
        - Multi-metric correlation issues

        Returns:
            List of degradation signals ordered by severity.
        """
        signals = []

        # Detect execution time degradation
        time_signal = self._detect_execution_time_degradation()
        if time_signal:
            signals.append(time_signal)

        # Detect failure rate trends
        failure_signal = self._detect_failure_rate_trend()
        if failure_signal:
            signals.append(failure_signal)

        # Detect baseline drift
        drift_signal = self._detect_baseline_drift()
        if drift_signal:
            signals.append(drift_signal)

        # Detect volatility increase
        volatility_signal = self._detect_volatility_increase()
        if volatility_signal:
            signals.append(volatility_signal)

        # Sort by severity (critical > warning > info)
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        signals.sort(key=lambda s: severity_order.get(s.severity, 3))

        return signals

    def _detect_execution_time_degradation(self) -> DegradationSignal | None:
        """Detect degradation in execution time using trend analysis.

        Returns:
            DegradationSignal if degradation detected, None otherwise.
        """
        if len(self._task_executions) < 5:
            return None

        # Get recent successful execution times
        recent_times = [
            e.duration
            for e in list(self._task_executions)[-20:]
            if e.success
        ]

        if len(recent_times) < 5:
            return None

        # Calculate trend using linear regression
        n = len(recent_times)
        x = list(range(n))
        y = recent_times

        # Simple linear regression: y = mx + b
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        if n * sum_x2 - sum_x * sum_x == 0:
            return None

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

        # Calculate current average vs baseline
        current_avg = statistics.mean(recent_times[-5:])
        baseline_avg = statistics.mean(recent_times[:5])

        if baseline_avg == 0:
            return None

        degradation_rate = (current_avg - baseline_avg) / baseline_avg

        # Determine severity based on trend and degradation
        severity = "info"
        confidence = min(abs(degradation_rate) * 2, 1.0)

        if degradation_rate > 0.5:  # 50% slower
            severity = "critical"
        elif degradation_rate > 0.25:  # 25% slower
            severity = "warning"
        elif degradation_rate > 0.1:  # 10% slower
            severity = "info"

        # Only return signal if there's meaningful degradation
        if degradation_rate > 0.1 and slope > 0:
            return DegradationSignal(
                signal_type="execution_time_trend",
                severity=severity,
                metric_name="execution_time",
                current_value=current_avg,
                baseline_value=baseline_avg,
                degradation_rate=degradation_rate,
                confidence=confidence,
                description=(
                    f"Execution time degrading at {slope:.2f}s per execution. "
                    f"Currently {degradation_rate * 100:.1f}% slower than baseline."
                ),
            )

        return None

    def _detect_failure_rate_trend(self) -> DegradationSignal | None:
        """Detect increasing failure rate trends.

        Returns:
            DegradationSignal if degradation detected, None otherwise.
        """
        if len(self._task_executions) < 10:
            return None

        # Calculate failure rate in sliding windows
        executions = list(self._task_executions)
        window_size = 5
        failure_rates = []

        for i in range(len(executions) - window_size + 1):
            window = executions[i : i + window_size]
            failures = sum(1 for e in window if not e.success)
            failure_rates.append(failures / window_size)

        if len(failure_rates) < 3:
            return None

        # Compare recent to older
        recent_rate = statistics.mean(failure_rates[-3:])
        older_rate = statistics.mean(failure_rates[:3])

        if older_rate == 0:
            # If baseline is 0, check for any failures
            if recent_rate > 0:
                degradation_rate = recent_rate
            else:
                return None
        else:
            degradation_rate = (recent_rate - older_rate) / older_rate

        # Determine severity
        severity = "info"
        if recent_rate > 0.3:  # 30% failure rate
            severity = "critical"
        elif recent_rate > 0.15:  # 15% failure rate
            severity = "warning"
        elif recent_rate > 0.05 and degradation_rate > 0.5:  # 5% with increasing trend
            severity = "info"

        confidence = min(recent_rate * 3, 1.0)

        # Only return if there's meaningful degradation
        if degradation_rate > 0.3 and recent_rate > 0.05:
            return DegradationSignal(
                signal_type="failure_rate_trend",
                severity=severity,
                metric_name="failure_rate",
                current_value=recent_rate,
                baseline_value=older_rate,
                degradation_rate=degradation_rate,
                confidence=confidence,
                description=(
                    f"Failure rate increased by {degradation_rate * 100:.1f}%. "
                    f"Current rate: {recent_rate * 100:.1f}%"
                ),
            )

        return None

    def _detect_baseline_drift(self) -> DegradationSignal | None:
        """Detect when current baseline drifts from initial baseline.

        Returns:
            DegradationSignal if drift detected, None otherwise.
        """
        if self._baseline_duration is None or len(self._task_executions) < 10:
            return None

        # Get recent successful executions
        recent_times = [
            e.duration
            for e in list(self._task_executions)[-10:]
            if e.success
        ]

        if len(recent_times) < 5:
            return None

        current_avg = statistics.mean(recent_times)
        drift_ratio = current_avg / self._baseline_duration

        # Detect significant drift (>20%)
        if drift_ratio > 1.2:
            severity = "warning" if drift_ratio < 1.5 else "critical"
            confidence = min((drift_ratio - 1.0) * 2, 1.0)

            return DegradationSignal(
                signal_type="baseline_drift",
                severity=severity,
                metric_name="execution_time",
                current_value=current_avg,
                baseline_value=self._baseline_duration,
                degradation_rate=drift_ratio - 1.0,
                confidence=confidence,
                description=(
                    f"Baseline drifted {drift_ratio * 100:.1f}% from initial. "
                    f"Current: {current_avg:.2f}s, Initial: {self._baseline_duration:.2f}s"
                ),
            )

        return None

    def _detect_volatility_increase(self) -> DegradationSignal | None:
        """Detect increased volatility in execution times.

        High volatility can indicate unstable performance or resource contention.

        Returns:
            DegradationSignal if volatility increase detected, None otherwise.
        """
        if len(self._task_executions) < 15:
            return None

        executions = list(self._task_executions)
        # Split into two halves
        mid = len(executions) // 2

        older_times = [
            e.duration for e in executions[:mid] if e.success
        ]
        recent_times = [
            e.duration for e in executions[mid:] if e.success
        ]

        if len(older_times) < 3 or len(recent_times) < 3:
            return None

        # Calculate coefficient of variation (CV = std/mean)
        if statistics.mean(older_times) == 0 or statistics.mean(recent_times) == 0:
            return None

        older_cv = (
            statistics.stdev(older_times) / statistics.mean(older_times)
            if len(older_times) > 1
            else 0
        )
        recent_cv = (
            statistics.stdev(recent_times) / statistics.mean(recent_times)
            if len(recent_times) > 1
            else 0
        )

        # Detect significant volatility increase
        if recent_cv > older_cv * 1.5 and recent_cv > 0.2:
            severity = "warning" if recent_cv < 0.4 else "critical"
            confidence = min((recent_cv - older_cv) * 2, 1.0)

            return DegradationSignal(
                signal_type="volatility_increase",
                severity=severity,
                metric_name="execution_time_volatility",
                current_value=recent_cv,
                baseline_value=older_cv,
                degradation_rate=(recent_cv - older_cv) / older_cv if older_cv > 0 else 1.0,
                confidence=confidence,
                description=(
                    f"Execution time volatility increased. "
                    f"Recent CV: {recent_cv:.2f}, Historical CV: {older_cv:.2f}"
                ),
            )

        return None

    def get_degradation_summary(self) -> dict:
        """Get summary of degradation analysis.

        Returns:
            Dictionary with degradation metrics and signals.
        """
        signals = self.detect_degradation()

        return {
            "degradation_detected": len(signals) > 0,
            "signal_count": len(signals),
            "critical_signals": sum(1 for s in signals if s.severity == "critical"),
            "warning_signals": sum(1 for s in signals if s.severity == "warning"),
            "info_signals": sum(1 for s in signals if s.severity == "info"),
            "signals": [
                {
                    "type": s.signal_type,
                    "severity": s.severity,
                    "metric": s.metric_name,
                    "description": s.description,
                    "confidence": s.confidence,
                }
                for s in signals
            ],
        }

    def reset(self) -> None:
        """Reset all monitoring data and baselines."""
        self._task_executions.clear()
        self._metric_history.clear()
        self._baseline_duration = None
        self._baseline_samples = 0


# Import for type checking
from autoflow.healing.config import HealthMetricType as HealingThresholdType
