"""
Autoflow Task Feature Extraction

Extracts features from tasks for ML-based prioritization. Features are
structured as dataclasses with to_dict() methods for easy serialization.

Usage:
    from autoflow.prediction import TaskFeatureExtractor

    extractor = TaskFeatureExtractor()
    features = extractor.extract_task_features(task_data)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class TaskStatus(StrEnum):
    """Status of a task in the workflow."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    NEEDS_CHANGES = "needs_changes"
    BLOCKED = "blocked"


class TaskType(StrEnum):
    """Type of task based on its purpose."""

    IMPLEMENTATION = "implementation"
    INTEGRATION = "integration"
    TEST = "test"
    DOCUMENTATION = "documentation"
    REFACTOR = "refactor"
    OTHER = "other"


@dataclass
class TaskComplexityFeatures:
    """
    Features related to task complexity.

    Attributes:
        description_length: Length of task description in characters
        description_word_count: Number of words in description
        num_files_to_create: Number of files to create
        num_files_to_modify: Number of files to modify
        num_patterns: Number of pattern files to reference
        has_verification: Whether task has verification criteria
        verification_type: Type of verification (command, test, api, e2e)
    """

    description_length: int = 0
    description_word_count: int = 0
    num_files_to_create: int = 0
    num_files_to_modify: int = 0
    num_patterns: int = 0
    has_verification: bool = False
    verification_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "task_description_length": self.description_length,
            "task_description_word_count": self.description_word_count,
            "task_files_to_create": self.num_files_to_create,
            "task_files_to_modify": self.num_files_to_modify,
            "task_patterns": self.num_patterns,
            "task_has_verification": 1 if self.has_verification else 0,
            "task_verification_type_" + str(self.verification_type): 1,
        }


@dataclass
class TaskDependencyFeatures:
    """
    Features related to task dependencies.

    Attributes:
        num_dependencies: Number of tasks this task depends on
        num_dependents: Number of tasks that depend on this task
        is_blocking: Whether this task blocks other tasks
        dependency_depth: Depth in dependency graph (0 = no dependencies)
        has_circular_dependency: Whether circular dependencies detected
    """

    num_dependencies: int = 0
    num_dependents: int = 0
    is_blocking: bool = False
    dependency_depth: int = 0
    has_circular_dependency: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "task_num_dependencies": self.num_dependencies,
            "task_num_dependents": self.num_dependents,
            "task_is_blocking": 1 if self.is_blocking else 0,
            "task_dependency_depth": self.dependency_depth,
            "task_has_circular_dep": 1 if self.has_circular_dependency else 0,
        }


@dataclass
class TaskServiceFeatures:
    """
    Features related to task service assignment.

    Attributes:
        service: Service assigned to task (backend, frontend, etc.)
        role: Role associated with task
        phase_type: Type of phase (implementation, integration)
    """

    service: str = ""
    role: str = ""
    phase_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "task_service_" + str(self.service): 1,
            "task_role_" + str(self.role): 1,
            "task_phase_type_" + str(self.phase_type): 1,
        }


@dataclass
class TaskHistoricalFeatures:
    """
    Features based on historical task completion data.

    Attributes:
        avg_completion_time: Average time to complete similar tasks
        success_rate: Success rate for similar tasks
        retry_count: Average number of retries for similar tasks
        last_completed: Timestamp of last similar task completion
    """

    avg_completion_time: float = 0.0
    success_rate: float = 0.0
    retry_count: int = 0
    last_completed: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ML model consumption."""
        return {
            "task_avg_completion_time": self.avg_completion_time,
            "task_success_rate": self.success_rate,
            "task_retry_count": self.retry_count,
            "task_last_completed": self.last_completed,
        }


@dataclass
class TaskFeatures:
    """
    Unified task feature vector combining all feature types.

    Attributes:
        task_id: Unique identifier for the task
        spec_id: Spec this task belongs to
        phase_id: Phase this task belongs to
        status: Current status of the task
        task_type: Type of task (implementation, integration, etc.)
        complexity: Complexity-related features
        dependencies: Dependency-related features
        service: Service-related features
        historical: Historical performance features
        priority_score: Calculated priority score (higher = more priority)
    """

    task_id: str
    spec_id: str
    phase_id: str
    status: TaskStatus
    task_type: TaskType
    complexity: TaskComplexityFeatures
    dependencies: TaskDependencyFeatures
    service: TaskServiceFeatures
    historical: TaskHistoricalFeatures
    priority_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """
        Flatten all features into a single dictionary for ML consumption.

        Returns:
            Dictionary with all features flattened and prefixed by type
        """
        result: dict[str, Any] = {
            "task_id": self.task_id,
            "spec_id": self.spec_id,
            "phase_id": self.phase_id,
            "task_status_" + str(self.status): 1,
            "task_type_" + str(self.task_type): 1,
            "task_priority_score": self.priority_score,
        }

        result.update(self.complexity.to_dict())
        result.update(self.dependencies.to_dict())
        result.update(self.service.to_dict())
        result.update(self.historical.to_dict())

        return result


class TaskFeatureExtractor:
    """
    Extract features from tasks for ML-based prioritization.

    This class provides methods to extract various types of features
    from task data for predicting optimal task ordering.
    """

    def __init__(self, root_dir: Path | None = None) -> None:
        """
        Initialize the task feature extractor.

        Args:
            root_dir: Root directory of the project. Defaults to current directory.
        """
        self.root_dir = root_dir or Path.cwd()

    def extract_task_features(
        self,
        task_data: dict[str, Any],
        spec_id: str,
        phase_id: str,
        all_tasks: list[dict[str, Any]] | None = None,
    ) -> TaskFeatures:
        """
        Extract features from a single task.

        Args:
            task_data: Dictionary containing task information
            spec_id: ID of the spec this task belongs to
            phase_id: ID of the phase this task belongs to
            all_tasks: List of all tasks for dependency analysis

        Returns:
            TaskFeatures object with extracted features

        Raises:
            ValueError: If task_data is malformed or missing required fields
        """
        if not isinstance(task_data, dict):
            raise ValueError("task_data must be a dictionary")

        # Extract task ID
        task_id = task_data.get("id", "")
        if not task_id:
            raise ValueError("task_data must contain 'id' field")

        # Extract status
        status_str = task_data.get("status", "todo")
        try:
            status = TaskStatus(status_str)
        except ValueError:
            status = TaskStatus.TODO

        # Extract task type from phase or task data
        task_type_str = task_data.get("type", phase_id)
        if "implementation" in task_type_str.lower():
            task_type = TaskType.IMPLEMENTATION
        elif "integration" in task_type_str.lower():
            task_type = TaskType.INTEGRATION
        elif "test" in task_type_str.lower():
            task_type = TaskType.TEST
        elif "documentation" in task_type_str.lower() or "docs" in task_type_str.lower():
            task_type = TaskType.DOCUMENTATION
        elif "refactor" in task_type_str.lower():
            task_type = TaskType.REFACTOR
        else:
            task_type = TaskType.OTHER

        # Extract complexity features
        complexity = self._extract_complexity_features(task_data)

        # Extract dependency features
        if all_tasks is None:
            all_tasks = [task_data]
        dependencies = self._extract_dependency_features(task_data, all_tasks)

        # Extract service features
        service = self._extract_service_features(task_data)

        # Extract historical features (defaults to empty for now)
        historical = self._extract_historical_features(task_data)

        # Calculate initial priority score
        priority_score = self._calculate_priority_score(
            complexity, dependencies, service, historical
        )

        return TaskFeatures(
            task_id=task_id,
            spec_id=spec_id,
            phase_id=phase_id,
            status=status,
            task_type=task_type,
            complexity=complexity,
            dependencies=dependencies,
            service=service,
            historical=historical,
            priority_score=priority_score,
        )

    def _extract_complexity_features(
        self, task_data: dict[str, Any]
    ) -> TaskComplexityFeatures:
        """Extract complexity-related features from task data."""
        description = task_data.get("description", "")
        description_length = len(description)
        description_word_count = len(description.split())

        files_to_create = task_data.get("files_to_create", [])
        num_files_to_create = len(files_to_create) if isinstance(files_to_create, list) else 0

        files_to_modify = task_data.get("files_to_modify", [])
        num_files_to_modify = len(files_to_modify) if isinstance(files_to_modify, list) else 0

        patterns_from = task_data.get("patterns_from", [])
        num_patterns = len(patterns_from) if isinstance(patterns_from, list) else 0

        verification = task_data.get("verification", {})
        has_verification = bool(verification)
        verification_type = verification.get("type", "") if isinstance(verification, dict) else ""

        return TaskComplexityFeatures(
            description_length=description_length,
            description_word_count=description_word_count,
            num_files_to_create=num_files_to_create,
            num_files_to_modify=num_files_to_modify,
            num_patterns=num_patterns,
            has_verification=has_verification,
            verification_type=verification_type,
        )

    def _extract_dependency_features(
        self, task_data: dict[str, Any], all_tasks: list[dict[str, Any]]
    ) -> TaskDependencyFeatures:
        """Extract dependency-related features from task data."""
        task_id = task_data.get("id", "")

        # Count direct dependencies
        depends_on = task_data.get("depends_on", [])
        if isinstance(depends_on, list):
            num_dependencies = len(depends_on)
        else:
            num_dependencies = 0

        # Count dependents (tasks that depend on this one)
        num_dependents = 0
        for other_task in all_tasks:
            if not isinstance(other_task, dict):
                continue
            other_depends_on = other_task.get("depends_on", [])
            if isinstance(other_depends_on, list) and task_id in other_depends_on:
                num_dependents += 1

        is_blocking = num_dependents > 0

        # Calculate dependency depth
        dependency_depth = self._calculate_dependency_depth(task_data, all_tasks)

        # Check for circular dependencies
        has_circular_dependency = self._check_circular_dependencies(task_data, all_tasks)

        return TaskDependencyFeatures(
            num_dependencies=num_dependencies,
            num_dependents=num_dependents,
            is_blocking=is_blocking,
            dependency_depth=dependency_depth,
            has_circular_dependency=has_circular_dependency,
        )

    def _calculate_dependency_depth(
        self, task_data: dict[str, Any], all_tasks: list[dict[str, Any]]
    ) -> int:
        """
        Calculate the depth of a task in the dependency graph.

        Args:
            task_data: Task to analyze
            all_tasks: All tasks in the graph

        Returns:
            Depth (0 = no dependencies, higher = deeper in chain)
        """
        task_id = task_data.get("id", "")
        visited: set[str] = set()

        def depth(current_task_id: str, current_depth: int) -> int:
            if current_task_id in visited:
                return current_depth  # Prevent infinite recursion

            visited.add(current_task_id)

            # Find the current task
            current_task = None
            for task in all_tasks:
                if isinstance(task, dict) and task.get("id") == current_task_id:
                    current_task = task
                    break

            if not current_task:
                return current_depth

            depends_on = current_task.get("depends_on", [])
            if not isinstance(depends_on, list) or not depends_on:
                return current_depth

            # Recursively calculate max depth
            max_depth = current_depth
            for dep_id in depends_on:
                max_depth = max(max_depth, depth(dep_id, current_depth + 1))

            return max_depth

        return depth(task_id, 0)

    def _check_circular_dependencies(
        self, task_data: dict[str, Any], all_tasks: list[dict[str, Any]]
    ) -> bool:
        """
        Check if a task has circular dependencies.

        Args:
            task_data: Task to analyze
            all_tasks: All tasks in the graph

        Returns:
            True if circular dependency detected
        """
        task_id = task_data.get("id", "")
        visited: set[str] = set()

        def check(current_task_id: str) -> bool:
            if current_task_id == task_id and current_task_id in visited:
                return True

            if current_task_id in visited:
                return False

            visited.add(current_task_id)

            # Find the current task
            current_task = None
            for task in all_tasks:
                if isinstance(task, dict) and task.get("id") == current_task_id:
                    current_task = task
                    break

            if not current_task:
                return False

            depends_on = current_task.get("depends_on", [])
            if not isinstance(depends_on, list):
                return False

            for dep_id in depends_on:
                if check(dep_id):
                    return True

            return False

        return check(task_id)

    def _extract_service_features(self, task_data: dict[str, Any]) -> TaskServiceFeatures:
        """Extract service-related features from task data."""
        service = task_data.get("service", "")
        role = task_data.get("role", "")
        phase_type = task_data.get("type", "")

        return TaskServiceFeatures(
            service=service,
            role=role,
            phase_type=phase_type,
        )

    def _extract_historical_features(
        self, task_data: dict[str, Any]
    ) -> TaskHistoricalFeatures:
        """
        Extract historical performance features.

        Note: This is a placeholder for now. Historical data will be
        populated by the TaskHistoryCollector in a later phase.
        """
        return TaskHistoricalFeatures()

    def _calculate_priority_score(
        self,
        complexity: TaskComplexityFeatures,
        dependencies: TaskDependencyFeatures,
        service: TaskServiceFeatures,
        historical: TaskHistoricalFeatures,
    ) -> float:
        """
        Calculate an initial priority score for a task.

        Higher score = higher priority. This is a heuristic that will
        be refined by the ML model.

        Args:
            complexity: Complexity features
            dependencies: Dependency features
            service: Service features
            historical: Historical features

        Returns:
            Priority score (0-100, higher = more priority)
        """
        score = 50.0  # Base score

        # Blocking tasks get higher priority
        if dependencies.is_blocking:
            score += 20.0

        # Tasks with fewer dependencies get higher priority
        score -= dependencies.num_dependencies * 5.0

        # Simpler tasks get slightly higher priority
        complexity_score = (
            complexity.num_files_to_create * 2.0
            + complexity.num_files_to_modify * 1.5
            + complexity.description_length / 100.0
        )
        score -= complexity_score * 0.5

        # Tasks with verification get priority (quality gate)
        if complexity.has_verification:
            score += 5.0

        # Normalize to 0-100 range
        return max(0.0, min(100.0, score))

    def extract_batch_features(
        self, tasks: list[dict[str, Any]], spec_id: str, phase_id: str
    ) -> list[TaskFeatures]:
        """
        Extract features from multiple tasks at once.

        Args:
            tasks: List of task dictionaries
            spec_id: ID of the spec these tasks belong to
            phase_id: ID of the phase these tasks belong to

        Returns:
            List of TaskFeatures objects
        """
        results: list[TaskFeatures] = []

        for task_data in tasks:
            try:
                features = self.extract_task_features(
                    task_data, spec_id, phase_id, all_tasks=tasks
                )
                results.append(features)
            except (ValueError, KeyError):
                # Skip tasks with missing required fields
                continue

        return results
