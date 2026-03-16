"""Configuration models for self-healing workflows.

This module provides configuration classes that define thresholds, timeouts,
and behavioral parameters for the self-healing system.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class HealingStrategy(Enum):
    """Available healing strategies for different failure types."""

    RETRY = "retry"
    ROLLBACK = "rollback"
    RECONFIGURE = "reconfigure"
    ESCALATE = "escalate"


class HealthMetricType(Enum):
    """Types of health metrics monitored by the healing system."""

    TASK_FAILURE_RATE = "task_failure_rate"
    EXECUTION_TIME = "execution_time"
    RESOURCE_USAGE = "resource_usage"
    ERROR_PATTERN = "error_pattern"
    DEPENDENCY_HEALTH = "dependency_health"


@dataclass
class HealingThreshold:
    """Threshold configuration for triggering healing actions.

    Attributes:
        metric_type: Type of metric being monitored.
        warning_threshold: Value at which to log warnings.
        critical_threshold: Value at which to trigger healing.
        measurement_window: Time window in seconds for metric aggregation.
    """

    metric_type: HealthMetricType
    warning_threshold: float
    critical_threshold: float
    measurement_window: int = 300  # 5 minutes default

    def is_warning(self, value: float) -> bool:
        """Check if value exceeds warning threshold.

        Args:
            value: Metric value to check.

        Returns:
            True if value exceeds warning threshold.
        """
        return value >= self.warning_threshold

    def is_critical(self, value: float) -> bool:
        """Check if value exceeds critical threshold.

        Args:
            value: Metric value to check.

        Returns:
            True if value exceeds critical threshold.
        """
        return value >= self.critical_threshold


@dataclass
class HealingConfig:
    """Configuration for the self-healing workflow system.

    This configuration defines when and how the healing system should respond
    to workflow degradation, including thresholds, timeouts, and strategy selection.

    Attributes:
        enabled: Whether self-healing is enabled.
        max_healing_attempts: Maximum number of healing attempts before escalation.
        healing_timeout: Timeout in seconds for healing actions.
        rollback_on_failure: Whether to rollback on healing failure.
        log_healing_actions: Whether to log all healing actions for transparency.
        thresholds: List of threshold configurations for different metrics.
        project_root: Root directory of the project.
        learning_enabled: Whether recovery learning is enabled.
        min_learning_samples: Minimum samples before trusting learned strategies.
        learning_confidence_threshold: Minimum confidence for using learned strategies.
    """

    enabled: bool = True
    max_healing_attempts: int = 3
    healing_timeout: int = 600  # 10 minutes default
    rollback_on_failure: bool = True
    log_healing_actions: bool = True
    thresholds: list[HealingThreshold] | None = None
    project_root: Path | None = None
    learning_enabled: bool = True
    min_learning_samples: int = 5
    learning_confidence_threshold: float = 0.7

    def __post_init__(self) -> None:
        """Initialize default thresholds if not provided."""
        if self.thresholds is None:
            self.thresholds = self._default_thresholds()

        if self.project_root is None:
            self.project_root = Path.cwd()

    def _default_thresholds(self) -> list[HealingThreshold]:
        """Create default threshold configurations.

        Returns:
            List of default HealingThreshold objects.
        """
        return [
            HealingThreshold(
                metric_type=HealthMetricType.TASK_FAILURE_RATE,
                warning_threshold=0.1,  # 10% failure rate
                critical_threshold=0.25,  # 25% failure rate
                measurement_window=300,
            ),
            HealingThreshold(
                metric_type=HealthMetricType.EXECUTION_TIME,
                warning_threshold=1.5,  # 50% slower than baseline
                critical_threshold=3.0,  # 3x slower than baseline
                measurement_window=300,
            ),
            HealingThreshold(
                metric_type=HealthMetricType.RESOURCE_USAGE,
                warning_threshold=0.8,  # 80% resource usage
                critical_threshold=0.95,  # 95% resource usage
                measurement_window=300,
            ),
        ]

    def get_threshold(self, metric_type: HealthMetricType) -> HealingThreshold | None:
        """Get threshold configuration for a specific metric.

        Args:
            metric_type: Type of metric to get threshold for.

        Returns:
            HealingThreshold if found, None otherwise.
        """
        if self.thresholds is None:
            return None

        for threshold in self.thresholds:
            if threshold.metric_type == metric_type:
                return threshold

        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation of configuration.
        """
        return {
            "enabled": self.enabled,
            "max_healing_attempts": self.max_healing_attempts,
            "healing_timeout": self.healing_timeout,
            "rollback_on_failure": self.rollback_on_failure,
            "log_healing_actions": self.log_healing_actions,
            "thresholds": (
                [
                    {
                        "metric_type": t.metric_type.value,
                        "warning_threshold": t.warning_threshold,
                        "critical_threshold": t.critical_threshold,
                        "measurement_window": t.measurement_window,
                    }
                    for t in self.thresholds
                ]
                if self.thresholds
                else None
            ),
            "project_root": str(self.project_root) if self.project_root else None,
            "learning_enabled": self.learning_enabled,
            "min_learning_samples": self.min_learning_samples,
            "learning_confidence_threshold": self.learning_confidence_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HealingConfig:
        """Create configuration from dictionary.

        Args:
            data: Dictionary containing configuration data.

        Returns:
            HealingConfig instance.
        """
        thresholds = None
        if data.get("thresholds"):
            thresholds = [
                HealingThreshold(
                    metric_type=HealthMetricType(t["metric_type"]),
                    warning_threshold=t["warning_threshold"],
                    critical_threshold=t["critical_threshold"],
                    measurement_window=t.get("measurement_window", 300),
                )
                for t in data["thresholds"]
            ]

        project_root = Path(data["project_root"]) if data.get("project_root") else None

        return cls(
            enabled=data.get("enabled", True),
            max_healing_attempts=data.get("max_healing_attempts", 3),
            healing_timeout=data.get("healing_timeout", 600),
            rollback_on_failure=data.get("rollback_on_failure", True),
            log_healing_actions=data.get("log_healing_actions", True),
            thresholds=thresholds,
            project_root=project_root,
            learning_enabled=data.get("learning_enabled", True),
            min_learning_samples=data.get("min_learning_samples", 5),
            learning_confidence_threshold=data.get(
                "learning_confidence_threshold", 0.7
            ),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []

        if self.max_healing_attempts < 1:
            errors.append("max_healing_attempts must be at least 1")

        if self.healing_timeout < 0:
            errors.append("healing_timeout cannot be negative")

        if self.min_learning_samples < 1:
            errors.append("min_learning_samples must be at least 1")

        if not 0 <= self.learning_confidence_threshold <= 1:
            errors.append("learning_confidence_threshold must be between 0 and 1")

        if self.thresholds:
            for threshold in self.thresholds:
                if threshold.warning_threshold >= threshold.critical_threshold:
                    errors.append(
                        f"Warning threshold must be less than critical threshold "
                        f"for {threshold.metric_type.value}"
                    )

                if threshold.measurement_window < 0:
                    errors.append(
                        f"Measurement window cannot be negative for "
                        f"{threshold.metric_type.value}"
                    )

        return errors
