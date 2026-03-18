"""
Autoflow Task History Collector

Collects historical task completion data by aggregating task features
with completion outcomes from past implementations. This data is used
to train ML models for task prioritization.

Usage:
    from autoflow.prediction import TaskHistoryCollector

    collector = TaskHistoryCollector()
    task_data = collector.collect_task_history()
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from autoflow.prediction.task_feature_extractor import (
    TaskFeatureExtractor,
    TaskFeatures,
)


class TaskOutcome(StrEnum):
    """
    Task completion outcome labels for training data.

    These represent the actual outcome of a task implementation:
        COMPLETED: Task completed successfully (status: done)
        NEEDS_WORK: Task required fixes/retries (status: needs_changes)
        BLOCKED: Task was blocked or failed (status: blocked)
        IN_PROGRESS: Task is currently in progress (status: in_progress)
        PENDING: Task is pending completion (status: todo, in_review)
    """

    COMPLETED = "completed"
    NEEDS_WORK = "needs_work"
    BLOCKED = "blocked"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"


@dataclass
class TaskPrioritySample:
    """
    A single training sample with task features and completion outcome.

    Attributes:
        task_id: Unique identifier for the task
        spec_id: Spec this task belongs to
        phase_id: Phase this task belongs to
        features: TaskFeatures with all extracted task features
        outcome: Actual task completion outcome
        priority_score: Historical priority score (if available)
        completion_time_seconds: Time taken to complete task (if available)
    """

    task_id: str
    spec_id: str
    phase_id: str
    features: TaskFeatures
    outcome: TaskOutcome
    priority_score: float | None = None
    completion_time_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "task_id": self.task_id,
            "spec_id": self.spec_id,
            "phase_id": self.phase_id,
            "features": self.features.to_dict(),
            "outcome": self.outcome.value,
            "priority_score": self.priority_score,
            "completion_time_seconds": self.completion_time_seconds,
        }


class TaskHistoryCollector:
    """
    Collects historical task completion data from past implementations.

    This class aggregates task features with outcomes by:
    1. Iterating through .auto-claude/specs/ to find implementation_plan.json
    2. Extracting features from tasks using TaskFeatureExtractor
    3. Mapping task status to completion outcomes
    4. Returning training data as feature-label pairs
    """

    def __init__(self, root_dir: Path | None = None) -> None:
        """
        Initialize the task history collector.

        Args:
            root_dir: Root directory of the project. Defaults to current directory.
        """
        self.root_dir = root_dir or Path.cwd()
        self.extractor = TaskFeatureExtractor(root_dir=self.root_dir)

    def collect_task_history(
        self,
        specs_dir: Path | None = None,
    ) -> list[TaskPrioritySample]:
        """
        Collect task completion history from all specs.

        Iterates through spec directories, extracts features for each task,
        and pairs them with the actual completion outcome.

        Args:
            specs_dir: Path to directory containing spec directories.
                     Defaults to .auto-claude/specs/

        Returns:
            List of TaskPrioritySample objects with features and outcomes

        Raises:
            FileNotFoundError: If specs_dir doesn't exist
        """
        if specs_dir is None:
            specs_dir = self.root_dir / ".auto-claude" / "specs"

        if not specs_dir.exists():
            raise FileNotFoundError(f"Specs directory not found: {specs_dir}")

        # Find all implementation_plan.json files
        plan_files = list(specs_dir.glob("*/implementation_plan.json"))

        if not plan_files:
            return []

        # Collect task samples from all specs
        task_samples: list[TaskPrioritySample] = []

        for plan_file in plan_files:
            try:
                spec_samples = self._collect_from_plan(plan_file)
                task_samples.extend(spec_samples)
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                # Skip specs with missing or malformed data
                continue

        return task_samples

    def _collect_from_plan(
        self, plan_file: Path
    ) -> list[TaskPrioritySample]:
        """
        Collect task samples from a single implementation plan.

        Args:
            plan_file: Path to implementation_plan.json

        Returns:
            List of TaskPrioritySample objects

        Raises:
            json.JSONDecodeError: If plan file is malformed
            KeyError: If required fields are missing
        """
        plan_data = json.loads(plan_file.read_text(encoding="utf-8"))

        # Extract spec_id from directory name
        spec_id = plan_file.parent.name

        # Get phases from the plan
        phases = plan_data.get("phases", [])
        if not phases:
            return []

        task_samples: list[TaskPrioritySample] = []

        # Collect all tasks from all phases for dependency analysis
        all_tasks: list[dict[str, Any]] = []
        for phase in phases:
            subtasks = phase.get("subtasks", [])
            all_tasks.extend(subtasks)

        if not all_tasks:
            return []

        # Process each phase
        for phase in phases:
            phase_id = phase.get("id", "")
            phase_type = phase.get("type", "")
            subtasks = phase.get("subtasks", [])

            # Extract features for each task in this phase
            for task_data in subtasks:
                try:
                    sample = self._create_task_sample(
                        task_data, spec_id, phase_id, phase_type, all_tasks
                    )
                    if sample:
                        task_samples.append(sample)
                except (ValueError, KeyError):
                    # Skip tasks with missing required fields
                    continue

        return task_samples

    def _create_task_sample(
        self,
        task_data: dict[str, Any],
        spec_id: str,
        phase_id: str,
        phase_type: str,
        all_tasks: list[dict[str, Any]],
    ) -> TaskPrioritySample | None:
        """
        Create a task training sample from task data.

        Args:
            task_data: Task dictionary from implementation plan
            spec_id: ID of the spec
            phase_id: ID of the phase
            phase_type: Type of phase (implementation, integration)
            all_tasks: All tasks for dependency analysis

        Returns:
            TaskPrioritySample object, or None if creation fails
        """
        task_id = task_data.get("id", "")
        if not task_id:
            return None

        # Add phase type to task data for feature extraction
        task_data_with_phase = {**task_data, "type": phase_type}

        # Extract task features
        try:
            features = self.extractor.extract_task_features(
                task_data_with_phase, spec_id, phase_id, all_tasks=all_tasks
            )
        except (ValueError, KeyError):
            return None

        # Determine task outcome from status
        status = task_data.get("status", "pending")
        outcome = self._map_status_to_outcome(status)

        # Get priority score from features (if calculated)
        priority_score = features.priority_score if features else None

        # Completion time is not currently available in implementation_plan.json
        # This will be added in a future subtask when integrating with VelocityTracker
        completion_time = None

        return TaskPrioritySample(
            task_id=task_id,
            spec_id=spec_id,
            phase_id=phase_id,
            features=features,
            outcome=outcome,
            priority_score=priority_score,
            completion_time_seconds=completion_time,
        )

    def _map_status_to_outcome(self, status: str) -> TaskOutcome:
        """
        Map task status to completion outcome.

        Args:
            status: Task status string

        Returns:
            TaskOutcome enum value
        """
        status_lower = status.lower()

        if status_lower == "done" or status_lower == "completed":
            return TaskOutcome.COMPLETED
        elif status_lower == "needs_changes":
            return TaskOutcome.NEEDS_WORK
        elif status_lower == "blocked" or status_lower == "failed":
            return TaskOutcome.BLOCKED
        elif status_lower == "in_progress":
            return TaskOutcome.IN_PROGRESS
        else:
            # Default to pending for todo, in_review, or unknown statuses
            return TaskOutcome.PENDING

    def collect_task_history_for_model(
        self,
        specs_dir: Path | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Collect task history formatted for ML model training.

        Returns feature vectors and outcome labels as separate lists suitable
        for sklearn's fit() method.

        Args:
            specs_dir: Path to directory containing spec directories

        Returns:
            Tuple of (feature_dicts, outcome_labels) where:
                - feature_dicts: List of dictionaries with flattened features
                - outcome_labels: List of outcome strings
        """
        samples = self.collect_task_history(specs_dir)

        feature_dicts = [sample.features.to_dict() for sample in samples]
        outcome_labels = [sample.outcome.value for sample in samples]

        return feature_dicts, outcome_labels

    def get_completed_tasks(
        self,
        specs_dir: Path | None = None,
    ) -> list[TaskPrioritySample]:
        """
        Get only completed tasks from history.

        Filters task history to return only tasks that have been
        successfully completed. Useful for training on positive examples.

        Args:
            specs_dir: Path to directory containing spec directories

        Returns:
            List of TaskPrioritySample objects with COMPLETED outcome
        """
        all_samples = self.collect_task_history(specs_dir)
        return [
            sample
            for sample in all_samples
            if sample.outcome == TaskOutcome.COMPLETED
        ]

    def get_task_statistics(
        self,
        specs_dir: Path | None = None,
    ) -> dict[str, Any]:
        """
        Calculate statistics about task completion history.

        Args:
            specs_dir: Path to directory containing spec directories

        Returns:
            Dictionary with task completion statistics
        """
        samples = self.collect_task_history(specs_dir)

        if not samples:
            return {
                "total_tasks": 0,
                "completed": 0,
                "needs_work": 0,
                "blocked": 0,
                "in_progress": 0,
                "pending": 0,
                "completion_rate": 0.0,
            }

        outcome_counts = {
            TaskOutcome.COMPLETED: 0,
            TaskOutcome.NEEDS_WORK: 0,
            TaskOutcome.BLOCKED: 0,
            TaskOutcome.IN_PROGRESS: 0,
            TaskOutcome.PENDING: 0,
        }

        for sample in samples:
            outcome_counts[sample.outcome] += 1

        total = len(samples)
        completed_tasks = (
            outcome_counts[TaskOutcome.COMPLETED] + outcome_counts[TaskOutcome.NEEDS_WORK]
        )
        completion_rate = completed_tasks / total if total > 0 else 0.0

        return {
            "total_tasks": total,
            "completed": outcome_counts[TaskOutcome.COMPLETED],
            "needs_work": outcome_counts[TaskOutcome.NEEDS_WORK],
            "blocked": outcome_counts[TaskOutcome.BLOCKED],
            "in_progress": outcome_counts[TaskOutcome.IN_PROGRESS],
            "pending": outcome_counts[TaskOutcome.PENDING],
            "completion_rate": completion_rate,
        }
