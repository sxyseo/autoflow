"""Base metrics collection and aggregation for analytics.

This module provides the foundational metrics collection system that tracks
performance data across the Autoflow system. It handles metric recording,
aggregation, and persistence for all analytics features.

The metrics system supports:
- Recording metric readings with timestamps
- Aggregating metrics over time windows
- Persisting metrics to disk for later analysis
- Querying metrics by time range and type

Usage:
    from autoflow.analytics import MetricsCollector

    collector = MetricsCollector()
    collector.record_metric("task_duration", 45.2, metadata={"task_id": "build-123"})
    summary = collector.get_metric_summary("task_duration")
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class MetricType(str, Enum):
    """Types of metrics that can be collected.

    Attributes:
        COUNTER: Cumulative counter that only increases (e.g., tasks completed)
        GAUGE: Point-in-time value that can go up or down (e.g., memory usage)
        HISTOGRAM: Distribution of values (e.g., task durations)
        SUMMARY: Histogram with calculated statistics (mean, percentile, etc.)
    """

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricReading:
    """A single metric reading with timestamp and optional metadata.

    Attributes:
        metric_name: Name of the metric (e.g., "task_duration", "tests_passed")
        value: The metric value (numeric)
        timestamp: When the reading was recorded (ISO format string)
        metric_type: Type of metric (counter, gauge, histogram, summary)
        metadata: Optional additional context (e.g., task_id, agent_name)
        labels: Optional key-value pairs for grouping/filtering
    """

    metric_name: str
    value: float
    timestamp: str
    metric_type: MetricType
    metadata: dict[str, Any] | None = None
    labels: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "timestamp": self.timestamp,
            "metric_type": self.metric_type.value,
            "metadata": self.metadata or {},
            "labels": self.labels or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricReading":
        """Create from dictionary for JSON deserialization."""
        return cls(
            metric_name=data["metric_name"],
            value=data["value"],
            timestamp=data["timestamp"],
            metric_type=MetricType(data["metric_type"]),
            metadata=data.get("metadata"),
            labels=data.get("labels"),
        )


@dataclass
class MetricSummary:
    """Summary statistics for a metric over a time window.

    Attributes:
        metric_name: Name of the metric
        count: Number of readings in the summary
        min: Minimum value (None if no readings)
        max: Maximum value (None if no readings)
        mean: Average value (None if no readings)
        sum: Sum of all values (0 if no readings)
        percentile_50: Median value (50th percentile)
        percentile_95: 95th percentile value
        percentile_99: 99th percentile value
        start_time: Start of the time window (ISO format)
        end_time: End of the time window (ISO format)
    """

    metric_name: str
    count: int
    min: float | None
    max: float | None
    mean: float | None
    sum: float
    percentile_50: float | None = None
    percentile_95: float | None = None
    percentile_99: float | None = None
    start_time: str | None = None
    end_time: str | None = None


@dataclass
class MetricWindow:
    """A time-windowed collection of metric readings.

    Attributes:
        metric_name: Name of the metric
        readings: Deque of readings in this window
        max_size: Maximum number of readings to keep in the window
        window_start: Start timestamp of the window
        window_end: End timestamp of the window
    """

    metric_name: str
    readings: deque[MetricReading] = field(default_factory=deque)
    max_size: int = 1000
    window_start: datetime | None = None
    window_end: datetime | None = None

    def add_reading(self, reading: MetricReading) -> None:
        """Add a reading to the window, evicting oldest if at capacity.

        Args:
            reading: The metric reading to add
        """
        # Enforce max size
        if len(self.readings) >= self.max_size:
            self.readings.popleft()

        self.readings.append(reading)

        # Update window bounds
        reading_time = datetime.fromisoformat(reading.timestamp.replace("Z", "+00:00"))
        if self.window_start is None or reading_time < self.window_start:
            self.window_start = reading_time
        if self.window_end is None or reading_time > self.window_end:
            self.window_end = reading_time


class MetricsCollector:
    """Collect and manage performance metrics for analytics.

    This class provides the core metrics collection infrastructure used by
    all analytics features. It handles:
    - Recording metric readings with timestamps
    - Managing time-windowed metric storage
    - Calculating summary statistics
    - Persisting metrics to disk
    - Querying metrics by type and time range

    Metrics are stored in .autoflow/metrics.json following the strategy
    memory pattern with atomic writes.

    Example:
        collector = MetricsCollector()
        collector.record_metric("task_duration", 45.2, metadata={"task_id": "build-123"})
        collector.record_metric("tests_passed", 12, metric_type=MetricType.COUNTER)

        summary = collector.get_metric_summary("task_duration")
        print(f"Average duration: {summary.mean:.2f}s")
    """

    # Default metrics file path
    DEFAULT_METRICS_PATH = Path(".autoflow/metrics.json")

    def __init__(
        self,
        metrics_path: Path | None = None,
        root_dir: Path | None = None,
        window_size: int = 1000,
    ) -> None:
        """Initialize the metrics collector.

        Args:
            metrics_path: Path to metrics JSON file. If None, uses DEFAULT_METRICS_PATH
            root_dir: Root directory of the project. Defaults to current directory.
            window_size: Maximum number of readings to keep per metric window.
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if metrics_path is None:
            metrics_path = self.DEFAULT_METRICS_PATH

        self.metrics_path = Path(metrics_path)
        self.window_size = window_size

        # Ensure parent directory exists
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)

        # Metric windows by metric name
        self._windows: dict[str, MetricWindow] = {}

        # Load existing metrics or initialize empty
        self._load_metrics()

    def record_metric(
        self,
        metric_name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a metric reading.

        Creates a new metric reading with the current timestamp and stores it
        in the appropriate time window.

        Args:
            metric_name: Name of the metric (e.g., "task_duration", "tests_passed")
            value: The metric value (numeric)
            metric_type: Type of metric (counter, gauge, histogram, summary)
            timestamp: When the reading was recorded. Defaults to now.
            metadata: Optional additional context (e.g., task_id, agent_name)
            labels: Optional key-value pairs for grouping/filtering

        Raises:
            IOError: If unable to write metrics to disk
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Create metric reading
        reading = MetricReading(
            metric_name=metric_name,
            value=float(value),
            timestamp=timestamp.isoformat(),
            metric_type=metric_type,
            metadata=metadata,
            labels=labels,
        )

        # Get or create window for this metric
        if metric_name not in self._windows:
            self._windows[metric_name] = MetricWindow(
                metric_name=metric_name,
                max_size=self.window_size,
            )

        # Add reading to window
        self._windows[metric_name].add_reading(reading)

        # Persist to disk
        self._save_metrics()

    def get_metric_summary(
        self,
        metric_name: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> MetricSummary:
        """Calculate summary statistics for a metric.

        Computes min, max, mean, percentiles, and other statistics for
        the specified metric over the given time range.

        Args:
            metric_name: Name of the metric to summarize
            start_time: Start of time window. Defaults to window start.
            end_time: End of time window. Defaults to window end.

        Returns:
            MetricSummary with calculated statistics

        Raises:
            ValueError: If metric not found or no readings in time range
        """
        if metric_name not in self._windows:
            raise ValueError(f"Metric not found: {metric_name}")

        window = self._windows[metric_name]

        # Filter readings by time range
        readings = list(window.readings)
        if start_time or end_time:
            filtered = []
            for reading in readings:
                reading_time = datetime.fromisoformat(
                    reading.timestamp.replace("Z", "+00:00")
                )
                if start_time and reading_time < start_time:
                    continue
                if end_time and reading_time > end_time:
                    continue
                filtered.append(reading)
            readings = filtered

        if not readings:
            return MetricSummary(
                metric_name=metric_name,
                count=0,
                min=None,
                max=None,
                mean=None,
                sum=0.0,
                start_time=start_time.isoformat() if start_time else None,
                end_time=end_time.isoformat() if end_time else None,
            )

        # Extract values
        values = [r.value for r in readings]

        # Calculate basic statistics
        count = len(values)
        value_sum = sum(values)
        value_min = min(values)
        value_max = max(values)
        value_mean = value_sum / count if count > 0 else 0.0

        # Calculate percentiles
        sorted_values = sorted(values)
        p50_idx = int(len(sorted_values) * 0.5)
        p95_idx = int(len(sorted_values) * 0.95)
        p99_idx = int(len(sorted_values) * 0.99)

        p50 = sorted_values[p50_idx] if sorted_values else None
        p95 = sorted_values[p95_idx] if sorted_values else None
        p99 = sorted_values[p99_idx] if sorted_values else None

        return MetricSummary(
            metric_name=metric_name,
            count=count,
            min=value_min,
            max=value_max,
            mean=value_mean,
            sum=value_sum,
            percentile_50=p50,
            percentile_95=p95,
            percentile_99=p99,
            start_time=start_time.isoformat()
            if start_time
            else window.window_start.isoformat()
            if window.window_start
            else None,
            end_time=end_time.isoformat()
            if end_time
            else window.window_end.isoformat()
            if window.window_end
            else None,
        )

    def get_metric_names(self) -> list[str]:
        """Get list of all metric names being tracked.

        Returns:
            List of metric names
        """
        return list(self._windows.keys())

    def get_metric_count(self, metric_name: str | None = None) -> int:
        """Get count of readings for a metric or all metrics.

        Args:
            metric_name: Specific metric to count. If None, counts all metrics.

        Returns:
            Number of readings
        """
        if metric_name:
            if metric_name not in self._windows:
                return 0
            return len(self._windows[metric_name].readings)

        return sum(len(w.readings) for w in self._windows.values())

    def query_metrics(
        self,
        metric_name: str | None = None,
        label_filter: dict[str, str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[MetricReading]:
        """Query metrics with optional filters.

        Args:
            metric_name: Specific metric to query. If None, queries all metrics.
            label_filter: Filter by label key-value pairs
            start_time: Filter to readings after this time
            end_time: Filter to readings before this time
            limit: Maximum number of readings to return

        Returns:
            List of matching metric readings
        """
        all_readings: list[MetricReading] = []

        # Collect readings from relevant windows
        windows_to_search = (
            [self._windows[metric_name]] if metric_name else self._windows.values()
        )

        for window in windows_to_search:
            for reading in window.readings:
                # Filter by metric name if specified
                if metric_name and reading.metric_name != metric_name:
                    continue

                # Filter by labels if specified
                if label_filter:
                    if not reading.labels:
                        continue
                    if not all(
                        reading.labels.get(k) == v for k, v in label_filter.items()
                    ):
                        continue

                # Filter by time range
                reading_time = datetime.fromisoformat(
                    reading.timestamp.replace("Z", "+00:00")
                )
                if start_time and reading_time < start_time:
                    continue
                if end_time and reading_time > end_time:
                    continue

                all_readings.append(reading)

        # Sort by timestamp (most recent first)
        all_readings.sort(key=lambda r: r.timestamp, reverse=True)

        # Apply limit
        if limit:
            all_readings = all_readings[:limit]

        return all_readings

    def clear_metric(self, metric_name: str) -> None:
        """Clear all readings for a specific metric.

        Args:
            metric_name: Name of the metric to clear

        Raises:
            ValueError: If metric not found
            IOError: If unable to write metrics to disk
        """
        if metric_name not in self._windows:
            raise ValueError(f"Metric not found: {metric_name}")

        self._windows[metric_name].readings.clear()
        self._windows[metric_name].window_start = None
        self._windows[metric_name].window_end = None

        self._save_metrics()

    def clear_all_metrics(self) -> None:
        """Clear all metric readings.

        Raises:
            IOError: If unable to write metrics to disk
        """
        self._windows.clear()
        self._save_metrics()

    def _load_metrics(self) -> None:
        """Load metrics from disk.

        Reads the metrics JSON file and populates the windows dictionary.
        Creates an empty metrics file if none exists.
        """
        if not self.metrics_path.exists():
            # Create empty metrics file
            self._save_metrics()
            return

        try:
            data = json.loads(self.metrics_path.read_text(encoding="utf-8"))
            windows_data = data.get("windows", {})

            # Convert dictionaries to MetricWindow objects
            for metric_name, window_data in windows_data.items():
                readings_data = window_data.get("readings", [])
                readings = deque(
                    [MetricReading.from_dict(r) for r in readings_data],
                    maxlen=self.window_size,
                )

                self._windows[metric_name] = MetricWindow(
                    metric_name=metric_name,
                    readings=readings,
                    max_size=window_data.get("max_size", self.window_size),
                )

        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            # If file is corrupted, start fresh
            self._windows = {}

    def _save_metrics(self) -> None:
        """Save metrics to disk.

        Writes the windows dictionary to the metrics JSON file.
        Uses atomic write to prevent data loss.

        Raises:
            IOError: If unable to write to the metrics file
        """
        # Convert windows to dictionaries
        windows_data = {}
        for metric_name, window in self._windows.items():
            windows_data[metric_name] = {
                "metric_name": window.metric_name,
                "max_size": window.max_size,
                "readings": [r.to_dict() for r in window.readings],
            }

        # Build metrics structure
        metrics_data = {
            "windows": windows_data,
            "metadata": {
                "total_metrics": len(self._windows),
                "total_readings": self.get_metric_count(),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }

        # Write to file with atomic update
        temp_path = self.metrics_path.with_suffix(".tmp")
        try:
            temp_path.write_text(
                json.dumps(metrics_data, indent=2) + "\n", encoding="utf-8"
            )
            temp_path.replace(self.metrics_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(f"Failed to write metrics to {self.metrics_path}: {e}") from e
