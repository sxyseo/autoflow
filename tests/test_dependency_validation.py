"""
Unit Tests for Dependency Validation

Tests the DependencyTracker's validation functionality including:
- Circular dependency detection
- Missing repository detection
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from autoflow.core.dependency import DependencyTracker
from autoflow.core.repository import Repository, RepositoryDependency
from autoflow.core.state import StateManager


@pytest.fixture
def temp_state_dir() -> Path:
    """Create a temporary state directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_dir = Path(tmp_dir) / ".autoflow"
        state_dir.mkdir()
        yield state_dir


@pytest.fixture
def dependency_tracker(temp_state_dir: Path) -> DependencyTracker:
    """Create a DependencyTracker instance with temporary directory."""
    tracker = DependencyTracker(temp_state_dir)
    tracker.initialize()
    return tracker


def test_validate_with_no_dependencies(dependency_tracker: DependencyTracker) -> None:
    """Test validation with no dependencies returns no errors."""
    errors = dependency_tracker.validate()
    assert errors == []


def test_validate_with_missing_repositories(dependency_tracker: DependencyTracker) -> None:
    """Test validation detects missing repositories."""
    # Add a dependency for non-existent repositories
    dep = RepositoryDependency(
        source_repo_id="nonexistent-src",
        target_repo_id="nonexistent-tgt",
        dependency_type="runtime",
    )
    dependency_tracker.add_dependency(dep)

    errors = dependency_tracker.validate()

    # Should have errors for both missing source and target
    assert len(errors) == 2
    assert any("source repository 'nonexistent-src' does not exist" in e for e in errors)
    assert any("target repository 'nonexistent-tgt' does not exist" in e for e in errors)


def test_validate_with_circular_dependencies(dependency_tracker: DependencyTracker) -> None:
    """Test validation detects circular dependencies."""
    # Create repositories
    state = dependency_tracker.state
    repo1 = Repository(id="repo1", name="Repository 1", path="/tmp/repo1")
    repo2 = Repository(id="repo2", name="Repository 2", path="/tmp/repo2")

    # Save repositories
    state.write_json(
        state.repositories_dir / "repo1.json",
        repo1.model_dump(),
    )
    state.write_json(
        state.repositories_dir / "repo2.json",
        repo2.model_dump(),
    )

    # Add circular dependencies: repo1 -> repo2 -> repo1
    dep1 = RepositoryDependency(
        source_repo_id="repo1",
        target_repo_id="repo2",
        dependency_type="runtime",
    )
    dep2 = RepositoryDependency(
        source_repo_id="repo2",
        target_repo_id="repo1",
        dependency_type="runtime",
    )

    dependency_tracker.add_dependency(dep1)
    dependency_tracker.add_dependency(dep2)

    errors = dependency_tracker.validate()

    # Should detect circular dependency
    assert len(errors) == 1
    assert "Circular dependency detected" in errors[0]
    assert "repo1" in errors[0]
    assert "repo2" in errors[0]


def test_validate_with_valid_dependencies(dependency_tracker: DependencyTracker) -> None:
    """Test validation with valid dependencies returns no errors."""
    # Create repositories
    state = dependency_tracker.state
    repo1 = Repository(id="repo1", name="Repository 1", path="/tmp/repo1")
    repo2 = Repository(id="repo2", name="Repository 2", path="/tmp/repo2")
    repo3 = Repository(id="repo3", name="Repository 3", path="/tmp/repo3")

    # Save repositories
    state.write_json(
        state.repositories_dir / "repo1.json",
        repo1.model_dump(),
    )
    state.write_json(
        state.repositories_dir / "repo2.json",
        repo2.model_dump(),
    )
    state.write_json(
        state.repositories_dir / "repo3.json",
        repo3.model_dump(),
    )

    # Add valid dependencies: repo1 -> repo2, repo2 -> repo3
    dep1 = RepositoryDependency(
        source_repo_id="repo1",
        target_repo_id="repo2",
        dependency_type="runtime",
    )
    dep2 = RepositoryDependency(
        source_repo_id="repo2",
        target_repo_id="repo3",
        dependency_type="runtime",
    )

    dependency_tracker.add_dependency(dep1)
    dependency_tracker.add_dependency(dep2)

    errors = dependency_tracker.validate()

    # Should have no errors
    assert errors == []


def test_detect_circular_dependencies_complex(dependency_tracker: DependencyTracker) -> None:
    """Test detection of complex circular dependencies."""
    # Create repositories
    state = dependency_tracker.state
    for i in range(1, 6):
        repo = Repository(id=f"repo{i}", name=f"Repository {i}", path=f"/tmp/repo{i}")
        state.write_json(
            state.repositories_dir / f"repo{i}.json",
            repo.model_dump(),
        )

    # Create a cycle: repo1 -> repo2 -> repo3 -> repo1
    deps = [
        RepositoryDependency(source_repo_id="repo1", target_repo_id="repo2", dependency_type="runtime"),
        RepositoryDependency(source_repo_id="repo2", target_repo_id="repo3", dependency_type="runtime"),
        RepositoryDependency(source_repo_id="repo3", target_repo_id="repo1", dependency_type="runtime"),
    ]

    for dep in deps:
        dependency_tracker.add_dependency(dep)

    errors = dependency_tracker.validate()

    # Should detect the circular dependency
    assert len(errors) == 1
    assert "Circular dependency detected" in errors[0]


def test_get_execution_order_with_valid_dependencies(dependency_tracker: DependencyTracker) -> None:
    """Test get_execution_order with valid dependencies."""
    # Create repositories
    state = dependency_tracker.state
    for i in range(1, 4):
        repo = Repository(id=f"repo{i}", name=f"Repository {i}", path=f"/tmp/repo{i}")
        state.write_json(
            state.repositories_dir / f"repo{i}.json",
            repo.model_dump(),
        )

    # Add dependencies: repo1 -> repo2 -> repo3
    # This means repo1 depends on repo2, and repo2 depends on repo3
    deps = [
        RepositoryDependency(source_repo_id="repo1", target_repo_id="repo2", dependency_type="runtime"),
        RepositoryDependency(source_repo_id="repo2", target_repo_id="repo3", dependency_type="runtime"),
    ]

    for dep in deps:
        dependency_tracker.add_dependency(dep)

    order = dependency_tracker.get_execution_order()

    # Verify all repos are in the order
    assert "repo1" in order
    assert "repo2" in order
    assert "repo3" in order

    # The order should be deterministic (sorted by repo ID)
    assert len(order) == 3


def test_get_execution_order_raises_on_circular(dependency_tracker: DependencyTracker) -> None:
    """Test get_execution_order raises ValueError on circular dependencies."""
    # Create repositories
    state = dependency_tracker.state
    repo1 = Repository(id="repo1", name="Repository 1", path="/tmp/repo1")
    repo2 = Repository(id="repo2", name="Repository 2", path="/tmp/repo2")

    state.write_json(
        state.repositories_dir / "repo1.json",
        repo1.model_dump(),
    )
    state.write_json(
        state.repositories_dir / "repo2.json",
        repo2.model_dump(),
    )

    # Add circular dependency
    dep1 = RepositoryDependency(
        source_repo_id="repo1",
        target_repo_id="repo2",
        dependency_type="runtime",
    )
    dep2 = RepositoryDependency(
        source_repo_id="repo2",
        target_repo_id="repo1",
        dependency_type="runtime",
    )

    dependency_tracker.add_dependency(dep1)
    dependency_tracker.add_dependency(dep2)

    # Should raise ValueError
    with pytest.raises(ValueError, match="circular dependencies"):
        dependency_tracker.get_execution_order()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
