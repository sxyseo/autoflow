"""ROI calculator for time saved vs manual effort.

This module provides comprehensive ROI calculations for autonomous development
by comparing the time taken by Autoflow vs estimated manual development time.
It tracks time savings, cost efficiency, and productivity gains to demonstrate
the value of automated workflows.

The ROI calculator helps answer questions like:
- How much time are we saving by using Autoflow?
- What is our ROI on autonomous development?
- How does automation efficiency compare to manual work?
- What is the cost savings per task?

Usage:
    from autoflow.analytics import ROICalculator

    roi = ROICalculator()
    roi.record_task_completion(
        task_id="build-123",
        autoflow_time_seconds=1800,
        estimated_manual_time_seconds=7200,
        task_complexity="medium"
    )
    metrics = roi.get_roi_summary()
    print(f"Time saved: {metrics.total_time_saved_hours:.1f}h")
    print(f"ROI: {metrics.roi_percentage:.1f}%")
"""

from __future__ import annotations

import json
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class TaskComplexity(str, Enum):
    """Complexity level of a task.

    Attributes:
        TRIVIAL: Very simple task (< 30 min manual)
        SIMPLE: Straightforward task (30 min - 2 hours manual)
        MEDIUM: Moderate complexity (2 - 8 hours manual)
        COMPLEX: Involved task (8 - 24 hours manual)
        VERY_COMPLEX: Highly complex (> 24 hours manual)
    """

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


@dataclass
class ROIRecord:
    """A single ROI measurement for a completed task.

    Attributes:
        task_id: Unique identifier for the task
        autoflow_time_seconds: Actual time taken by Autoflow
        estimated_manual_time_seconds: Estimated time for manual completion
        time_saved_seconds: Difference between manual and autoflow time
        efficiency_ratio: Ratio of manual time to autoflow time
        task_complexity: Complexity classification of the task
        timestamp: When the task was completed
        metadata: Additional context about the task
    """

    task_id: str
    autoflow_time_seconds: float
    estimated_manual_time_seconds: float
    time_saved_seconds: float
    efficiency_ratio: float
    task_complexity: TaskComplexity
    timestamp: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "autoflow_time_seconds": self.autoflow_time_seconds,
            "estimated_manual_time_seconds": self.estimated_manual_time_seconds,
            "time_saved_seconds": self.time_saved_seconds,
            "efficiency_ratio": self.efficiency_ratio,
            "task_complexity": self.task_complexity.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ROIRecord":
        """Create from dictionary for JSON deserialization."""
        return cls(
            task_id=data["task_id"],
            autoflow_time_seconds=data["autoflow_time_seconds"],
            estimated_manual_time_seconds=data["estimated_manual_time_seconds"],
            time_saved_seconds=data["time_saved_seconds"],
            efficiency_ratio=data["efficiency_ratio"],
            task_complexity=TaskComplexity(data["task_complexity"]),
            timestamp=data["timestamp"],
            metadata=data.get("metadata"),
        )


@dataclass
class ROIMetrics:
    """Aggregated ROI metrics for a time period.

    Attributes:
        period_start: Start of the time period
        period_end: End of the time period
        total_tasks: Total number of tasks completed
        total_autoflow_time_seconds: Total time spent by Autoflow
        total_manual_time_estimate_seconds: Total estimated manual time
        total_time_saved_seconds: Total time saved
        total_time_saved_hours: Total time saved in hours
        avg_efficiency_ratio: Average efficiency ratio across all tasks
        median_efficiency_ratio: Median efficiency ratio
        roi_percentage: ROI as a percentage (time saved / autoflow time * 100)
        cost_savings_estimate_usd: Estimated cost savings (optional, requires hourly rate)
        tasks_by_complexity: Breakdown of tasks by complexity level
        time_saved_by_complexity: Time saved breakdown by complexity
    """

    period_start: str | None = None
    period_end: str | None = None
    total_tasks: int = 0
    total_autoflow_time_seconds: float = 0.0
    total_manual_time_estimate_seconds: float = 0.0
    total_time_saved_seconds: float = 0.0
    total_time_saved_hours: float = 0.0
    avg_efficiency_ratio: float = 0.0
    median_efficiency_ratio: float = 0.0
    roi_percentage: float = 0.0
    cost_savings_estimate_usd: float | None = None
    tasks_by_complexity: dict[str, int] = field(default_factory=dict)
    time_saved_by_complexity: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_tasks": self.total_tasks,
            "total_autoflow_time_seconds": self.total_autoflow_time_seconds,
            "total_manual_time_estimate_seconds": self.total_manual_time_estimate_seconds,
            "total_time_saved_seconds": self.total_time_saved_seconds,
            "total_time_saved_hours": self.total_time_saved_hours,
            "avg_efficiency_ratio": self.avg_efficiency_ratio,
            "median_efficiency_ratio": self.median_efficiency_ratio,
            "roi_percentage": self.roi_percentage,
            "cost_savings_estimate_usd": self.cost_savings_estimate_usd,
            "tasks_by_complexity": self.tasks_by_complexity,
            "time_saved_by_complexity": self.time_saved_by_complexity,
        }


@dataclass
class ROITrend:
    """Trend analysis for ROI metrics over time.

    Attributes:
        metric_name: Name of the ROI metric
        current_value: Current metric value
        previous_value: Previous metric value for comparison
        change_rate: Rate of change (e.g., 0.15 for 15% increase)
        trend_direction: Direction of the trend (improving, stable, declining)
        confidence: Confidence score in the trend (0.0 to 1.0)
    """

    metric_name: str
    current_value: float
    previous_value: float
    change_rate: float
    trend_direction: str
    confidence: float


class ROICalculator:
    """Calculate ROI for autonomous development vs manual effort.

    This class tracks and analyzes the return on investment for using Autoflow
    by comparing actual execution time against estimated manual development time.
    It provides comprehensive metrics including time savings, efficiency ratios,
    cost savings, and trend analysis.

    ROI data is persisted to .autoflow/roi.json following the strategy
    memory pattern with atomic writes.

    Example:
        calculator = ROICalculator()
        calculator.record_task_completion(
            task_id="build-123",
            autoflow_time_seconds=1800,  # 30 minutes
            estimated_manual_time_seconds=7200,  # 2 hours
            task_complexity=TaskComplexity.MEDIUM
        )

        metrics = calculator.get_roi_summary()
        print(f"Time saved: {metrics.total_time_saved_hours:.1f}h")
        print(f"Efficiency: {metrics.avg_efficiency_ratio:.1f}x faster")
        print(f"ROI: {metrics.roi_percentage:.1f}%")
    """

    # Default ROI file path
    DEFAULT_ROI_PATH = Path(".autoflow/roi.json")

    # Default hourly rate for cost savings (USD)
    DEFAULT_HOURLY_RATE = 100.0

    def __init__(
        self,
        roi_path: Path | None = None,
        root_dir: Path | None = None,
        max_records: int = 10000,
    ) -> None:
        """Initialize the ROI calculator.

        Args:
            roi_path: Path to ROI JSON file. If None, uses DEFAULT_ROI_PATH
            root_dir: Root directory of the project. Defaults to current directory.
            max_records: Maximum number of records to keep in memory
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if roi_path is None:
            roi_path = self.DEFAULT_ROI_PATH

        self.roi_path = Path(roi_path)
        self.max_records = max_records

        # Ensure parent directory exists
        self.roi_path.parent.mkdir(parents=True, exist_ok=True)

        # ROI records
        self._records: deque[ROIRecord] = deque(maxlen=max_records)

        # Load existing records or initialize empty
        self._load_records()

    def record_task_completion(
        self,
        task_id: str,
        autoflow_time_seconds: float,
        estimated_manual_time_seconds: float,
        task_complexity: TaskComplexity | str = TaskComplexity.MEDIUM,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ROIRecord:
        """Record a completed task and calculate its ROI.

        Args:
            task_id: Unique identifier for the task
            autoflow_time_seconds: Actual time taken by Autoflow
            estimated_manual_time_seconds: Estimated time for manual completion
            task_complexity: Complexity classification of the task
            timestamp: When the task was completed. Defaults to now.
            metadata: Additional context about the task

        Returns:
            ROIRecord with calculated metrics

        Raises:
            ValueError: If time values are invalid
            IOError: If unable to write ROI data to disk
        """
        if autoflow_time_seconds <= 0:
            raise ValueError(f"autoflow_time_seconds must be positive, got {autoflow_time_seconds}")
        if estimated_manual_time_seconds <= 0:
            raise ValueError(f"estimated_manual_time_seconds must be positive, got {estimated_manual_time_seconds}")

        # Normalize complexity to enum
        if isinstance(task_complexity, str):
            task_complexity = TaskComplexity(task_complexity)

        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Calculate ROI metrics
        time_saved_seconds = estimated_manual_time_seconds - autoflow_time_seconds
        efficiency_ratio = estimated_manual_time_seconds / autoflow_time_seconds

        # Create ROI record
        record = ROIRecord(
            task_id=task_id,
            autoflow_time_seconds=autoflow_time_seconds,
            estimated_manual_time_seconds=estimated_manual_time_seconds,
            time_saved_seconds=time_saved_seconds,
            efficiency_ratio=efficiency_ratio,
            task_complexity=task_complexity,
            timestamp=timestamp.isoformat(),
            metadata=metadata,
        )

        # Add to records
        self._records.append(record)

        # Persist to disk
        self._save_records()

        return record

    def get_roi_summary(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        hourly_rate_usd: float | None = None,
    ) -> ROIMetrics:
        """Calculate aggregated ROI metrics for a time period.

        Args:
            start_time: Start of time period. Defaults to earliest record.
            end_time: End of time period. Defaults to latest record.
            hourly_rate_usd: Hourly rate for cost savings calculation.

        Returns:
            ROIMetrics with aggregated statistics
        """
        # Filter records by time range
        records = list(self._records)
        if start_time or end_time:
            filtered = []
            for record in records:
                record_time = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                if start_time and record_time < start_time:
                    continue
                if end_time and record_time > end_time:
                    continue
                filtered.append(record)
            records = filtered

        if not records:
            return ROIMetrics(
                period_start=start_time.isoformat() if start_time else None,
                period_end=end_time.isoformat() if end_time else None,
            )

        # Calculate aggregate metrics
        total_tasks = len(records)
        total_autoflow_time = sum(r.autoflow_time_seconds for r in records)
        total_manual_time = sum(r.estimated_manual_time_seconds for r in records)
        total_time_saved = sum(r.time_saved_seconds for r in records)

        efficiency_ratios = [r.efficiency_ratio for r in records]
        avg_efficiency = statistics.mean(efficiency_ratios)
        median_efficiency = statistics.median(efficiency_ratios)

        # Calculate ROI percentage: (time saved / autoflow time) * 100
        # This represents how much value we get relative to the investment
        roi_percentage = (total_time_saved / total_autoflow_time * 100) if total_autoflow_time > 0 else 0.0

        # Calculate cost savings if hourly rate provided
        cost_savings = None
        if hourly_rate_usd is not None:
            cost_savings = (total_time_saved / 3600) * hourly_rate_usd

        # Break down by complexity
        tasks_by_complexity: dict[str, int] = {}
        time_saved_by_complexity: dict[str, float] = {}

        for record in records:
            complexity = record.task_complexity.value
            tasks_by_complexity[complexity] = tasks_by_complexity.get(complexity, 0) + 1
            time_saved_by_complexity[complexity] = (
                time_saved_by_complexity.get(complexity, 0.0) + record.time_saved_seconds
            )

        # Determine period bounds
        timestamps = [datetime.fromisoformat(r.timestamp.replace("Z", "+00:00")) for r in records]
        period_start = min(timestamps).isoformat() if timestamps else None
        period_end = max(timestamps).isoformat() if timestamps else None

        return ROIMetrics(
            period_start=period_start or (start_time.isoformat() if start_time else None),
            period_end=period_end or (end_time.isoformat() if end_time else None),
            total_tasks=total_tasks,
            total_autoflow_time_seconds=total_autoflow_time,
            total_manual_time_estimate_seconds=total_manual_time,
            total_time_saved_seconds=total_time_saved,
            total_time_saved_hours=total_time_saved / 3600,
            avg_efficiency_ratio=avg_efficiency,
            median_efficiency_ratio=median_efficiency,
            roi_percentage=roi_percentage,
            cost_savings_estimate_usd=cost_savings,
            tasks_by_complexity=tasks_by_complexity,
            time_saved_by_complexity=time_saved_by_complexity,
        )

    def get_roi_trend(
        self,
        metric_name: str = "roi_percentage",
        period_hours: int = 168,  # 1 week
    ) -> ROITrend | None:
        """Analyze trends in ROI metrics over time.

        Args:
            metric_name: Name of the metric to analyze
            period_hours: Time period to compare (current vs previous)

        Returns:
            ROITrend with trend analysis, or None if insufficient data
        """
        if len(self._records) < 2:
            return None

        now = datetime.now(UTC)
        current_period_start = now - timedelta(hours=period_hours)
        previous_period_start = current_period_start - timedelta(hours=period_hours)

        # Get metrics for current period
        current_metrics = self.get_roi_summary(
            start_time=current_period_start,
            end_time=now,
        )

        # Get metrics for previous period
        previous_metrics = self.get_roi_summary(
            start_time=previous_period_start,
            end_time=current_period_start,
        )

        # Extract values
        if metric_name == "roi_percentage":
            current_value = current_metrics.roi_percentage
            previous_value = previous_metrics.roi_percentage
        elif metric_name == "avg_efficiency_ratio":
            current_value = current_metrics.avg_efficiency_ratio
            previous_value = previous_metrics.avg_efficiency_ratio
        elif metric_name == "total_time_saved_hours":
            current_value = current_metrics.total_time_saved_hours
            previous_value = previous_metrics.total_time_saved_hours
        else:
            return None

        # Calculate change rate
        if previous_value == 0:
            change_rate = 0.0
        else:
            change_rate = (current_value - previous_value) / previous_value

        # Determine trend direction
        if change_rate > 0.05:
            trend_direction = "improving"
        elif change_rate < -0.05:
            trend_direction = "declining"
        else:
            trend_direction = "stable"

        # Calculate confidence based on sample size
        confidence = min(1.0, current_metrics.total_tasks / 10.0)

        return ROITrend(
            metric_name=metric_name,
            current_value=current_value,
            previous_value=previous_value,
            change_rate=change_rate,
            trend_direction=trend_direction,
            confidence=confidence,
        )

    def get_record_count(self) -> int:
        """Get the number of ROI records."""
        return len(self._records)

    def clear_records(self) -> None:
        """Clear all ROI records.

        Raises:
            IOError: If unable to write to disk
        """
        self._records.clear()
        self._save_records()

    def export_to_json(
        self,
        output_path: Path,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> None:
        """Export ROI records to a JSON file.

        Args:
            output_path: Path to write the export file
            start_time: Start of time period to export
            end_time: End of time period to export

        Raises:
            IOError: If unable to write to the export file
        """
        # Filter records by time range
        records = list(self._records)
        if start_time or end_time:
            filtered = []
            for record in records:
                record_time = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                if start_time and record_time < start_time:
                    continue
                if end_time and record_time > end_time:
                    continue
                filtered.append(record)
            records = filtered

        # Build export structure
        export_data = {
            "export_timestamp": datetime.now(UTC).isoformat(),
            "record_count": len(records),
            "records": [r.to_dict() for r in records],
        }

        # Write to file
        output_path.write_text(
            json.dumps(export_data, indent=2) + "\n",
            encoding="utf-8",
        )

    def _load_records(self) -> None:
        """Load ROI records from disk.

        Reads the ROI JSON file and populates the records deque.
        Creates an empty file if none exists.
        """
        if not self.roi_path.exists():
            # Create empty ROI file
            self._save_records()
            return

        try:
            data = json.loads(self.roi_path.read_text(encoding="utf-8"))
            records_data = data.get("records", [])

            # Convert dictionaries to ROIRecord objects
            for record_data in records_data:
                try:
                    record = ROIRecord.from_dict(record_data)
                    self._records.append(record)
                except (KeyError, ValueError):
                    # Skip malformed records
                    continue

        except (json.JSONDecodeError, UnicodeDecodeError):
            # If file is corrupted, start fresh
            self._records.clear()

    def _save_records(self) -> None:
        """Save ROI records to disk.

        Writes the records deque to the ROI JSON file.
        Uses atomic write to prevent data loss.

        Raises:
            IOError: If unable to write to the ROI file
        """
        # Build ROI structure
        roi_data = {
            "records": [r.to_dict() for r in self._records],
            "metadata": {
                "total_records": len(self._records),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }

        # Write to file with atomic update
        temp_path = self.roi_path.with_suffix(".tmp")
        try:
            temp_path.write_text(
                json.dumps(roi_data, indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self.roi_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(f"Failed to write ROI data to {self.roi_path}: {e}") from e
