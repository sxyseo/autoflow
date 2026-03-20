"""Unit Tests for Task History Collector

Tests the TaskHistoryCollector class for collecting historical task
completion data with VelocityTracker integration for cycle time data.

These tests follow the patterns from test_analytics_velocity.py for consistency.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from autoflow.analytics.velocity import (
    TaskRecord,
    TaskStatus,
    VelocityTracker,
)
from autoflow.prediction.task_history_collector import (
    TaskHistoryCollector,
    TaskOutcome,
    TaskPrioritySample,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_specs_dir(tmp_path: Path) -> Path:
    """Create a temporary specs directory with test data."""
    specs_dir = tmp_path / ".auto-claude" / "specs"
    specs_dir.mkdir(parents=True)

    # Create a test spec directory with implementation plan
    test_spec_dir = specs_dir / "test-spec-1"
    test_spec_dir.mkdir()

    # Create implementation_plan.json with sample tasks
    plan_data = {
        "phases": [
            {
                "id": "phase-1",
                "type": "implementation",
                "subtasks": [
                    {
                        "id": "task-1",
                        "title": "First task",
                        "description": "Test task one",
                        "status": "done",
                        "type": "feature",
                        "complexity": 3,
                        "dependencies": [],
                    },
                    {
                        "id": "task-2",
                        "title": "Second task",
                        "description": "Test task two",
                        "status": "needs_changes",
                        "type": "bug",
                        "complexity": 2,
                        "dependencies": ["task-1"],
                    },
                    {
                        "id": "task-3",
                        "title": "Third task",
                        "description": "Test task three",
                        "status": "in_progress",
                        "type": "feature",
                        "complexity": 5,
                        "dependencies": [],
                    },
                ]
            },
            {
                "id": "phase-2",
                "type": "integration",
                "subtasks": [
                    {
                        "id": "task-4",
                        "title": "Fourth task",
                        "description": "Test task four",
                        "status": "todo",
                        "type": "testing",
                        "complexity": 1,
                        "dependencies": ["task-1"],
                    },
                ]
            },
        ]
    }

    plan_file = test_spec_dir / "implementation_plan.json"
    plan_file.write_text(json.dumps(plan_data), encoding="utf-8")

    return specs_dir


@pytest.fixture
def velocity_tracker() -> VelocityTracker:
    """Create a VelocityTracker instance with sample data."""
    tracker = VelocityTracker(window_size=50)

    # Add some sample tasks with cycle times
    now = datetime.now()

    # Task-1: Completed with 2 hour cycle time
    tracker.record_task_creation("task-1", task_type="feature", complexity=3, created_at=now - timedelta(hours=5))
    tracker.record_task_start("task-1", started_at=now - timedelta(hours=4))
    tracker.record_task_completion("task-1", completed_at=now - timedelta(hours=2))

    # Task-2: Completed with 1 hour cycle time
    tracker.record_task_creation("task-2", task_type="bug", complexity=2, created_at=now - timedelta(hours=4))
    tracker.record_task_start("task-2", started_at=now - timedelta(hours=3))
    tracker.record_task_completion("task-2", completed_at=now - timedelta(hours=2))

    # Task-3: In progress, no cycle time yet
    tracker.record_task_creation("task-3", task_type="feature", complexity=5, created_at=now - timedelta(hours=2))
    tracker.record_task_start("task-3", started_at=now - timedelta(hours=1))

    return tracker


@pytest.fixture
def task_history_collector(temp_specs_dir: Path) -> TaskHistoryCollector:
    """Create a TaskHistoryCollector instance without VelocityTracker."""
    return TaskHistoryCollector(root_dir=temp_specs_dir.parent.parent)


@pytest.fixture
def collector_with_velocity(
    temp_specs_dir: Path, velocity_tracker: VelocityTracker
) -> TaskHistoryCollector:
    """Create a TaskHistoryCollector instance with VelocityTracker."""
    return TaskHistoryCollector(
        root_dir=temp_specs_dir.parent.parent,
        velocity_tracker=velocity_tracker,
    )


# ============================================================================
# Basic Functionality Tests
# ============================================================================


class TestTaskHistoryCollectorInit:
    """Tests for TaskHistoryCollector initialization."""

    def test_init_without_velocity_tracker(self, temp_specs_dir: Path) -> None:
        """Test initialization without VelocityTracker."""
        collector = TaskHistoryCollector(root_dir=temp_specs_dir.parent.parent)
        assert collector.velocity_tracker is None
        assert collector.root_dir == temp_specs_dir.parent.parent

    def test_init_with_velocity_tracker(
        self, temp_specs_dir: Path, velocity_tracker: VelocityTracker
    ) -> None:
        """Test initialization with VelocityTracker."""
        collector = TaskHistoryCollector(
            root_dir=temp_specs_dir.parent.parent,
            velocity_tracker=velocity_tracker,
        )
        assert collector.velocity_tracker is velocity_tracker
        assert collector.root_dir == temp_specs_dir.parent.parent


class TestTaskOutcomeEnum:
    """Tests for TaskOutcome enum."""

    def test_task_outcome_values(self) -> None:
        """Test TaskOutcome enum values."""
        assert TaskOutcome.COMPLETED.value == "completed"
        assert TaskOutcome.NEEDS_WORK.value == "needs_work"
        assert TaskOutcome.BLOCKED.value == "blocked"
        assert TaskOutcome.IN_PROGRESS.value == "in_progress"
        assert TaskOutcome.PENDING.value == "pending"

    def test_task_outcome_is_string(self) -> None:
        """Test that TaskOutcome values are strings."""
        assert isinstance(TaskOutcome.COMPLETED.value, str)


class TestTaskPrioritySample:
    """Tests for TaskPrioritySample dataclass."""

    def test_task_priority_sample_creation(self) -> None:
        """Test creating a TaskPrioritySample."""
        from autoflow.prediction.task_feature_extractor import (
            TaskComplexityFeatures,
            TaskDependencyFeatures,
            TaskFeatures,
            TaskHistoricalFeatures,
            TaskServiceFeatures,
            TaskStatus,
            TaskType,
        )

        features = TaskFeatures(
            task_id="test-1",
            spec_id="spec-1",
            phase_id="phase-1",
            status=TaskStatus.DONE,
            task_type=TaskType.IMPLEMENTATION,
            complexity=TaskComplexityFeatures(
                description_length=10,
                description_word_count=2,
            ),
            dependencies=TaskDependencyFeatures(
                num_dependencies=0,
                is_blocking=False,
            ),
            service=TaskServiceFeatures(
                service="backend",
            ),
            historical=TaskHistoricalFeatures(),
            priority_score=0.8,
        )

        sample = TaskPrioritySample(
            task_id="test-1",
            spec_id="spec-1",
            phase_id="phase-1",
            features=features,
            outcome=TaskOutcome.COMPLETED,
            priority_score=0.8,
            completion_time_seconds=7200.0,
        )

        assert sample.task_id == "test-1"
        assert sample.spec_id == "spec-1"
        assert sample.phase_id == "phase-1"
        assert sample.outcome == TaskOutcome.COMPLETED
        assert sample.priority_score == 0.8
        assert sample.completion_time_seconds == 7200.0

    def test_task_priority_sample_to_dict(self) -> None:
        """Test converting TaskPrioritySample to dictionary."""
        from autoflow.prediction.task_feature_extractor import (
            TaskComplexityFeatures,
            TaskDependencyFeatures,
            TaskFeatures,
            TaskHistoricalFeatures,
            TaskServiceFeatures,
            TaskStatus,
            TaskType,
        )

        features = TaskFeatures(
            task_id="test-1",
            spec_id="spec-1",
            phase_id="phase-1",
            status=TaskStatus.DONE,
            task_type=TaskType.IMPLEMENTATION,
            complexity=TaskComplexityFeatures(
                description_length=10,
                description_word_count=2,
            ),
            dependencies=TaskDependencyFeatures(
                num_dependencies=0,
                is_blocking=False,
            ),
            service=TaskServiceFeatures(
                service="backend",
            ),
            historical=TaskHistoricalFeatures(),
            priority_score=0.8,
        )

        sample = TaskPrioritySample(
            task_id="test-1",
            spec_id="spec-1",
            phase_id="phase-1",
            features=features,
            outcome=TaskOutcome.COMPLETED,
            priority_score=0.8,
            completion_time_seconds=7200.0,
        )

        result = sample.to_dict()

        assert isinstance(result, dict)
        assert result["task_id"] == "test-1"
        assert result["spec_id"] == "spec-1"
        assert result["phase_id"] == "phase-1"
        assert result["outcome"] == "completed"
        assert result["priority_score"] == 0.8
        assert result["completion_time_seconds"] == 7200.0
        assert isinstance(result["features"], dict)


# ============================================================================
# VelocityTracker Integration Tests
# ============================================================================


class TestVelocityTrackerIntegration:
    """Tests for VelocityTracker integration."""

    def test_collect_with_velocity_tracker_populates_cycle_time(
        self, collector_with_velocity: TaskHistoryCollector, temp_specs_dir: Path
    ) -> None:
        """Test that cycle time is populated from VelocityTracker."""
        samples = collector_with_velocity.collect_task_history(specs_dir=temp_specs_dir)

        # Find task-1 which should have cycle time
        task_1_sample = next((s for s in samples if s.task_id == "task-1"), None)
        assert task_1_sample is not None
        assert task_1_sample.completion_time_seconds is not None
        # task-1 has 2 hour cycle time = 7200 seconds
        assert task_1_sample.completion_time_seconds == 7200.0

    def test_collect_without_velocity_tracker_has_no_cycle_time(
        self, task_history_collector: TaskHistoryCollector, temp_specs_dir: Path
    ) -> None:
        """Test that cycle time is None without VelocityTracker."""
        samples = task_history_collector.collect_task_history(specs_dir=temp_specs_dir)

        # All samples should have None for completion_time
        for sample in samples:
            assert sample.completion_time_seconds is None

    def test_velocity_tracker_get_task_is_called(
        self, collector_with_velocity: TaskHistoryCollector, temp_specs_dir: Path
    ) -> None:
        """Test that VelocityTracker.get_task is called for each task."""
        samples = collector_with_velocity.collect_task_history(specs_dir=temp_specs_dir)

        # Should have collected 4 tasks
        assert len(samples) == 4

        # task-1 and task-2 should have cycle times
        task_1 = next((s for s in samples if s.task_id == "task-1"), None)
        task_2 = next((s for s in samples if s.task_id == "task-2"), None)
        task_3 = next((s for s in samples if s.task_id == "task-3"), None)
        task_4 = next((s for s in samples if s.task_id == "task-4"), None)

        assert task_1 is not None
        assert task_2 is not None
        assert task_3 is not None
        assert task_4 is not None

        # task-1 and task-2 should have cycle times from VelocityTracker
        assert task_1.completion_time_seconds is not None
        assert task_2.completion_time_seconds is not None

        # task-3 is in progress, should have no cycle time
        assert task_3.completion_time_seconds is None

        # task-4 is not in VelocityTracker, should have no cycle time
        assert task_4.completion_time_seconds is None

    def test_collect_task_history_with_empty_specs_dir(
        self, task_history_collector: TaskHistoryCollector, tmp_path: Path
    ) -> None:
        """Test collecting from empty specs directory."""
        empty_dir = tmp_path / "empty_specs"
        empty_dir.mkdir()

        samples = task_history_collector.collect_task_history(specs_dir=empty_dir)
        assert samples == []


# ============================================================================
# Status Mapping Tests
# ============================================================================


class TestStatusMapping:
    """Tests for task status to outcome mapping."""

    def test_map_done_to_completed(self, task_history_collector: TaskHistoryCollector) -> None:
        """Test mapping 'done' status to COMPLETED outcome."""
        outcome = task_history_collector._map_status_to_outcome("done")
        assert outcome == TaskOutcome.COMPLETED

    def test_map_completed_to_completed(self, task_history_collector: TaskHistoryCollector) -> None:
        """Test mapping 'completed' status to COMPLETED outcome."""
        outcome = task_history_collector._map_status_to_outcome("completed")
        assert outcome == TaskOutcome.COMPLETED

    def test_map_needs_changes_to_needs_work(
        self, task_history_collector: TaskHistoryCollector
    ) -> None:
        """Test mapping 'needs_changes' status to NEEDS_WORK outcome."""
        outcome = task_history_collector._map_status_to_outcome("needs_changes")
        assert outcome == TaskOutcome.NEEDS_WORK

    def test_map_blocked_to_blocked(self, task_history_collector: TaskHistoryCollector) -> None:
        """Test mapping 'blocked' status to BLOCKED outcome."""
        outcome = task_history_collector._map_status_to_outcome("blocked")
        assert outcome == TaskOutcome.BLOCKED

    def test_map_failed_to_blocked(self, task_history_collector: TaskHistoryCollector) -> None:
        """Test mapping 'failed' status to BLOCKED outcome."""
        outcome = task_history_collector._map_status_to_outcome("failed")
        assert outcome == TaskOutcome.BLOCKED

    def test_map_in_progress_to_in_progress(
        self, task_history_collector: TaskHistoryCollector
    ) -> None:
        """Test mapping 'in_progress' status to IN_PROGRESS outcome."""
        outcome = task_history_collector._map_status_to_outcome("in_progress")
        assert outcome == TaskOutcome.IN_PROGRESS

    def test_map_todo_to_pending(self, task_history_collector: TaskHistoryCollector) -> None:
        """Test mapping 'todo' status to PENDING outcome."""
        outcome = task_history_collector._map_status_to_outcome("todo")
        assert outcome == TaskOutcome.PENDING

    def test_map_in_review_to_pending(self, task_history_collector: TaskHistoryCollector) -> None:
        """Test mapping 'in_review' status to PENDING outcome."""
        outcome = task_history_collector._map_status_to_outcome("in_review")
        assert outcome == TaskOutcome.PENDING

    def test_map_unknown_to_pending(self, task_history_collector: TaskHistoryCollector) -> None:
        """Test mapping unknown status to PENDING outcome."""
        outcome = task_history_collector._map_status_to_outcome("unknown_status")
        assert outcome == TaskOutcome.PENDING


# ============================================================================
# Data Collection Tests
# ============================================================================


class TestDataCollection:
    """Tests for data collection functionality."""

    def test_collect_task_history_returns_samples(
        self, task_history_collector: TaskHistoryCollector, temp_specs_dir: Path
    ) -> None:
        """Test that collect_task_history returns TaskPrioritySample objects."""
        samples = task_history_collector.collect_task_history(specs_dir=temp_specs_dir)

        assert isinstance(samples, list)
        assert len(samples) > 0

        for sample in samples:
            assert isinstance(sample, TaskPrioritySample)

    def test_collect_task_history_correct_outcomes(
        self, task_history_collector: TaskHistoryCollector, temp_specs_dir: Path
    ) -> None:
        """Test that task outcomes are correctly mapped from status."""
        samples = task_history_collector.collect_task_history(specs_dir=temp_specs_dir)

        # Find tasks by ID
        task_1 = next((s for s in samples if s.task_id == "task-1"), None)
        task_2 = next((s for s in samples if s.task_id == "task-2"), None)
        task_3 = next((s for s in samples if s.task_id == "task-3"), None)
        task_4 = next((s for s in samples if s.task_id == "task-4"), None)

        # Check outcomes
        assert task_1 is not None
        assert task_1.outcome == TaskOutcome.COMPLETED  # status: done

        assert task_2 is not None
        assert task_2.outcome == TaskOutcome.NEEDS_WORK  # status: needs_changes

        assert task_3 is not None
        assert task_3.outcome == TaskOutcome.IN_PROGRESS  # status: in_progress

        assert task_4 is not None
        assert task_4.outcome == TaskOutcome.PENDING  # status: todo

    def test_collect_task_history_for_model(
        self, task_history_collector: TaskHistoryCollector, temp_specs_dir: Path
    ) -> None:
        """Test collecting history formatted for ML model."""
        feature_dicts, outcome_labels = task_history_collector.collect_task_history_for_model(
            specs_dir=temp_specs_dir
        )

        assert isinstance(feature_dicts, list)
        assert isinstance(outcome_labels, list)
        assert len(feature_dicts) == len(outcome_labels)

        # All feature dicts should be dictionaries
        for feature_dict in feature_dicts:
            assert isinstance(feature_dict, dict)

        # All outcome labels should be strings
        for label in outcome_labels:
            assert isinstance(label, str)

    def test_get_completed_tasks(
        self, task_history_collector: TaskHistoryCollector, temp_specs_dir: Path
    ) -> None:
        """Test getting only completed tasks."""
        completed = task_history_collector.get_completed_tasks(specs_dir=temp_specs_dir)

        assert isinstance(completed, list)

        # All should be COMPLETED outcome
        for sample in completed:
            assert sample.outcome == TaskOutcome.COMPLETED

    def test_get_task_statistics(
        self, task_history_collector: TaskHistoryCollector, temp_specs_dir: Path
    ) -> None:
        """Test getting task statistics."""
        stats = task_history_collector.get_task_statistics(specs_dir=temp_specs_dir)

        assert isinstance(stats, dict)
        assert "total_tasks" in stats
        assert "completed" in stats
        assert "needs_work" in stats
        assert "blocked" in stats
        assert "in_progress" in stats
        assert "pending" in stats
        assert "completion_rate" in stats

        # Check values
        assert stats["total_tasks"] == 4
        assert stats["completed"] == 1  # task-1
        assert stats["needs_work"] == 1  # task-2
        assert stats["in_progress"] == 1  # task-3
        assert stats["pending"] == 1  # task-4
        assert stats["completion_rate"] == 0.5  # 2 completed out of 4

    def test_get_task_statistics_empty(
        self, task_history_collector: TaskHistoryCollector, tmp_path: Path
    ) -> None:
        """Test getting statistics from empty specs directory."""
        empty_dir = tmp_path / "empty_specs"
        empty_dir.mkdir()

        stats = task_history_collector.get_task_statistics(specs_dir=empty_dir)

        assert stats["total_tasks"] == 0
        assert stats["completion_rate"] == 0.0


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_collect_with_nonexistent_specs_dir(
        self, task_history_collector: TaskHistoryCollector
    ) -> None:
        """Test collecting with non-existent specs directory."""
        with pytest.raises(FileNotFoundError):
            task_history_collector.collect_task_history(specs_dir=Path("/nonexistent/path"))

    def test_collect_with_malformed_plan_file(
        self, task_history_collector: TaskHistoryCollector, tmp_path: Path
    ) -> None:
        """Test collecting with malformed implementation_plan.json."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()

        spec_dir = specs_dir / "bad-spec"
        spec_dir.mkdir()

        # Create malformed JSON
        plan_file = spec_dir / "implementation_plan.json"
        plan_file.write_text("{invalid json", encoding="utf-8")

        # Should skip malformed file and return empty list
        samples = task_history_collector.collect_task_history(specs_dir=specs_dir)
        assert samples == []

    def test_collect_with_missing_required_fields(
        self, task_history_collector: TaskHistoryCollector, tmp_path: Path
    ) -> None:
        """Test collecting with missing required fields."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()

        spec_dir = specs_dir / "incomplete-spec"
        spec_dir.mkdir()

        # Create plan with missing fields
        plan_data = {"phases": [{"id": "phase-1"}]}  # No subtasks
        plan_file = spec_dir / "implementation_plan.json"
        plan_file.write_text(json.dumps(plan_data), encoding="utf-8")

        # Should handle gracefully
        samples = task_history_collector.collect_task_history(specs_dir=specs_dir)
        assert samples == []
