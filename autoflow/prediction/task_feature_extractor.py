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
from collections import defaultdict
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

    def dependency_analysis(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Perform comprehensive dependency graph analysis for task ordering.

        Analyzes the dependency structure of tasks to determine optimal execution
        order, identify critical paths, blocking tasks, and parallel execution
        opportunities.

        Args:
            tasks: List of task dictionaries with 'id' and 'depends_on' fields

        Returns:
            Dictionary containing:
                - execution_order: List of task IDs in topological order
                - critical_path: List of task IDs forming the longest dependency chain
                - blocking_tasks: List of task IDs that block other tasks
                - parallel_safe: List of task IDs that can run in parallel
                - levels: Dictionary mapping task IDs to their dependency depth
                - cycles: List of detected circular dependencies (if any)

        Raises:
            ValueError: If tasks list is empty or malformed

        Example:
            >>> extractor = TaskFeatureExtractor()
            >>> tasks = [
            ...     {"id": "task-1", "depends_on": []},
            ...     {"id": "task-2", "depends_on": ["task-1"]},
            ...     {"id": "task-3", "depends_on": ["task-1"]},
            ... ]
            >>> analysis = extractor.dependency_analysis(tasks)
            >>> print(analysis["execution_order"])
            ['task-1', 'task-2', 'task-3']
        """
        if not tasks:
            raise ValueError("Tasks list cannot be empty")

        # Build dependency graph
        graph = self._build_dependency_graph(tasks)
        reverse_graph = self._build_reverse_dependency_graph(tasks)

        # Detect circular dependencies
        cycles = self._detect_all_cycles(graph)

        # Calculate execution order using topological sort
        execution_order = self._topological_sort(graph, reverse_graph)

        # Calculate dependency levels (depth)
        levels = self._calculate_dependency_levels(graph)

        # Find critical path (longest chain)
        critical_path = self._find_critical_path(graph, levels)

        # Find blocking tasks (tasks that others depend on)
        blocking_tasks = list(reverse_graph.keys())

        # Find parallel-safe tasks (tasks at same level that don't depend on each other)
        parallel_safe = self._find_parallel_safe_tasks(graph, levels)

        return {
            "execution_order": execution_order,
            "critical_path": critical_path,
            "blocking_tasks": blocking_tasks,
            "parallel_safe": parallel_safe,
            "levels": levels,
            "cycles": cycles,
        }

    def _build_dependency_graph(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, set[str]]:
        """
        Build a dependency graph mapping tasks to their dependencies.

        Args:
            tasks: List of task dictionaries

        Returns:
            Dictionary mapping task IDs to sets of task IDs they depend on
        """
        graph: dict[str, set[str]] = defaultdict(set)

        for task in tasks:
            if not isinstance(task, dict):
                continue

            task_id = task.get("id", "")
            if not task_id:
                continue

            depends_on = task.get("depends_on", [])
            if isinstance(depends_on, list):
                graph[task_id] = set(depends_on)
            else:
                graph[task_id] = set()

        return dict(graph)

    def _build_reverse_dependency_graph(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, set[str]]:
        """
        Build a reverse dependency graph mapping tasks to their dependents.

        Args:
            tasks: List of task dictionaries

        Returns:
            Dictionary mapping task IDs to sets of task IDs that depend on them
        """
        graph: dict[str, set[str]] = defaultdict(set)

        for task in tasks:
            if not isinstance(task, dict):
                continue

            task_id = task.get("id", "")
            if not task_id:
                continue

            depends_on = task.get("depends_on", [])
            if isinstance(depends_on, list):
                for dep_id in depends_on:
                    graph[dep_id].add(task_id)

        return dict(graph)

    def _topological_sort(
        self,
        graph: dict[str, set[str]],
        reverse_graph: dict[str, set[str]],
    ) -> list[str]:
        """
        Perform topological sort using Kahn's algorithm.

        Args:
            graph: Dependency graph (task -> dependencies)
            reverse_graph: Reverse dependency graph (task -> dependents)

        Returns:
            List of task IDs in topological order
        """
        # Calculate in-degrees
        in_degree: dict[str, int] = {
            task_id: len(deps) for task_id, deps in graph.items()
        }

        # Add tasks with no dependencies to in_degree
        all_task_ids = set(graph.keys()) | set(
            dep_id for deps in graph.values() for dep_id in deps
        )
        for task_id in all_task_ids:
            if task_id not in in_degree:
                in_degree[task_id] = 0

        # Start with tasks that have no dependencies
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        queue.sort()  # Sort for deterministic ordering
        result: list[str] = []

        while queue:
            task_id = queue.pop(0)
            result.append(task_id)

            # Reduce in-degree for dependents
            for dependent in reverse_graph.get(task_id, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
                        queue.sort()  # Maintain deterministic ordering

        return result

    def _calculate_dependency_levels(
        self, graph: dict[str, set[str]]
    ) -> dict[str, int]:
        """
        Calculate the dependency level (depth) for each task.

        Args:
            graph: Dependency graph (task -> dependencies)

        Returns:
            Dictionary mapping task IDs to their dependency level
        """
        levels: dict[str, int] = {}

        def calculate_level(task_id: str, visited: set[str]) -> int:
            """Recursively calculate the level of a task."""
            if task_id in levels:
                return levels[task_id]

            if task_id in visited:
                # Circular dependency - assign a high level
                return 999

            visited.add(task_id)

            dependencies = graph.get(task_id, set())
            if not dependencies:
                levels[task_id] = 0
            else:
                max_dep_level = 0
                for dep_id in dependencies:
                    dep_level = calculate_level(dep_id, visited.copy())
                    max_dep_level = max(max_dep_level, dep_level)
                levels[task_id] = max_dep_level + 1

            return levels[task_id]

        # Calculate levels for all tasks
        all_task_ids = set(graph.keys()) | set(
            dep_id for deps in graph.values() for dep_id in deps
        )

        for task_id in all_task_ids:
            if task_id not in levels:
                calculate_level(task_id, set())

        return levels

    def _find_critical_path(
        self, graph: dict[str, set[str]], levels: dict[str, int]
    ) -> list[str]:
        """
        Find the critical path (longest dependency chain) in the graph.

        Args:
            graph: Dependency graph (task -> dependencies)
            levels: Dependency levels for each task

        Returns:
            List of task IDs forming the critical path
        """
        if not levels:
            return []

        # Find the task with the maximum level
        max_level = max(levels.values())
        max_level_tasks = [task_id for task_id, level in levels.items() if level == max_level]

        if not max_level_tasks:
            return []

        # Build the critical path by following dependencies backward
        critical_path: list[str] = []
        current_task = max_level_tasks[0]

        while current_task:
            critical_path.append(current_task)

            # Find the dependency with the highest level
            dependencies = graph.get(current_task, set())
            if not dependencies:
                break

            next_task = max(dependencies, key=lambda d: levels.get(d, 0))
            if levels.get(next_task, 0) >= levels.get(current_task, 0):
                # This shouldn't happen in a valid DAG
                break

            current_task = next_task

        return critical_path[::-1]  # Reverse to get topological order

    def _find_parallel_safe_tasks(
        self, graph: dict[str, set[str]], levels: dict[str, int]
    ) -> list[list[str]]:
        """
        Find groups of tasks that can be executed in parallel.

        Tasks are parallel-safe if they are at the same dependency level
        and don't depend on each other.

        Args:
            graph: Dependency graph (task -> dependencies)
            levels: Dependency levels for each task

        Returns:
            List of groups, where each group is a list of task IDs that can run in parallel
        """
        # Group tasks by level
        level_groups: dict[int, list[str]] = defaultdict(list)

        for task_id, level in levels.items():
            level_groups[level].append(task_id)

        # Filter groups to remove dependencies within the same level
        parallel_safe_groups: list[list[str]] = []

        for level, tasks in sorted(level_groups.items()):
            # Check if tasks within this level depend on each other
            task_set = set(tasks)
            independent_tasks = []

            for task_id in tasks:
                dependencies = graph.get(task_id, set())
                # Task is independent if it doesn't depend on other tasks at the same level
                if not dependencies.intersection(task_set):
                    independent_tasks.append(task_id)

            if independent_tasks:
                parallel_safe_groups.append(sorted(independent_tasks))

        return parallel_safe_groups

    def _detect_all_cycles(
        self, graph: dict[str, set[str]]
    ) -> list[list[str]]:
        """
        Detect all circular dependencies using DFS.

        Args:
            graph: Dependency graph (task -> dependencies)

        Returns:
            List of cycles, where each cycle is a list of task IDs
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> bool:
            """DFS helper that returns True if a cycle is found."""
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    # Found a cycle - extract it from the path
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles
