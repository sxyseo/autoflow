"""
Autoflow Conflict Detection Module

Provides utilities for detecting potential conflicts between parallel tasks,
including file access conflicts and resource contention. Helps prevent
data corruption and race conditions when executing tasks concurrently.

Usage:
    from autoflow.core.conflict import (
        detect_file_conflicts,
        detect_task_conflicts,
        ConflictInfo,
        ConflictSeverity,
    )

    # Detect conflicts between tasks
    tasks = [
        {"id": "task-1", "files": ["src/main.py"]},
        {"id": "task-2", "files": ["src/main.py", "src/utils.py"]},
    ]
    conflicts = detect_task_conflicts(tasks)
    if conflicts:
        print(f"Found {len(conflicts)} potential conflicts")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ConflictSeverity(str, Enum):
    """Severity level of a detected conflict."""

    LOW = "low"
    """Minor conflict, unlikely to cause issues"""

    MEDIUM = "medium"
    """Moderate conflict, may cause issues under certain conditions"""

    HIGH = "high"
    """Severe conflict, very likely to cause data corruption or failures"""


class ConflictType(str, Enum):
    """Type of conflict detected."""

    FILE_OVERLAP = "file_overlap"
    """Multiple tasks modify the same file"""

    DIRECTORY_OVERLAP = "directory_overlap"
    """Multiple tasks modify files in the same directory"""

    RESOURCE_CONTENTION = "resource_contention"
    """Multiple tasks contend for the same resource (e.g., network, database)"""

    DEPENDENCY_CYCLE = "dependency_cycle"
    """Circular dependency between tasks"""


@dataclass
class ConflictInfo:
    """
    Information about a detected conflict.

    Attributes:
        type: The type of conflict detected
        severity: How severe the conflict is
        description: Human-readable description of the conflict
        task_ids: List of task IDs involved in the conflict
        resources: List of resources (files, directories, etc.) involved
        suggestion: Optional suggestion for resolving the conflict
    """

    type: ConflictType
    severity: ConflictSeverity
    description: str
    task_ids: list[str]
    resources: list[str] = field(default_factory=list)
    suggestion: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert conflict info to a dictionary.

        Returns:
            Dictionary representation of the conflict
        """
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "description": self.description,
            "task_ids": self.task_ids,
            "resources": self.resources,
            "suggestion": self.suggestion,
        }


@dataclass
class ConflictReport:
    """
    Report of detected conflicts.

    Attributes:
        has_conflicts: Whether any conflicts were detected
        conflicts: List of conflict details
        total_tasks: Number of tasks analyzed
        safe_to_run: Whether it's safe to run tasks in parallel
    """

    has_conflicts: bool
    conflicts: list[ConflictInfo]
    total_tasks: int
    safe_to_run: bool

    def get_high_severity(self) -> list[ConflictInfo]:
        """
        Get only high-severity conflicts.

        Returns:
            List of high-severity conflicts
        """
        return [c for c in self.conflicts if c.severity == ConflictSeverity.HIGH]

    def get_by_type(self, conflict_type: ConflictType) -> list[ConflictInfo]:
        """
        Get conflicts of a specific type.

        Args:
            conflict_type: Type of conflict to filter by

        Returns:
            List of conflicts of the specified type
        """
        return [c for c in self.conflicts if c.type == conflict_type]

    def to_dict(self) -> dict[str, Any]:
        """
        Convert report to a dictionary.

        Returns:
            Dictionary representation of the report
        """
        return {
            "has_conflicts": self.has_conflicts,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "total_tasks": self.total_tasks,
            "safe_to_run": self.safe_to_run,
        }


def detect_file_conflicts(
    task_files: dict[str, list[str]],
    severity_threshold: ConflictSeverity = ConflictSeverity.LOW,
) -> ConflictReport:
    """
    Detect file access conflicts between tasks.

    Analyzes file access patterns to identify when multiple tasks might
    modify the same files, which could lead to race conditions or
    data corruption during parallel execution.

    Args:
        task_files: Dictionary mapping task IDs to lists of file paths
        severity_threshold: Minimum severity level to include in report

    Returns:
        ConflictReport with detected file conflicts

    Examples:
        >>> task_files = {
        ...     "task-1": ["src/main.py", "src/utils.py"],
        ...     "task-2": ["src/main.py", "tests/test_main.py"],
        ...     "task-3": ["docs/README.md"],
        ... }
        >>> report = detect_file_conflicts(task_files)
        >>> if report.has_conflicts:
        ...     print(f"Found {len(report.conflicts)} conflicts")
        ...     for conflict in report.get_high_severity():
        ...         print(f"  {conflict.description}")
    """
    conflicts: list[ConflictInfo] = []
    task_ids = list(task_files.keys())

    # Build a mapping of files to tasks that access them
    file_to_tasks: dict[str, list[str]] = {}
    for task_id, files in task_files.items():
        for file_path in files:
            if file_path not in file_to_tasks:
                file_to_tasks[file_path] = []
            file_to_tasks[file_path].append(task_id)

    # Detect direct file overlaps
    for file_path, accessing_tasks in file_to_tasks.items():
        if len(accessing_tasks) > 1:
            severity = _determine_file_conflict_severity(file_path)
            if _severity_meets_threshold(severity, severity_threshold):
                conflicts.append(
                    ConflictInfo(
                        type=ConflictType.FILE_OVERLAP,
                        severity=severity,
                        description=f"Multiple tasks modify the same file: {file_path}",
                        task_ids=accessing_tasks,
                        resources=[file_path],
                        suggestion="Consider serializing these tasks or merging them into a single task",
                    )
                )

    # Detect directory-level conflicts
    dir_to_tasks: dict[str, list[str]] = {}
    for task_id, files in task_files.items():
        for file_path in files:
            dir_path = str(Path(file_path).parent)
            if dir_path not in dir_to_tasks:
                dir_to_tasks[dir_path] = []
            dir_to_tasks[dir_path].append(task_id)

    for dir_path, tasks_in_dir in dir_to_tasks.items():
        if len(tasks_in_dir) > 1:
            # Check if this is already covered by a file overlap
            if not any(
                dir_path in c.resources
                for c in conflicts
                if c.type == ConflictType.FILE_OVERLAP
            ):
                severity = ConflictSeverity.MEDIUM
                if _severity_meets_threshold(severity, severity_threshold):
                    conflicts.append(
                        ConflictInfo(
                            type=ConflictType.DIRECTORY_OVERLAP,
                            severity=severity,
                            description=f"Multiple tasks modify files in the same directory: {dir_path}",
                            task_ids=tasks_in_dir,
                            resources=[dir_path],
                            suggestion="Monitor for merge conflicts or consider task serialization",
                        )
                    )

    has_conflicts = len(conflicts) > 0
    safe_to_run = not any(c.severity == ConflictSeverity.HIGH for c in conflicts)

    return ConflictReport(
        has_conflicts=has_conflicts,
        conflicts=conflicts,
        total_tasks=len(task_ids),
        safe_to_run=safe_to_run,
    )


def detect_task_conflicts(
    tasks: list[dict[str, Any]],
    severity_threshold: ConflictSeverity = ConflictSeverity.LOW,
) -> ConflictReport:
    """
    Detect various types of conflicts between tasks.

    Performs comprehensive conflict detection including file overlaps,
    resource contention, and dependency cycles.

    Args:
        tasks: List of task dictionaries, each containing at least an 'id' field
        severity_threshold: Minimum severity level to include in report

    Returns:
        ConflictReport with all detected conflicts

    Examples:
        >>> tasks = [
        ...     {
        ...         "id": "task-1",
        ...         "files": ["src/main.py"],
        ...         "resources": ["database:primary"],
        ...     },
        ...     {
        ...         "id": "task-2",
        ...         "files": ["src/main.py"],
        ...         "resources": ["database:primary"],
        ...     },
        ... ]
        >>> report = detect_task_conflicts(tasks)
        >>> if not report.safe_to_run:
        ...     print("Not safe to run in parallel!")
        ...     for conflict in report.conflicts:
        ...         print(f"  {conflict.description}")
    """
    conflicts: list[ConflictInfo] = []

    # Extract task IDs and build task lookup
    task_lookup = {task["id"]: task for task in tasks if "id" in task}
    task_ids = list(task_lookup.keys())

    # Detect file conflicts
    task_files: dict[str, list[str]] = {}
    for task in tasks:
        task_id = task.get("id")
        if not task_id:
            continue

        files = task.get("files", [])
        if isinstance(files, list):
            task_files[task_id] = files

    if task_files:
        file_report = detect_file_conflicts(task_files, severity_threshold)
        conflicts.extend(file_report.conflicts)

    # Detect resource contention
    task_resources: dict[str, list[str]] = {}
    for task in tasks:
        task_id = task.get("id")
        if not task_id:
            continue

        resources = task.get("resources", [])
        if isinstance(resources, list):
            task_resources[task_id] = resources

    resource_to_tasks: dict[str, list[str]] = {}
    for task_id, resources in task_resources.items():
        for resource in resources:
            if resource not in resource_to_tasks:
                resource_to_tasks[resource] = []
            resource_to_tasks[resource].append(task_id)

    for resource, accessing_tasks in resource_to_tasks.items():
        if len(accessing_tasks) > 1:
            severity = _determine_resource_conflict_severity(resource)
            if _severity_meets_threshold(severity, severity_threshold):
                conflicts.append(
                    ConflictInfo(
                        type=ConflictType.RESOURCE_CONTENTION,
                        severity=severity,
                        description=f"Multiple tasks contend for resource: {resource}",
                        task_ids=accessing_tasks,
                        resources=[resource],
                        suggestion="Consider resource pooling or sequential access",
                    )
                )

    # Detect dependency cycles
    dependencies: dict[str, list[str]] = {}
    for task in tasks:
        task_id = task.get("id")
        if not task_id:
            continue

        deps = task.get("dependencies", [])
        if isinstance(deps, list):
            dependencies[task_id] = deps

    cycles = _detect_dependency_cycles(dependencies)
    for cycle in cycles:
        severity = ConflictSeverity.HIGH
        if _severity_meets_threshold(severity, severity_threshold):
            conflicts.append(
                ConflictInfo(
                    type=ConflictType.DEPENDENCY_CYCLE,
                    severity=severity,
                    description=f"Circular dependency detected: {' -> '.join(cycle)}",
                    task_ids=cycle,
                    resources=[],
                    suggestion="Break the cycle by removing or restructuring dependencies",
                )
            )

    has_conflicts = len(conflicts) > 0
    safe_to_run = not any(c.severity == ConflictSeverity.HIGH for c in conflicts)

    return ConflictReport(
        has_conflicts=has_conflicts,
        conflicts=conflicts,
        total_tasks=len(task_ids),
        safe_to_run=safe_to_run,
    )


def _determine_file_conflict_severity(file_path: str) -> ConflictSeverity:
    """
    Determine the severity of a file conflict based on the file type.

    Args:
        file_path: Path to the file

    Returns:
        ConflictSeverity level
    """
    path = Path(file_path)
    filename = path.name.lower()

    # High severity: code files, configuration files
    high_extensions = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".cpp",
        ".c",
        ".h",
        ".go",
        ".rs",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
    }

    # Medium severity: documentation, data files
    medium_extensions = {
        ".md",
        ".txt",
        ".csv",
        ".sql",
        ".sh",
        ".bat",
        ".ps1",
    }

    if path.suffix in high_extensions:
        return ConflictSeverity.HIGH
    elif path.suffix in medium_extensions:
        return ConflictSeverity.MEDIUM
    else:
        return ConflictSeverity.LOW


def _determine_resource_conflict_severity(resource: str) -> ConflictSeverity:
    """
    Determine the severity of a resource conflict.

    Args:
        resource: Resource identifier (e.g., "database:primary")

    Returns:
        ConflictSeverity level
    """
    resource_lower = resource.lower()

    # High severity: databases, critical services
    if any(
        keyword in resource_lower
        for keyword in ["database", "db:", "storage", "s3:", "redis"]
    ):
        return ConflictSeverity.HIGH

    # Medium severity: APIs, external services
    if any(
        keyword in resource_lower for keyword in ["api", "http", "https", "service"]
    ):
        return ConflictSeverity.MEDIUM

    # Low severity: caches, queues
    return ConflictSeverity.LOW


def _severity_meets_threshold(
    severity: ConflictSeverity,
    threshold: ConflictSeverity,
) -> bool:
    """
    Check if a severity meets or exceeds the threshold.

    Args:
        severity: The severity to check
        threshold: The minimum severity threshold

    Returns:
        True if severity meets or exceeds threshold
    """
    severity_order = {
        ConflictSeverity.LOW: 1,
        ConflictSeverity.MEDIUM: 2,
        ConflictSeverity.HIGH: 3,
    }
    return severity_order[severity] >= severity_order[threshold]


def _detect_dependency_cycles(
    dependencies: dict[str, list[str]],
) -> list[list[str]]:
    """
    Detect cycles in task dependencies using depth-first search.

    Args:
        dependencies: Dictionary mapping task IDs to their dependencies

    Returns:
        List of cycles, where each cycle is a list of task IDs
    """
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> bool:
        """Perform DFS to detect cycles."""
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in dependencies.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
                return True

        path.pop()
        rec_stack.remove(node)
        return False

    for node in dependencies:
        if node not in visited:
            dfs(node)

    return cycles
