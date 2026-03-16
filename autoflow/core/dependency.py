"""
Autoflow Dependency Tracker Module

Provides dependency tracking and validation for cross-repository operations.
Enables proper ordering of operations and detection of circular dependencies.

Usage:
    from autoflow.core.dependency import DependencyTracker
    from autoflow.core.repository import Repository, RepositoryDependency

    tracker = DependencyTracker(".autoflow")
    tracker.initialize()

    # Add a dependency
    dep = RepositoryDependency(
        source_repo_id="frontend",
        target_repo_id="backend-api",
        dependency_type="runtime",
        branch_constraint="main"
    )
    tracker.add_dependency(dep)

    # Check for circular dependencies
    errors = tracker.validate()
    if errors:
        for error in errors:
            print(f"Error: {error}")

    # Get execution order
    order = tracker.get_execution_order()
    print(f"Execution order: {order}")
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional, TypedDict, Union

from pydantic import ValidationError

from autoflow.core.repository import (
    Repository,
    RepositoryDependency,
    RepositoryManager,
)
from autoflow.core.state import StateManager


# === TypedDict Definitions ===


class DependencyData(TypedDict, total=False):
    """
    TypedDict for dependency data dictionary input.

    This type provides type safety for dependency data passed to add_dependency.
    All fields are optional to support partial updates and various input formats.

    Attributes:
        source_repo_id: ID of the repository that has this dependency
        target_repo_id: ID of the repository being depended on
        dependency_type: Type of dependency relationship (runtime, development, etc.)
        branch_constraint: Required branch for the target repository
        version_constraint: Optional version constraint
        required: Whether this dependency must be satisfied
        created_at: When this dependency was created
        metadata: Additional metadata about the dependency
    """

    source_repo_id: str
    target_repo_id: str
    dependency_type: str
    branch_constraint: str | None
    version_constraint: str | None
    required: bool
    created_at: str
    metadata: dict[str, Any]


class DependencyTypeCounts(TypedDict, total=False):
    """
    TypedDict for dependency type counts.

    Maps dependency type names to the number of dependencies of that type.

    Attributes:
        runtime: Count of runtime dependencies
        development: Count of development dependencies
        peer: Count of peer dependencies
        optional: Count of optional dependencies
    """

    runtime: int
    development: int
    peer: int
    optional: int


class DependencyStatus(TypedDict, total=False):
    """
    TypedDict for dependency tracker status summary.

    Provides a typed structure for the status information returned by get_status.

    Attributes:
        total: Total number of dependencies
        by_type: Dictionary counting dependencies by type
        repositories: Total number of repositories
        has_errors: Whether there are validation errors
    """

    total: int
    by_type: DependencyTypeCounts
    repositories: int
    has_errors: bool


class DependencyTracker:
    """
    Tracks and validates cross-repository dependencies.

    Provides methods for adding, removing, and validating dependencies
    between repositories. Detects circular dependencies and determines
    execution order for multi-repository operations.

    Integrates with RepositoryManager and StateManager for atomic
    file operations and crash safety.

    Attributes:
        state: StateManager instance for state operations
        repo_manager: RepositoryManager instance for repository operations

    Example:
        >>> tracker = DependencyTracker(".autoflow")
        >>> tracker.initialize()
        >>> dep = RepositoryDependency(
        ...     source_repo_id="frontend",
        ...     target_repo_id="backend-api",
        ...     dependency_type="runtime"
        ... )
        >>> tracker.add_dependency(dep)
        >>> order = tracker.get_execution_order()
        >>> print(order)
        ['backend-api', 'frontend']
    """

    def __init__(
        self,
        state_dir: Union[str, Path, StateManager],
        repo_manager: Optional[RepositoryManager] = None,
    ):
        """
        Initialize the DependencyTracker.

        Args:
            state_dir: Root directory for state storage, or a StateManager instance.
            repo_manager: Optional RepositoryManager instance. If not provided,
                         creates a new one from state_dir.
        """
        if isinstance(state_dir, StateManager):
            self.state = state_dir
        else:
            self.state = StateManager(state_dir)

        if repo_manager is not None:
            self.repo_manager = repo_manager
        else:
            self.repo_manager = RepositoryManager(self.state)

    @property
    def state_dir(self) -> Path:
        """Path to state directory."""
        return self.state.state_dir

    @property
    def dependencies_dir(self) -> Path:
        """Path to dependencies directory."""
        return self.state.dependencies_dir

    @property
    def repositories_dir(self) -> Path:
        """Path to repositories directory."""
        return self.state.repositories_dir

    def initialize(self) -> None:
        """
        Initialize the state directory structure.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> tracker = DependencyTracker(".autoflow")
            >>> tracker.initialize()
            >>> assert tracker.state_dir.exists()
        """
        self.state.initialize()

    # === Dependency Operations ===

    def add_dependency(
        self,
        dependency: Union[RepositoryDependency, DependencyData],
    ) -> str:
        """
        Add a dependency relationship between repositories.

        Args:
            dependency: RepositoryDependency object or dependency data dictionary

        Returns:
            Dependency ID (generated from source and target repo IDs)

        Raises:
            ValueError: If dependency data is invalid

        Example:
            >>> dep = RepositoryDependency(
            ...     source_repo_id="frontend",
            ...     target_repo_id="backend-api",
            ...     dependency_type="runtime"
            ... )
            >>> dep_id = tracker.add_dependency(dep)
            >>> print(dep_id)
            'frontend-to-backend-api'
        """
        # Convert dict to RepositoryDependency if needed
        if isinstance(dependency, dict):
            try:
                dependency = RepositoryDependency(**dependency)
            except ValidationError as e:
                raise ValueError(f"Invalid dependency data: {e}")

        # Generate dependency ID
        dep_id = self._generate_dependency_id(
            dependency.source_repo_id,
            dependency.target_repo_id,
        )

        # Save dependency
        dep_data = dependency.model_dump()
        file_path = self.dependencies_dir / f"{dep_id}.json"

        # Ensure created_at is set and serializable
        from datetime import datetime

        if "created_at" not in dep_data:
            dep_data["created_at"] = datetime.utcnow().isoformat()
        else:
            # Convert datetime object to ISO string if needed
            created_at = dep_data["created_at"]
            if isinstance(created_at, datetime):
                dep_data["created_at"] = created_at.isoformat()
            elif not isinstance(created_at, str):
                dep_data["created_at"] = str(created_at)

        self.state.write_json(file_path, dep_data)
        return dep_id

    def remove_dependency(self, dep_id: str) -> bool:
        """
        Remove a dependency relationship.

        Args:
            dep_id: Dependency identifier

        Returns:
            True if removed, False if not found

        Example:
            >>> removed = tracker.remove_dependency("frontend-to-backend-api")
            >>> print(removed)
            True
        """
        file_path = self.dependencies_dir / f"{dep_id}.json"
        if file_path.exists():
            self.state._create_backup(file_path)
            file_path.unlink()
            return True
        return False

    def get_dependency(self, dep_id: str) -> Optional[RepositoryDependency]:
        """
        Get a dependency by ID.

        Args:
            dep_id: Dependency identifier

        Returns:
            RepositoryDependency object or None if not found

        Example:
            >>> dep = tracker.get_dependency("frontend-to-backend-api")
            >>> if dep:
            ...     print(f"{dep.source_repo_id} -> {dep.target_repo_id}")
        """
        file_path = self.dependencies_dir / f"{dep_id}.json"
        try:
            dep_data = self.state.read_json(file_path)
            return RepositoryDependency(**dep_data)
        except FileNotFoundError:
            return None
        except (ValidationError, KeyError):
            return None

    def list_dependencies(
        self,
        source_repo_id: Optional[str] = None,
        target_repo_id: Optional[str] = None,
        dependency_type: Optional[str] = None,
    ) -> list[RepositoryDependency]:
        """
        List dependencies, optionally filtered.

        Args:
            source_repo_id: Filter by source repository ID
            target_repo_id: Filter by target repository ID
            dependency_type: Filter by dependency type

        Returns:
            List of RepositoryDependency objects

        Example:
            >>> runtime_deps = tracker.list_dependencies(
            ...     dependency_type="runtime"
            ... )
            >>> for dep in runtime_deps:
            ...     print(f"{dep.source_repo_id} -> {dep.target_repo_id}")
        """
        dependencies = []
        if not self.dependencies_dir.exists():
            return dependencies

        for dep_file in self.dependencies_dir.glob("*.json"):
            try:
                dep_data = self.state.read_json(dep_file)
                dep = RepositoryDependency(**dep_data)

                # Apply filters
                if source_repo_id and dep.source_repo_id != source_repo_id:
                    continue
                if target_repo_id and dep.target_repo_id != target_repo_id:
                    continue
                if dependency_type and dep.dependency_type != dependency_type:
                    continue

                dependencies.append(dep)
            except (json.JSONDecodeError, ValidationError, KeyError):
                continue

        # Sort by source_repo_id, then target_repo_id
        dependencies.sort(
            key=lambda d: (d.source_repo_id, d.target_repo_id)
        )
        return dependencies

    # === Dependency Analysis ===

    def get_dependencies_for(
        self,
        repo_id: str,
        as_source: bool = True,
        as_target: bool = False,
    ) -> list[RepositoryDependency]:
        """
        Get all dependencies for a specific repository.

        Args:
            repo_id: Repository identifier
            as_source: Include dependencies where repo is the source
            as_target: Include dependencies where repo is the target

        Returns:
            List of RepositoryDependency objects

        Example:
            >>> deps = tracker.get_dependencies_for("frontend")
            >>> for dep in deps:
            ...     print(f"Frontend depends on {dep.target_repo_id}")
        """
        all_deps = self.list_dependencies()

        result = []
        for dep in all_deps:
            if as_source and dep.source_repo_id == repo_id:
                result.append(dep)
            if as_target and dep.target_repo_id == repo_id:
                result.append(dep)

        return result

    def get_dependency_graph(self) -> dict[str, set[str]]:
        """
        Build a dependency graph mapping repositories to their dependencies.

        Returns:
            Dictionary mapping source repo IDs to sets of target repo IDs

        Example:
            >>> graph = tracker.get_dependency_graph()
            >>> for source, targets in graph.items():
            ...     print(f"{source} -> {', '.join(targets)}")
        """
        graph: dict[str, set[str]] = defaultdict(set)

        for dep in self.list_dependencies():
            graph[dep.source_repo_id].add(dep.target_repo_id)

        return dict(graph)

    def get_reverse_dependency_graph(self) -> dict[str, set[str]]:
        """
        Build a reverse dependency graph mapping repositories to their dependents.

        Returns:
            Dictionary mapping target repo IDs to sets of source repo IDs

        Example:
            >>> reverse_graph = tracker.get_reverse_dependency_graph()
            >>> for target, sources in reverse_graph.items():
            ...     print(f"{target} is depended on by {', '.join(sources)}")
        """
        graph: dict[str, set[str]] = defaultdict(set)

        for dep in self.list_dependencies():
            graph[dep.target_repo_id].add(dep.source_repo_id)

        return dict(graph)

    # === Validation ===

    def validate(self) -> list[str]:
        """
        Validate all dependencies and return list of errors.

        Checks that:
        - All referenced repositories exist
        - No circular dependencies exist
        - Dependencies are properly configured

        Returns:
            List of error messages (empty if all valid)

        Example:
            >>> errors = tracker.validate()
            >>> if errors:
            ...     for error in errors:
            ...         print(f"Error: {error}")
        """
        errors: list[str] = []

        # Check for missing repositories
        repo_ids = self._get_all_repository_ids()
        dependencies = self.list_dependencies()

        for dep in dependencies:
            if dep.source_repo_id not in repo_ids:
                errors.append(
                    f"Dependency '{dep.source_repo_id} -> {dep.target_repo_id}': "
                    f"source repository '{dep.source_repo_id}' does not exist"
                )

            if dep.target_repo_id not in repo_ids:
                errors.append(
                    f"Dependency '{dep.source_repo_id} -> {dep.target_repo_id}': "
                    f"target repository '{dep.target_repo_id}' does not exist"
                )

        # Check for circular dependencies
        circular = self._detect_circular_dependencies()
        if circular:
            for cycle in circular:
                errors.append(
                    f"Circular dependency detected: {' -> '.join(cycle)} -> {cycle[0]}"
                )

        return errors

    def _get_all_repository_ids(self) -> set[str]:
        """Get all repository IDs from repository manager."""
        repo_ids = set()
        repositories = self.repo_manager.list_repositories()

        for repo in repositories:
            repo_id = repo.get("id")
            if repo_id:
                repo_ids.add(repo_id)

        return repo_ids

    def _detect_circular_dependencies(self) -> list[list[str]]:
        """
        Detect circular dependencies using depth-first search.

        Returns:
            List of cycles (each cycle is a list of repo IDs)
        """
        graph = self.get_dependency_graph()
        cycles: list[list[str]] = []

        # Perform DFS to detect cycles
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

    # === Execution Ordering ===

    def get_execution_order(self) -> list[str]:
        """
        Get topological ordering of repositories based on dependencies.

        Repositories with no dependencies come first. Dependent repositories
        come after their dependencies.

        Returns:
            List of repository IDs in execution order

        Raises:
            ValueError: If circular dependencies are detected

        Example:
            >>> order = tracker.get_execution_order()
            >>> print(f"Execution order: {order}")
            ['backend-api', 'shared-utils', 'frontend']
        """
        # Validate first
        errors = self.validate()
        if errors:
            # Check if there are circular dependencies
            circular = self._detect_circular_dependencies()
            if circular:
                raise ValueError(
                    f"Cannot determine execution order: circular dependencies exist: {errors}"
                )

        # Build reverse dependency graph (targets depend on sources)
        # This maps each repo to the repos that depend on it
        reverse_graph = self.get_reverse_dependency_graph()

        # Get all repositories
        all_repos = self._get_all_repository_ids()

        # Perform topological sort using Kahn's algorithm
        # Calculate in-degrees (number of dependencies each repo has)
        dependency_graph = self.get_dependency_graph()
        in_degree: dict[str, int] = {repo: 0 for repo in all_repos}

        # Calculate in-degrees based on dependencies
        for source, targets in dependency_graph.items():
            for target in targets:
                # source depends on target, so target's in-degree increases
                if target in in_degree:
                    in_degree[source] += 1

        # Start with nodes that have no dependencies (no outgoing edges in dep graph)
        queue = [repo for repo in all_repos if in_degree[repo] == 0]
        result: list[str] = []

        while queue:
            # Sort queue for deterministic ordering
            queue.sort()
            node = queue.pop(0)
            result.append(node)

            # Reduce in-degree for repos that depend on this node
            for dependent in reverse_graph.get(node, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # Check if all nodes were processed (should not happen due to validation)
        if len(result) != len(all_repos):
            remaining = all_repos - set(result)
            raise ValueError(
                f"Failed to determine execution order. Could not order: {remaining}"
            )

        return result

    # === Utility Methods ===

    def _generate_dependency_id(self, source_id: str, target_id: str) -> str:
        """
        Generate a unique dependency ID from source and target repository IDs.

        Args:
            source_id: Source repository ID
            target_id: Target repository ID

        Returns:
            Dependency ID string
        """
        return f"{source_id}-to-{target_id}"

    def get_status(self) -> DependencyStatus:
        """
        Get status summary of dependencies.

        Returns:
            Dictionary with counts and status information

        Example:
            >>> status = tracker.get_status()
            >>> print(f"Total dependencies: {status['total']}")
        """
        dependencies = self.list_dependencies()

        return {
            "total": len(dependencies),
            "by_type": self._count_dependencies_by_type(dependencies),
            "repositories": len(self._get_all_repository_ids()),
            "has_errors": len(self.validate()) > 0,
        }

    def _count_dependencies_by_type(
        self,
        dependencies: list[RepositoryDependency],
    ) -> DependencyTypeCounts:
        """Count dependencies by type."""
        counts = defaultdict(int)

        for dep in dependencies:
            # Convert enum to string value
            dep_type = dep.dependency_type.value if hasattr(dep.dependency_type, 'value') else str(dep.dependency_type)
            counts[dep_type] += 1

        return dict(counts)

    def get_dependents(
        self,
        repo_id: str,
        recursive: bool = False,
    ) -> set[str]:
        """
        Get all repositories that depend on the given repository.

        Args:
            repo_id: Repository identifier
            recursive: If True, include transitive dependents

        Returns:
            Set of repository IDs that depend on the given repository

        Example:
            >>> dependents = tracker.get_dependents("shared-utils")
            >>> print(f"Dependents: {dependents}")
            {'frontend', 'backend-api'}
        """
        reverse_graph = self.get_reverse_dependency_graph()

        if not recursive:
            return reverse_graph.get(repo_id, set())

        # Recursive case - use BFS
        dependents: set[str] = set()
        to_visit: list[str] = list(reverse_graph.get(repo_id, set()))

        while to_visit:
            current = to_visit.pop()
            if current not in dependents:
                dependents.add(current)
                to_visit.extend(reverse_graph.get(current, set()))

        return dependents

    def get_prerequisites(
        self,
        repo_id: str,
        recursive: bool = False,
    ) -> set[str]:
        """
        Get all repositories that the given repository depends on.

        Args:
            repo_id: Repository identifier
            recursive: If True, include transitive dependencies

        Returns:
            Set of repository IDs that the given repository depends on

        Example:
            >>> prereqs = tracker.get_prerequisites("frontend")
            >>> print(f"Prerequisites: {prereqs}")
            {'backend-api', 'shared-utils'}
        """
        graph = self.get_dependency_graph()

        if not recursive:
            return graph.get(repo_id, set())

        # Recursive case - use BFS
        prerequisites: set[str] = set()
        to_visit: list[str] = list(graph.get(repo_id, set()))

        while to_visit:
            current = to_visit.pop()
            if current not in prerequisites:
                prerequisites.add(current)
                to_visit.extend(graph.get(current, set()))

        return prerequisites

    def __repr__(self) -> str:
        """Detailed string representation of the DependencyTracker."""
        return (
            f"DependencyTracker(state_dir={self.state_dir!r}, "
            f"dependencies={len(self.list_dependencies())})"
        )
