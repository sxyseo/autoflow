"""
Unit Tests for Analytics Metrics Module

Tests the MetricsCollector class and related models (MetricReading, MetricSummary,
MetricWindow, MetricType) for performance metrics collection and aggregation.

These tests use temporary directories to avoid affecting real metrics files.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.analytics.metrics import (
    MetricReading,
    MetricSummary,
    MetricType,
    MetricWindow,
    MetricsCollector,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_metrics_dir(tmp_path: Path) -> Path:
    """Create a temporary metrics directory."""
    metrics_dir = tmp_path / ".autoflow"
    metrics_dir.mkdir()
    return metrics_dir


@pytest.fixture
def metrics_file(temp_metrics_dir: Path) -> Path:
    """Create a metrics file path."""
    return temp_metrics_dir / "metrics.json"


@pytest.fixture
def metrics_collector(temp_metrics_dir: Path) -> MetricsCollector:
    """Create a MetricsCollector instance with temporary directory."""
    collector = MetricsCollector(
        metrics_path=temp_metrics_dir / "metrics.json",
        root_dir=temp_metrics_dir,
    )
    return collector


@pytest.fixture
def sample_reading_data() -> dict[str, Any]:
    """Return sample metric reading data for testing."""
    return {
        "metric_name": "task_duration",
        "value": 45.2,
        "timestamp": "2024-01-15T10:30:00+00:00",
        "metric_type": "histogram",
        "metadata": {"task_id": "build-123", "agent": "claude-code"},
        "labels": {"project": "autoflow", "stage": "build"},
    }


@pytest.fixture
def sample_timestamp() -> datetime:
    """Return a sample timestamp for testing."""
    return datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)


# ============================================================================
# MetricType Enum Tests
# ============================================================================


class TestMetricType:
    """Tests for MetricType enum."""

    def test_metric_type_values(self) -> None:
        """Test MetricType enum values."""
        assert MetricType.COUNTER == "counter"
        assert MetricType.GAUGE == "gauge"
        assert MetricType.HISTOGRAM == "histogram"
        assert MetricType.SUMMARY == "summary"

    def test_metric_type_is_string(self) -> None:
        """Test that MetricType values are strings."""
        assert isinstance(MetricType.COUNTER.value, str)

    def test_metric_type_from_string(self) -> None:
        """Test creating MetricType from string."""
        metric_type = MetricType("histogram")
        assert metric_type == MetricType.HISTOGRAM


# ============================================================================
# MetricReading Model Tests
# ============================================================================


class TestMetricReading:
    """Tests for MetricReading model."""

    def test_reading_init_minimal(self) -> None:
        """Test MetricReading initialization with minimal fields."""
        reading = MetricReading(
            metric_name="test_metric",
            value=42.0,
            timestamp="2024-01-15T10:30:00+00:00",
            metric_type=MetricType.GAUGE,
        )

        assert reading.metric_name == "test_metric"
        assert reading.value == 42.0
        assert reading.metadata is None
        assert reading.labels is None

    def test_reading_init_full(self) -> None:
        """Test MetricReading initialization with all fields."""
        reading = MetricReading(
            metric_name="test_metric",
            value=100.5,
            timestamp="2024-01-15T10:30:00+00:00",
            metric_type=MetricType.HISTOGRAM,
            metadata={"task_id": "task-001"},
            labels={"agent": "claude-code"},
        )

        assert reading.metric_name == "test_metric"
        assert reading.value == 100.5
        assert reading.metadata == {"task_id": "task-001"}
        assert reading.labels == {"agent": "claude-code"}

    def test_reading_to_dict(self, sample_reading_data: dict) -> None:
        """Test MetricReading.to_dict() serialization."""
        reading = MetricReading.from_dict(sample_reading_data)
        result = reading.to_dict()

        assert result["metric_name"] == "task_duration"
        assert result["value"] == 45.2
        assert result["metric_type"] == "histogram"
        assert result["metadata"]["task_id"] == "build-123"
        assert result["labels"]["project"] == "autoflow"

    def test_reading_from_dict(self, sample_reading_data: dict) -> None:
        """Test MetricReading.from_dict() deserialization."""
        reading = MetricReading.from_dict(sample_reading_data)

        assert reading.metric_name == "task_duration"
        assert reading.value == 45.2
        assert reading.metric_type == MetricType.HISTOGRAM
        assert reading.metadata["task_id"] == "build-123"
        assert reading.labels["project"] == "autoflow"

    def test_reading_roundtrip(self, sample_reading_data: dict) -> None:
        """Test MetricReading serialization roundtrip."""
        original = MetricReading.from_dict(sample_reading_data)
        dict_repr = original.to_dict()
        restored = MetricReading.from_dict(dict_repr)

        assert restored.metric_name == original.metric_name
        assert restored.value == original.value
        assert restored.metric_type == original.metric_type
        assert restored.metadata == original.metadata
        assert restored.labels == original.labels

    def test_reading_from_dict_minimal(self) -> None:
        """Test from_dict with minimal required fields."""
        data = {
            "metric_name": "test_metric",
            "value": 42.0,
            "timestamp": "2024-01-15T10:30:00+00:00",
            "metric_type": "gauge",
        }
        reading = MetricReading.from_dict(data)

        assert reading.metric_name == "test_metric"
        assert reading.metadata is None
        assert reading.labels is None


# ============================================================================
# MetricSummary Model Tests
# ============================================================================


class TestMetricSummary:
    """Tests for MetricSummary model."""

    def test_summary_init_with_data(self) -> None:
        """Test MetricSummary initialization with actual data."""
        summary = MetricSummary(
            metric_name="task_duration",
            count=10,
            min=1.5,
            max=100.0,
            mean=45.2,
            sum=452.0,
            percentile_50=42.0,
            percentile_95=95.0,
            percentile_99=99.0,
            start_time="2024-01-15T10:00:00+00:00",
            end_time="2024-01-15T11:00:00+00:00",
        )

        assert summary.metric_name == "task_duration"
        assert summary.count == 10
        assert summary.min == 1.5
        assert summary.max == 100.0
        assert summary.mean == 45.2

    def test_summary_init_empty(self) -> None:
        """Test MetricSummary initialization with no data."""
        summary = MetricSummary(
            metric_name="empty_metric",
            count=0,
            min=None,
            max=None,
            mean=None,
            sum=0.0,
        )

        assert summary.metric_name == "empty_metric"
        assert summary.count == 0
        assert summary.min is None
        assert summary.max is None
        assert summary.mean is None
        assert summary.sum == 0.0


# ============================================================================
# MetricWindow Model Tests
# ============================================================================


class TestMetricWindow:
    """Tests for MetricWindow model."""

    def test_window_init(self) -> None:
        """Test MetricWindow initialization."""
        window = MetricWindow(metric_name="test_metric", max_size=100)

        assert window.metric_name == "test_metric"
        assert window.max_size == 100
        assert len(window.readings) == 0
        assert window.window_start is None
        assert window.window_end is None

    def test_window_add_reading(self, sample_timestamp: datetime) -> None:
        """Test adding reading to window."""
        window = MetricWindow(metric_name="test_metric", max_size=10)
        reading = MetricReading(
            metric_name="test_metric",
            value=42.0,
            timestamp=sample_timestamp.isoformat(),
            metric_type=MetricType.GAUGE,
        )

        window.add_reading(reading)

        assert len(window.readings) == 1
        assert window.window_start == sample_timestamp
        assert window.window_end == sample_timestamp

    def test_window_add_multiple_readings(self, sample_timestamp: datetime) -> None:
        """Test adding multiple readings to window."""
        window = MetricWindow(metric_name="test_metric", max_size=10)

        for i in range(5):
            reading = MetricReading(
                metric_name="test_metric",
                value=float(i * 10),
                timestamp=(sample_timestamp + timedelta(seconds=i)).isoformat(),
                metric_type=MetricType.GAUGE,
            )
            window.add_reading(reading)

        assert len(window.readings) == 5
        assert window.window_start == sample_timestamp
        assert window.window_end == sample_timestamp + timedelta(seconds=4)

    def test_window_max_size_enforcement(self, sample_timestamp: datetime) -> None:
        """Test window enforces max_size by evicting oldest."""
        window = MetricWindow(metric_name="test_metric", max_size=3)

        # Add 5 readings
        for i in range(5):
            reading = MetricReading(
                metric_name="test_metric",
                value=float(i),
                timestamp=(sample_timestamp + timedelta(seconds=i)).isoformat(),
                metric_type=MetricType.GAUGE,
            )
            window.add_reading(reading)

        # Should only keep last 3
        assert len(window.readings) == 3
        values = [r.value for r in window.readings]
        assert values == [2.0, 3.0, 4.0]  # Oldest evicted

    def test_window_bounds_update(self, sample_timestamp: datetime) -> None:
        """Test window bounds update correctly."""
        window = MetricWindow(metric_name="test_metric", max_size=10)

        # Add first reading
        window.add_reading(
            MetricReading(
                metric_name="test_metric",
                value=1.0,
                timestamp=(sample_timestamp + timedelta(seconds=10)).isoformat(),
                metric_type=MetricType.GAUGE,
            )
        )

        assert window.window_start == sample_timestamp + timedelta(seconds=10)
        assert window.window_end == sample_timestamp + timedelta(seconds=10)

        # Add earlier reading
        window.add_reading(
            MetricReading(
                metric_name="test_metric",
                value=2.0,
                timestamp=sample_timestamp.isoformat(),
                metric_type=MetricType.GAUGE,
            )
        )

        assert window.window_start == sample_timestamp  # Updated to earlier
        assert window.window_end == sample_timestamp + timedelta(seconds=10)

        # Add later reading
        window.add_reading(
            MetricReading(
                metric_name="test_metric",
                value=3.0,
                timestamp=(sample_timestamp + timedelta(seconds=20)).isoformat(),
                metric_type=MetricType.GAUGE,
            )
        )

        assert window.window_start == sample_timestamp
        assert window.window_end == sample_timestamp + timedelta(seconds=20)


# ============================================================================
# MetricsCollector Initialization Tests
# ============================================================================


class TestMetricsCollectorInit:
    """Tests for MetricsCollector initialization."""

    def test_init_with_defaults(self, temp_metrics_dir: Path) -> None:
        """Test MetricsCollector initialization with defaults."""
        collector = MetricsCollector(
            metrics_path=temp_metrics_dir / "metrics.json",
            root_dir=temp_metrics_dir,
        )

        assert collector.metrics_path == temp_metrics_dir / "metrics.json"
        assert collector.window_size == 1000
        assert collector.get_metric_names() == []

    def test_init_with_custom_window_size(self, temp_metrics_dir: Path) -> None:
        """Test MetricsCollector initialization with custom window size."""
        collector = MetricsCollector(
            metrics_path=temp_metrics_dir / "metrics.json",
            root_dir=temp_metrics_dir,
            window_size=100,
        )

        assert collector.window_size == 100

    def test_init_creates_directory(self, temp_metrics_dir: Path) -> None:
        """Test MetricsCollector creates parent directory."""
        metrics_path = temp_metrics_dir / "nested" / "metrics.json"
        collector = MetricsCollector(
            metrics_path=metrics_path,
            root_dir=temp_metrics_dir,
        )

        assert metrics_path.parent.exists()

    def test_init_loads_existing_metrics(
        self, temp_metrics_dir: Path, sample_reading_data: dict
    ) -> None:
        """Test MetricsCollector loads existing metrics from disk."""
        metrics_path = temp_metrics_dir / "metrics.json"

        # Create existing metrics file
        existing_data = {
            "windows": {
                "test_metric": {
                    "metric_name": "test_metric",
                    "max_size": 1000,
                    "readings": [sample_reading_data],
                }
            },
            "metadata": {
                "total_metrics": 1,
                "total_readings": 1,
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }
        metrics_path.write_text(json.dumps(existing_data))

        # Create collector - should load existing
        collector = MetricsCollector(
            metrics_path=metrics_path,
            root_dir=temp_metrics_dir,
        )

        assert "test_metric" in collector.get_metric_names()
        assert collector.get_metric_count("test_metric") == 1

    def test_init_handles_corrupted_file(
        self, temp_metrics_dir: Path
    ) -> None:
        """Test MetricsCollector handles corrupted metrics file."""
        metrics_path = temp_metrics_dir / "metrics.json"

        # Write corrupted JSON
        metrics_path.write_text("not valid json")

        # Should not raise error, just start fresh
        collector = MetricsCollector(
            metrics_path=metrics_path,
            root_dir=temp_metrics_dir,
        )

        assert collector.get_metric_names() == []

    def test_init_creates_new_file_if_not_exists(
        self, temp_metrics_dir: Path
    ) -> None:
        """Test MetricsCollector creates new metrics file if not exists."""
        metrics_path = temp_metrics_dir / "new_metrics.json"

        assert not metrics_path.exists()

        collector = MetricsCollector(
            metrics_path=metrics_path,
            root_dir=temp_metrics_dir,
        )

        # Should create empty metrics file
        assert metrics_path.exists()


# ============================================================================
# MetricsCollector Recording Tests
# ============================================================================


class TestMetricsCollectorRecording:
    """Tests for MetricsCollector record_metric method."""

    def test_record_metric_basic(self, metrics_collector: MetricsCollector) -> None:
        """Test recording a basic metric."""
        metrics_collector.record_metric("test_metric", 42.0)

        assert "test_metric" in metrics_collector.get_metric_names()
        assert metrics_collector.get_metric_count("test_metric") == 1

    def test_record_metric_with_type(self, metrics_collector: MetricsCollector) -> None:
        """Test recording metric with specific type."""
        metrics_collector.record_metric(
            "counter_metric", 1.0, metric_type=MetricType.COUNTER
        )

        readings = metrics_collector.query_metrics("counter_metric")
        assert len(readings) == 1
        assert readings[0].metric_type == MetricType.COUNTER

    def test_record_metric_with_metadata(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Test recording metric with metadata."""
        metadata = {"task_id": "build-123", "agent": "claude-code"}
        metrics_collector.record_metric(
            "task_duration", 45.2, metadata=metadata
        )

        readings = metrics_collector.query_metrics("task_duration")
        assert readings[0].metadata == metadata

    def test_record_metric_with_labels(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Test recording metric with labels."""
        labels = {"project": "autoflow", "stage": "build"}
        metrics_collector.record_metric(
            "build_time", 120.5, labels=labels
        )

        readings = metrics_collector.query_metrics("build_time")
        assert readings[0].labels == labels

    def test_record_metric_with_custom_timestamp(
        self, metrics_collector: MetricsCollector, sample_timestamp: datetime
    ) -> None:
        """Test recording metric with custom timestamp."""
        metrics_collector.record_metric(
            "test_metric", 42.0, timestamp=sample_timestamp
        )

        readings = metrics_collector.query_metrics("test_metric")
        assert readings[0].timestamp == sample_timestamp.isoformat()

    def test_record_metric_multiple_readings(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Test recording multiple metric readings."""
        for i in range(10):
            metrics_collector.record_metric("test_metric", float(i))

        assert metrics_collector.get_metric_count("test_metric") == 10

    def test_record_metric_persists_to_disk(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Test recording metric persists to disk."""
        metrics_collector.record_metric("persistent_metric", 99.9)

        # Load from file
        data = json.loads(metrics_collector.metrics_path.read_text())
        assert "persistent_metric" in data["windows"]

    def test_record_metric_creates_window(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Test recording metric creates new window."""
        metrics_collector.record_metric("new_metric", 1.0)

        assert "new_metric" in metrics_collector._windows
        assert metrics_collector._windows["new_metric"].metric_name == "new_metric"


# ============================================================================
# MetricsCollector Summary Tests
# ============================================================================


class TestMetricsCollectorSummary:
    """Tests for MetricsCollector get_metric_summary method."""

    def test_get_summary_basic(self, metrics_collector: MetricsCollector) -> None:
        """Test getting basic metric summary."""
        for value in [10.0, 20.0, 30.0, 40.0, 50.0]:
            metrics_collector.record_metric("test_metric", value)

        summary = metrics_collector.get_metric_summary("test_metric")

        assert summary.metric_name == "test_metric"
        assert summary.count == 5
        assert summary.min == 10.0
        assert summary.max == 50.0
        assert summary.mean == 30.0
        assert summary.sum == 150.0

    def test_get_summary_percentiles(self, metrics_collector: MetricsCollector) -> None:
        """Test getting summary with percentiles."""
        values = list(range(1, 101))  # 1 to 100
        for value in values:
            metrics_collector.record_metric("test_metric", float(value))

        summary = metrics_collector.get_metric_summary("test_metric")

        # Percentiles use 0-based indexing: int(100 * 0.5) = index 50 = value 51
        assert summary.percentile_50 == 51  # Median (index 50 in 0-indexed)
        assert summary.percentile_95 == 96  # Index 95
        assert summary.percentile_99 == 100  # Index 99

    def test_get_summary_with_time_range(
        self, metrics_collector: MetricsCollector, sample_timestamp: datetime
    ) -> None:
        """Test getting summary with time range filter."""
        # Record metrics at different times
        for i in range(5):
            ts = sample_timestamp + timedelta(minutes=i)
            metrics_collector.record_metric(
                "test_metric", float(i * 10), timestamp=ts
            )

        # Get summary for middle 3 readings
        start = sample_timestamp + timedelta(minutes=1)
        end = sample_timestamp + timedelta(minutes=3)

        summary = metrics_collector.get_metric_summary(
            "test_metric", start_time=start, end_time=end
        )

        assert summary.count == 3  # minutes 1, 2, 3
        assert summary.min == 10.0
        assert summary.max == 30.0

    def test_get_summary_empty_metric(self, metrics_collector: MetricsCollector) -> None:
        """Test getting summary for metric with no readings in range."""
        metrics_collector.record_metric("test_metric", 42.0)

        # Use time range that excludes all readings
        future = datetime.now(UTC) + timedelta(days=1)
        summary = metrics_collector.get_metric_summary(
            "test_metric", start_time=future
        )

        assert summary.count == 0
        assert summary.min is None
        assert summary.max is None
        assert summary.mean is None

    def test_get_summary_nonexistent_metric(self, metrics_collector: MetricsCollector) -> None:
        """Test getting summary for nonexistent metric raises error."""
        with pytest.raises(ValueError, match="Metric not found"):
            metrics_collector.get_metric_summary("nonexistent_metric")

    def test_get_summary_single_reading(self, metrics_collector: MetricsCollector) -> None:
        """Test getting summary with single reading."""
        metrics_collector.record_metric("test_metric", 42.0)

        summary = metrics_collector.get_metric_summary("test_metric")

        assert summary.count == 1
        assert summary.min == 42.0
        assert summary.max == 42.0
        assert summary.mean == 42.0


# ============================================================================
# MetricsCollector Query Tests
# ============================================================================


class TestMetricsCollectorQuery:
    """Tests for MetricsCollector query_metrics method."""

    def test_query_all_metrics(self, metrics_collector: MetricsCollector) -> None:
        """Test querying all metrics."""
        metrics_collector.record_metric("metric1", 1.0)
        metrics_collector.record_metric("metric2", 2.0)

        results = metrics_collector.query_metrics()

        assert len(results) == 2

    def test_query_specific_metric(self, metrics_collector: MetricsCollector) -> None:
        """Test querying specific metric."""
        metrics_collector.record_metric("metric1", 1.0)
        metrics_collector.record_metric("metric2", 2.0)

        results = metrics_collector.query_metrics("metric1")

        assert len(results) == 1
        assert results[0].metric_name == "metric1"

    def test_query_by_labels(self, metrics_collector: MetricsCollector) -> None:
        """Test querying by label filter."""
        metrics_collector.record_metric(
            "test_metric", 1.0, labels={"project": "autoflow"}
        )
        metrics_collector.record_metric(
            "test_metric", 2.0, labels={"project": "other"}
        )

        results = metrics_collector.query_metrics(
            label_filter={"project": "autoflow"}
        )

        assert len(results) == 1
        assert results[0].value == 1.0

    def test_query_by_time_range(
        self, metrics_collector: MetricsCollector, sample_timestamp: datetime
    ) -> None:
        """Test querying by time range."""
        for i in range(5):
            ts = sample_timestamp + timedelta(hours=i)
            metrics_collector.record_metric("test_metric", float(i), timestamp=ts)

        # Query for first 3 hours
        end = sample_timestamp + timedelta(hours=2, minutes=59)
        results = metrics_collector.query_metrics(
            "test_metric", end_time=end
        )

        assert len(results) == 3

    def test_query_with_limit(self, metrics_collector: MetricsCollector) -> None:
        """Test querying with limit."""
        for i in range(10):
            metrics_collector.record_metric("test_metric", float(i))

        results = metrics_collector.query_metrics("test_metric", limit=5)

        assert len(results) == 5

    def test_query_sorted_by_timestamp(
        self, metrics_collector: MetricsCollector, sample_timestamp: datetime
    ) -> None:
        """Test query results are sorted by timestamp descending."""
        for i in range(5):
            ts = sample_timestamp + timedelta(seconds=i)
            metrics_collector.record_metric("test_metric", float(i), timestamp=ts)

        results = metrics_collector.query_metrics("test_metric")

        # Most recent first
        assert results[0].value == 4.0
        assert results[-1].value == 0.0

    def test_query_empty_result(self, metrics_collector: MetricsCollector) -> None:
        """Test query with no matching results."""
        metrics_collector.record_metric("test_metric", 1.0)

        results = metrics_collector.query_metrics(
            label_filter={"nonexistent": "label"}
        )

        assert len(results) == 0


# ============================================================================
# MetricsCollector Clear Tests
# ============================================================================


class TestMetricsCollectorClear:
    """Tests for MetricsCollector clear methods."""

    def test_clear_metric(self, metrics_collector: MetricsCollector) -> None:
        """Test clearing a specific metric."""
        metrics_collector.record_metric("metric1", 1.0)
        metrics_collector.record_metric("metric2", 2.0)

        metrics_collector.clear_metric("metric1")

        # Window should still exist but with no readings
        assert metrics_collector.get_metric_count("metric1") == 0
        assert metrics_collector.get_metric_count("metric2") == 1

    def test_clear_metric_persists(self, metrics_collector: MetricsCollector) -> None:
        """Test clearing metric persists to disk."""
        metrics_collector.record_metric("to_clear", 1.0)
        metrics_collector.clear_metric("to_clear")

        # Load from file
        data = json.loads(metrics_collector.metrics_path.read_text())
        # Window should still exist but with empty readings
        assert "to_clear" in data["windows"]
        assert len(data["windows"]["to_clear"]["readings"]) == 0

    def test_clear_nonexistent_metric(self, metrics_collector: MetricsCollector) -> None:
        """Test clearing nonexistent metric raises error."""
        with pytest.raises(ValueError, match="Metric not found"):
            metrics_collector.clear_metric("nonexistent")

    def test_clear_all_metrics(self, metrics_collector: MetricsCollector) -> None:
        """Test clearing all metrics."""
        metrics_collector.record_metric("metric1", 1.0)
        metrics_collector.record_metric("metric2", 2.0)

        metrics_collector.clear_all_metrics()

        assert metrics_collector.get_metric_names() == []
        assert metrics_collector.get_metric_count() == 0

    def test_clear_all_persists(self, metrics_collector: MetricsCollector) -> None:
        """Test clearing all metrics persists to disk."""
        metrics_collector.record_metric("metric1", 1.0)
        metrics_collector.clear_all_metrics()

        # Load from file
        data = json.loads(metrics_collector.metrics_path.read_text())
        assert len(data["windows"]) == 0


# ============================================================================
# MetricsCollector Utility Tests
# ============================================================================


class TestMetricsCollectorUtilities:
    """Tests for MetricsCollector utility methods."""

    def test_get_metric_names(self, metrics_collector: MetricsCollector) -> None:
        """Test getting list of metric names."""
        metrics_collector.record_metric("metric1", 1.0)
        metrics_collector.record_metric("metric2", 2.0)
        metrics_collector.record_metric("metric3", 3.0)

        names = metrics_collector.get_metric_names()

        assert set(names) == {"metric1", "metric2", "metric3"}

    def test_get_metric_count_all(self, metrics_collector: MetricsCollector) -> None:
        """Test getting count of all metric readings."""
        metrics_collector.record_metric("metric1", 1.0)
        metrics_collector.record_metric("metric2", 2.0)
        metrics_collector.record_metric("metric2", 3.0)

        count = metrics_collector.get_metric_count()

        assert count == 3

    def test_get_metric_count_specific(self, metrics_collector: MetricsCollector) -> None:
        """Test getting count for specific metric."""
        metrics_collector.record_metric("metric1", 1.0)
        metrics_collector.record_metric("metric2", 2.0)
        metrics_collector.record_metric("metric2", 3.0)

        count = metrics_collector.get_metric_count("metric2")

        assert count == 2

    def test_get_metric_count_nonexistent(self, metrics_collector: MetricsCollector) -> None:
        """Test getting count for nonexistent metric returns 0."""
        count = metrics_collector.get_metric_count("nonexistent")

        assert count == 0


# ============================================================================
# MetricsCollector Persistence Tests
# ============================================================================


class TestMetricsCollectorPersistence:
    """Tests for MetricsCollector persistence functionality."""

    def test_persistence_multiple_collectors(
        self, temp_metrics_dir: Path
    ) -> None:
        """Test metrics persist across collector instances."""
        metrics_path = temp_metrics_dir / "metrics.json"

        # First collector records metric
        collector1 = MetricsCollector(
            metrics_path=metrics_path,
            root_dir=temp_metrics_dir,
        )
        collector1.record_metric("persistent_metric", 42.0)

        # Second collector should load the metric
        collector2 = MetricsCollector(
            metrics_path=metrics_path,
            root_dir=temp_metrics_dir,
        )

        assert "persistent_metric" in collector2.get_metric_names()
        assert collector2.get_metric_count("persistent_metric") == 1

    def test_atomic_write(self, temp_metrics_dir: Path) -> None:
        """Test metrics file uses atomic write pattern."""
        metrics_path = temp_metrics_dir / "metrics.json"
        temp_path = metrics_path.with_suffix(".tmp")

        collector = MetricsCollector(
            metrics_path=metrics_path,
            root_dir=temp_metrics_dir,
        )
        collector.record_metric("test", 1.0)

        # Temp file should be cleaned up
        assert not temp_path.exists()

    def test_metadata_updated(self, metrics_collector: MetricsCollector) -> None:
        """Test metadata is updated when saving metrics."""
        metrics_collector.record_metric("test_metric", 1.0)

        data = json.loads(metrics_collector.metrics_path.read_text())
        metadata = data["metadata"]

        assert metadata["total_metrics"] == 1
        assert metadata["total_readings"] == 1
        assert "last_updated" in metadata

    def test_metadata_multiple_metrics(self, metrics_collector: MetricsCollector) -> None:
        """Test metadata reflects multiple metrics."""
        for i in range(3):
            metrics_collector.record_metric(f"metric{i}", float(i))

        data = json.loads(metrics_collector.metrics_path.read_text())
        metadata = data["metadata"]

        assert metadata["total_metrics"] == 3
        assert metadata["total_readings"] == 3


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_record_zero_value(self, metrics_collector: MetricsCollector) -> None:
        """Test recording zero value."""
        metrics_collector.record_metric("test", 0.0)

        summary = metrics_collector.get_metric_summary("test")
        assert summary.min == 0.0
        assert summary.max == 0.0

    def test_record_negative_value(self, metrics_collector: MetricsCollector) -> None:
        """Test recording negative value."""
        metrics_collector.record_metric("test", -42.0)

        readings = metrics_collector.query_metrics("test")
        assert readings[0].value == -42.0

    def test_record_large_value(self, metrics_collector: MetricsCollector) -> None:
        """Test recording very large value."""
        large_value = 1e15
        metrics_collector.record_metric("test", large_value)

        readings = metrics_collector.query_metrics("test")
        assert readings[0].value == large_value

    def test_window_exactly_at_capacity(self, metrics_collector: MetricsCollector) -> None:
        """Test window at exactly max capacity."""
        small_window = MetricsCollector(
            metrics_path=metrics_collector.metrics_path,
            root_dir=metrics_collector.metrics_path.parent,
            window_size=5,
        )

        # Add exactly 5 readings
        for i in range(5):
            small_window.record_metric("test", float(i))

        assert small_window.get_metric_count("test") == 5

    def test_window_over_capacity(self, metrics_collector: MetricsCollector) -> None:
        """Test window exceeding capacity."""
        small_window = MetricsCollector(
            metrics_path=metrics_collector.metrics_path,
            root_dir=metrics_collector.metrics_path.parent,
            window_size=3,
        )

        # Add more than max_size
        for i in range(10):
            small_window.record_metric("test", float(i))

        # Should only keep 3
        assert small_window.get_metric_count("test") == 3

    def test_query_with_no_labels_filter(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Test query on reading without labels."""
        metrics_collector.record_metric("test", 1.0)  # No labels
        metrics_collector.record_metric(
            "test", 2.0, labels={"key": "value"}
        )

        # Should only return labeled reading
        results = metrics_collector.query_metrics(
            label_filter={"key": "value"}
        )

        assert len(results) == 1
        assert results[0].value == 2.0

    def test_percentiles_with_small_dataset(self, metrics_collector: MetricsCollector) -> None:
        """Test percentiles with very small dataset."""
        metrics_collector.record_metric("test", 10.0)
        metrics_collector.record_metric("test", 20.0)

        summary = metrics_collector.get_metric_summary("test")

        # Should still calculate percentiles
        assert summary.percentile_50 is not None
        assert summary.percentile_95 is not None
        assert summary.percentile_99 is not None

    def test_empty_metadata_and_labels(self, metrics_collector: MetricsCollector) -> None:
        """Test recording with empty metadata and labels."""
        metrics_collector.record_metric(
            "test",
            1.0,
            metadata={},
            labels={},
        )

        readings = metrics_collector.query_metrics("test")
        assert readings[0].metadata == {}
        assert readings[0].labels == {}

    def test_concurrent_metric_names(self, metrics_collector: MetricsCollector) -> None:
        """Test multiple independent metrics."""
        for i in range(5):
            metrics_collector.record_metric(f"metric{i}", float(i))

        names = metrics_collector.get_metric_names()
        assert len(names) == 5

        # Each should have 1 reading
        for name in names:
            assert metrics_collector.get_metric_count(name) == 1
