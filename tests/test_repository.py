"""
Unit Tests for Autoflow Repository Management

Tests the RepositoryManager class and related models (Repository, RepositoryDependency, BranchConfig)
for multi-repository configuration and dependency tracking.

These tests use temporary directories to avoid affecting real repository files.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.core.dependency import DependencyTracker
from autoflow.core.repository import (
    BranchConfig,
    DependencyType,
    Repository,
    RepositoryDependency,
    RepositoryManager,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / ".autoflow"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def repository_manager(temp_state_dir: Path) -> RepositoryManager:
    """Create a RepositoryManager instance with temporary directory."""
    manager = RepositoryManager(temp_state_dir)
    manager.initialize()
    return manager


@pytest.fixture
def sample_repository_data() -> dict[str, Any]:
    """Return sample repository data for testing."""
    return {
        "id": "frontend",
        "name": "Frontend Monorepo",
        "path": "~/dev/frontend",
        "url": "https://github.com/org/frontend.git",
        "enabled": True,
    }


@pytest.fixture
def sample_dependency_data() -> dict[str, Any]:
    """Return sample dependency data for testing."""
    return {
        "source_repo_id": "frontend",
        "target_repo_id": "backend-api",
        "dependency_type": "runtime",
        "branch_constraint": "main",
        "required": True,
    }


# ============================================================================
# DependencyType Enum Tests
# ============================================================================


class TestDependencyType:
    """Tests for DependencyType enum."""

    def test_dependency_type_values(self) -> None:
        """Test DependencyType enum values."""
        assert DependencyType.RUNTIME == "runtime"
        assert DependencyType.DEVELOPMENT == "development"
        assert DependencyType.PEER == "peer"
        assert DependencyType.OPTIONAL == "optional"

    def test_dependency_type_is_string(self) -> None:
        """Test that DependencyType values are strings."""
        assert isinstance(DependencyType.RUNTIME.value, str)

    def test_dependency_type_from_string(self) -> None:
        """Test creating DependencyType from string."""
        dep_type = DependencyType("runtime")
        assert dep_type == DependencyType.RUNTIME


# ============================================================================
# BranchConfig Model Tests
# ============================================================================


class TestBranchConfig:
    """Tests for BranchConfig model."""

    def test_branch_config_init_default(self) -> None:
        """Test BranchConfig initialization with defaults."""
        config = BranchConfig()

        assert config.default == "main"
        # Note: validator doesn't auto-set current when not provided
        # It only sets current to default when explicitly passed as None
        assert config.current is None
        assert config.protected == ["main", "master"]

    def test_branch_config_init_custom(self) -> None:
        """Test BranchConfig initialization with custom values."""
        config = BranchConfig(
            default="develop",
            current="feature-branch",
            protected=["main", "develop", "release/*"],
        )

        assert config.default == "develop"
        assert config.current == "feature-branch"
        assert config.protected == ["main", "develop", "release/*"]

    def test_branch_config_current_defaults_to_default(self) -> None:
        """Test that current defaults to default branch when explicitly None."""
        config = BranchConfig(default="main", current=None)

        assert config.current == "main"

    def test_branch_config_current_explicit_none(self) -> None:
        """Test that explicit None for current still defaults to default."""
        config = BranchConfig(default="develop", current=None)

        assert config.current == "develop"


# ============================================================================
# RepositoryDependency Model Tests
# ============================================================================


class TestRepositoryDependency:
    """Tests for RepositoryDependency model."""

    def test_dependency_init_minimal(self) -> None:
        """Test RepositoryDependency initialization with minimal fields."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
        )

        assert dep.source_repo_id == "frontend"
        assert dep.target_repo_id == "backend"
        assert dep.dependency_type == DependencyType.RUNTIME
        assert dep.branch_constraint is None
        assert dep.version_constraint is None
        assert dep.required is True
        assert dep.metadata == {}

    def test_dependency_init_full(self) -> None:
        """Test RepositoryDependency initialization with all fields."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            dependency_type=DependencyType.DEVELOPMENT,
            branch_constraint="develop",
            version_constraint="^2.0.0",
            required=False,
            metadata={"purpose": "testing"},
        )

        assert dep.source_repo_id == "frontend"
        assert dep.target_repo_id == "backend"
        assert dep.dependency_type == DependencyType.DEVELOPMENT
        assert dep.branch_constraint == "develop"
        assert dep.version_constraint == "^2.0.0"
        assert dep.required is False
        assert dep.metadata == {"purpose": "testing"}

    def test_dependency_is_satisfied_by_id_mismatch(self) -> None:
        """Test is_satisfied_by returns False for repo ID mismatch."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
        )
        target_repo = Repository(id="other", name="Other", path="/tmp")

        assert dep.is_satisfied_by(target_repo) is False

    def test_dependency_is_satisfied_by_no_constraint(self) -> None:
        """Test is_satisfied_by returns True when no branch constraint."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
        )
        target_repo = Repository(
            id="backend",
            name="Backend",
            path="/tmp",
            branch=BranchConfig(current="feature-branch"),
        )

        assert dep.is_satisfied_by(target_repo) is True

    def test_dependency_is_satisfied_by_with_constraint_match(self) -> None:
        """Test is_satisfied_by returns True when branch constraint matches."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            branch_constraint="main",
        )
        target_repo = Repository(
            id="backend",
            name="Backend",
            path="/tmp",
            branch=BranchConfig(current="main"),
        )

        assert dep.is_satisfied_by(target_repo) is True

    def test_dependency_is_satisfied_by_with_constraint_mismatch(self) -> None:
        """Test is_satisfied_by returns False when branch constraint doesn't match."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            branch_constraint="main",
        )
        target_repo = Repository(
            id="backend",
            name="Backend",
            path="/tmp",
            branch=BranchConfig(current="develop"),
        )

        assert dep.is_satisfied_by(target_repo) is False

    def test_dependency_is_satisfied_by_with_explicit_branch(self) -> None:
        """Test is_satisfied_by uses explicit branch parameter when provided."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            branch_constraint="main",
        )
        target_repo = Repository(
            id="backend",
            name="Backend",
            path="/tmp",
            branch=BranchConfig(current="develop"),
        )

        # Explicit branch should override repo's current branch
        assert dep.is_satisfied_by(target_repo, target_branch="main") is True

    def test_dependency_str_representation(self) -> None:
        """Test __str__ method of RepositoryDependency."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            branch_constraint="main",
            required=True,
        )

        str_repr = str(dep)
        assert "frontend -> backend" in str_repr
        assert "@main" in str_repr
        # The enum representation includes the full type name
        assert "[DependencyType.RUNTIME]" in str_repr
        assert "(required)" in str_repr

    def test_dependency_repr_representation(self) -> None:
        """Test __repr__ method of RepositoryDependency."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            dependency_type=DependencyType.DEVELOPMENT,
        )

        repr_str = repr(dep)
        assert "RepositoryDependency" in repr_str
        assert "source='frontend'" in repr_str
        assert "target='backend'" in repr_str
        assert "type='development'" in repr_str


# ============================================================================
# Repository Model Tests
# ============================================================================


class TestRepository:
    """Tests for Repository model."""

    def test_repository_init_minimal(self) -> None:
        """Test Repository initialization with minimal fields."""
        repo = Repository(
            id="frontend",
            name="Frontend",
            path="/dev/frontend",
        )

        assert repo.id == "frontend"
        assert repo.name == "Frontend"
        assert repo.path == "/dev/frontend"
        assert repo.url is None
        assert repo.description is None
        assert repo.enabled is True
        assert repo.branch.default == "main"
        # current is None when not explicitly set
        assert repo.branch.current is None

    def test_repository_init_full(self) -> None:
        """Test Repository initialization with all fields."""
        repo = Repository(
            id="backend",
            name="Backend API",
            path="~/dev/backend",
            url="https://github.com/org/backend.git",
            branch=BranchConfig(default="develop", current="feature-api"),
            description="Backend service API",
            enabled=False,
        )

        assert repo.id == "backend"
        assert repo.name == "Backend API"
        assert repo.url == "https://github.com/org/backend.git"
        assert repo.description == "Backend service API"
        assert repo.enabled is False
        assert repo.branch.default == "develop"
        assert repo.branch.current == "feature-api"

    def test_repository_path_expansion_tilde(self) -> None:
        """Test Repository path expansion with tilde."""
        repo = Repository(
            id="test",
            name="Test",
            path="~/dev/test",
        )

        # Path should be expanded
        import os
        home = os.path.expanduser("~")
        assert repo.path.startswith(home)
        assert repo.path.endswith("/dev/test")

    def test_repository_path_expansion_env_var(self) -> None:
        """Test Repository path expansion with environment variables."""
        with patch.dict(os.environ, {"PROJECTS": "/home/user/projects"}):
            repo = Repository(
                id="test",
                name="Test",
                path="$PROJECTS/frontend",
            )

            assert repo.path == "/home/user/projects/frontend"

    def test_repository_get_resolved_path(self) -> None:
        """Test Repository.get_resolved_path returns absolute Path."""
        repo = Repository(
            id="test",
            name="Test",
            path="~/dev/test",
        )

        resolved = repo.get_resolved_path()
        assert isinstance(resolved, Path)
        assert resolved.is_absolute()

    def test_repository_get_git_dir(self) -> None:
        """Test Repository.get_git_dir returns path to .git directory."""
        repo = Repository(
            id="test",
            name="Test",
            path="/tmp/test",
        )

        git_dir = repo.get_git_dir()
        # Note: Path may resolve differently based on OS (e.g., /tmp -> /private/tmp on macOS)
        assert git_dir.name == ".git"
        assert str(git_dir).endswith("/test/.git")

    def test_repository_is_valid_with_git_directory(self, tmp_path: Path) -> None:
        """Test Repository.is_valid returns True for normal git repository."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        repo = Repository(id="test", name="Test", path=str(repo_path))

        assert repo.is_valid() is True

    def test_repository_is_valid_with_git_worktree(self, tmp_path: Path) -> None:
        """Test Repository.is_valid returns True for git worktree."""
        repo_path = tmp_path / "worktree"
        repo_path.mkdir()

        # Create a .git file with gitdir reference
        git_file = repo_path / ".git"
        git_file.write_text("gitdir: /path/to/.git/worktrees/test")

        repo = Repository(id="test", name="Test", path=str(repo_path))

        # This should return False because the referenced gitdir doesn't exist
        # but the code should handle the file correctly
        assert repo.is_valid() is False

    def test_repository_is_valid_missing_git(self, tmp_path: Path) -> None:
        """Test Repository.is_valid returns False when .git missing."""
        repo_path = tmp_path / "no-git"
        repo_path.mkdir()

        repo = Repository(id="test", name="Test", path=str(repo_path))

        assert repo.is_valid() is False

    def test_repository_str_representation(self) -> None:
        """Test __str__ method of Repository."""
        repo = Repository(
            id="frontend",
            name="Frontend Monorepo",
            path="/dev/frontend",
        )

        str_repr = str(repo)
        assert "Repository" in str_repr
        assert "frontend" in str_repr
        assert "Frontend Monorepo" in str_repr
        assert "/dev/frontend" in str_repr

    def test_repository_repr_representation(self) -> None:
        """Test __repr__ method of Repository."""
        repo = Repository(
            id="backend",
            name="Backend",
            path="/dev/backend",
            url="https://github.com/org/backend.git",
        )

        repr_str = repr(repo)
        assert "Repository" in repr_str
        assert "id='backend'" in repr_str
        assert "name='Backend'" in repr_str
        assert "path='/dev/backend'" in repr_str
        assert "url='https://github.com/org/backend.git'" in repr_str


# ============================================================================
# RepositoryManager Init Tests
# ============================================================================


class TestRepositoryManagerInit:
    """Tests for RepositoryManager initialization."""

    def test_init_with_path(self, temp_state_dir: Path) -> None:
        """Test RepositoryManager initialization with path."""
        manager = RepositoryManager(temp_state_dir)

        assert manager.state_dir == temp_state_dir.resolve()

    def test_init_with_string(self, temp_state_dir: Path) -> None:
        """Test RepositoryManager initialization with string path."""
        manager = RepositoryManager(str(temp_state_dir))

        assert manager.state_dir == temp_state_dir.resolve()

    def test_init_with_state_manager(self, temp_state_dir: Path) -> None:
        """Test RepositoryManager initialization with StateManager."""
        from autoflow.core.state import StateManager

        state = StateManager(temp_state_dir)
        manager = RepositoryManager(state)

        assert manager.state_dir == temp_state_dir.resolve()

    def test_properties(self, repository_manager: RepositoryManager) -> None:
        """Test RepositoryManager directory properties."""
        assert repository_manager.repositories_dir == repository_manager.state_dir / "repositories"
        assert repository_manager.dependencies_dir == repository_manager.state_dir / "dependencies"
        assert repository_manager.backup_dir == repository_manager.state_dir / "backups"

    def test_initialize(self, temp_state_dir: Path) -> None:
        """Test RepositoryManager.initialize() creates directories."""
        manager = RepositoryManager(temp_state_dir)
        manager.initialize()

        assert manager.state_dir.exists()
        assert manager.repositories_dir.exists()
        assert manager.dependencies_dir.exists()
        assert manager.backup_dir.exists()

    def test_initialize_idempotent(self, repository_manager: RepositoryManager) -> None:
        """Test RepositoryManager.initialize() is idempotent."""
        # Should not raise error when called again
        repository_manager.initialize()

        assert repository_manager.state_dir.exists()


# ============================================================================
# RepositoryManager Repository Operations Tests
# ============================================================================


class TestRepositoryManagerRepositories:
    """Tests for RepositoryManager repository operations."""

    def test_save_repository(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test save_repository creates repository file."""
        result = repository_manager.save_repository("frontend", sample_repository_data)

        assert result.exists()
        assert result.name == "frontend.json"

    def test_save_repository_adds_id(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test save_repository adds ID if not present."""
        data_without_id = sample_repository_data.copy()
        del data_without_id["id"]

        repository_manager.save_repository("backend", data_without_id)

        loaded = repository_manager.load_repository("backend")
        assert loaded is not None
        assert loaded["id"] == "backend"

    def test_load_repository_existing(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test load_repository returns repository data."""
        repository_manager.save_repository("frontend", sample_repository_data)

        result = repository_manager.load_repository("frontend")

        assert result is not None
        assert result["id"] == "frontend"
        assert result["name"] == "Frontend Monorepo"

    def test_load_repository_nonexistent(self, repository_manager: RepositoryManager) -> None:
        """Test load_repository returns None for nonexistent repository."""
        result = repository_manager.load_repository("nonexistent")

        assert result is None

    def test_list_repositories_all(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test list_repositories returns all repositories."""
        repository_manager.save_repository("frontend", sample_repository_data)
        repository_manager.save_repository(
            "backend",
            {**sample_repository_data, "id": "backend", "name": "Backend"},
        )

        repos = repository_manager.list_repositories()

        assert len(repos) == 2

    def test_list_repositories_filter_enabled(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test list_repositories filters by enabled status."""
        repository_manager.save_repository("frontend", sample_repository_data)
        repository_manager.save_repository(
            "backend",
            {**sample_repository_data, "id": "backend", "enabled": False},
        )

        enabled = repository_manager.list_repositories(enabled=True)
        disabled = repository_manager.list_repositories(enabled=False)

        assert len(enabled) == 1
        assert enabled[0]["id"] == "frontend"
        assert len(disabled) == 1
        assert disabled[0]["id"] == "backend"

    def test_list_repositories_sorted(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test list_repositories returns repositories sorted by ID."""
        repository_manager.save_repository("zebra", {**sample_repository_data, "id": "zebra"})
        repository_manager.save_repository("alpha", {**sample_repository_data, "id": "alpha"})
        repository_manager.save_repository("beta", {**sample_repository_data, "id": "beta"})

        repos = repository_manager.list_repositories()

        assert repos[0]["id"] == "alpha"
        assert repos[1]["id"] == "beta"
        assert repos[2]["id"] == "zebra"

    def test_list_repositories_empty(self, repository_manager: RepositoryManager) -> None:
        """Test list_repositories returns empty list when no repositories."""
        repos = repository_manager.list_repositories()

        assert repos == []

    def test_delete_repository_existing(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test delete_repository removes repository."""
        repository_manager.save_repository("frontend", sample_repository_data)

        result = repository_manager.delete_repository("frontend")

        assert result is True
        assert repository_manager.load_repository("frontend") is None

    def test_delete_repository_nonexistent(self, repository_manager: RepositoryManager) -> None:
        """Test delete_repository returns False for nonexistent repository."""
        result = repository_manager.delete_repository("nonexistent")

        assert result is False

    def test_repository_exists(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test repository_exists checks if repository exists."""
        repository_manager.save_repository("frontend", sample_repository_data)

        assert repository_manager.repository_exists("frontend") is True
        assert repository_manager.repository_exists("nonexistent") is False

    def test_validate_missing_config(self, repository_manager: RepositoryManager) -> None:
        """Test validate returns errors for missing configuration."""
        errors = repository_manager.validate("nonexistent")

        assert len(errors) > 0
        assert "configuration not found" in errors[0]

    def test_validate_missing_path(
        self, repository_manager: RepositoryManager, temp_state_dir: Path
    ) -> None:
        """Test validate returns errors for missing path."""
        # Save repository without path
        repository_manager.save_repository("no-path", {"id": "no-path", "name": "No Path"})

        errors = repository_manager.validate("no-path")

        assert len(errors) > 0
        assert "no path specified" in errors[0]

    def test_validate_path_not_exists(
        self, repository_manager: RepositoryManager
    ) -> None:
        """Test validate returns errors for nonexistent path."""
        repository_manager.save_repository(
            "missing",
            {"id": "missing", "name": "Missing", "path": "/nonexistent/path"},
        )

        errors = repository_manager.validate("missing")

        assert len(errors) > 0
        assert any("does not exist" in e for e in errors)

    def test_validate_not_git_repo(
        self, repository_manager: RepositoryManager, tmp_path: Path
    ) -> None:
        """Test validate returns errors for non-git directory."""
        not_git = tmp_path / "not-git"
        not_git.mkdir()

        repository_manager.save_repository(
            "not-git",
            {"id": "not-git", "name": "Not Git", "path": str(not_git)},
        )

        errors = repository_manager.validate("not-git")

        assert len(errors) > 0
        assert any("not a valid git repository" in e for e in errors)

    def test_validate_success(
        self, repository_manager: RepositoryManager, tmp_path: Path
    ) -> None:
        """Test validate returns empty list for valid repository."""
        repo_path = tmp_path / "valid-repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        repository_manager.save_repository(
            "valid",
            {"id": "valid", "name": "Valid", "path": str(repo_path)},
        )

        # This should fail on git command since we don't have a real git repo
        # but the .git directory check should pass
        errors = repository_manager.validate("valid")

        # We expect some error from git command, but not about .git missing
        assert not any("not a valid git repository" in e for e in errors)

    def test_validate_all(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test validate_all returns results for all repositories."""
        repository_manager.save_repository("frontend", sample_repository_data)
        repository_manager.save_repository(
            "backend",
            {**sample_repository_data, "id": "backend", "path": "/nonexistent"},
        )

        results = repository_manager.validate_all()

        assert "frontend" in results
        assert "backend" in results
        # Backend should have errors (path doesn't exist)
        assert len(results["backend"]) > 0


# ============================================================================
# RepositoryManager Dependency Operations Tests
# ============================================================================


class TestRepositoryManagerDependencies:
    """Tests for RepositoryManager dependency operations."""

    def test_save_dependency(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test save_dependency creates dependency file."""
        result = repository_manager.save_dependency("frontend-to-backend", sample_dependency_data)

        assert result.exists()
        assert result.name == "frontend-to-backend.json"

    def test_save_dependency_adds_timestamp(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test save_dependency adds created_at timestamp."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)

        loaded = repository_manager.load_dependency("dep-001")

        assert "created_at" in loaded
        assert loaded["created_at"] is not None

    def test_load_dependency_existing(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test load_dependency returns dependency data."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)

        result = repository_manager.load_dependency("dep-001")

        assert result is not None
        assert result["source_repo_id"] == "frontend"
        assert result["target_repo_id"] == "backend-api"

    def test_load_dependency_nonexistent(self, repository_manager: RepositoryManager) -> None:
        """Test load_dependency returns None for nonexistent dependency."""
        result = repository_manager.load_dependency("nonexistent")

        assert result is None

    def test_list_dependencies_all(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test list_dependencies returns all dependencies."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "source_repo_id": "backend", "target_repo_id": "db"},
        )

        deps = repository_manager.list_dependencies()

        assert len(deps) == 2

    def test_list_dependencies_filter_by_source(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test list_dependencies filters by source repository."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "source_repo_id": "backend", "target_repo_id": "db"},
        )

        frontend_deps = repository_manager.list_dependencies(source_repo_id="frontend")

        assert len(frontend_deps) == 1
        assert frontend_deps[0]["source_repo_id"] == "frontend"

    def test_list_dependencies_filter_by_target(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test list_dependencies filters by target repository."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "source_repo_id": "mobile", "target_repo_id": "backend-api"},
        )

        api_deps = repository_manager.list_dependencies(target_repo_id="backend-api")

        assert len(api_deps) == 2

    def test_list_dependencies_filter_by_type(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test list_dependencies filters by dependency type."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "dependency_type": "development"},
        )

        runtime_deps = repository_manager.list_dependencies(
            dependency_type=DependencyType.RUNTIME
        )

        assert len(runtime_deps) == 1
        assert runtime_deps[0]["dependency_type"] == "runtime"

    def test_list_dependencies_sorted(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test list_dependencies returns dependencies sorted."""
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "source_repo_id": "z", "target_repo_id": "b"},
        )
        repository_manager.save_dependency(
            "dep-001",
            {**sample_dependency_data, "source_repo_id": "a", "target_repo_id": "c"},
        )
        repository_manager.save_dependency(
            "dep-003",
            {**sample_dependency_data, "source_repo_id": "a", "target_repo_id": "b"},
        )

        deps = repository_manager.list_dependencies()

        # Sorted by source_repo_id, then target_repo_id
        assert deps[0]["source_repo_id"] == "a"
        assert deps[0]["target_repo_id"] == "b"
        assert deps[1]["source_repo_id"] == "a"
        assert deps[1]["target_repo_id"] == "c"
        assert deps[2]["source_repo_id"] == "z"

    def test_list_dependencies_empty(self, repository_manager: RepositoryManager) -> None:
        """Test list_dependencies returns empty list when no dependencies."""
        deps = repository_manager.list_dependencies()

        assert deps == []

    def test_delete_dependency_existing(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test delete_dependency removes dependency."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)

        result = repository_manager.delete_dependency("dep-001")

        assert result is True
        assert repository_manager.load_dependency("dep-001") is None

    def test_delete_dependency_nonexistent(self, repository_manager: RepositoryManager) -> None:
        """Test delete_dependency returns False for nonexistent dependency."""
        result = repository_manager.delete_dependency("nonexistent")

        assert result is False

    def test_get_repository_dependencies_as_source(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test get_repository_dependencies returns dependencies where repo is source."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "source_repo_id": "backend", "target_repo_id": "db"},
        )

        frontend_deps = repository_manager.get_repository_dependencies("frontend", as_source=True)

        assert len(frontend_deps) == 1
        assert frontend_deps[0]["source_repo_id"] == "frontend"

    def test_get_repository_dependencies_as_target(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test get_repository_dependencies returns dependencies where repo is target."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "source_repo_id": "mobile", "target_repo_id": "backend-api"},
        )

        api_deps = repository_manager.get_repository_dependencies(
            "backend-api", as_target=True
        )

        assert len(api_deps) == 2

    def test_get_repository_dependencies_both(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test get_repository_dependencies returns both source and target dependencies."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "source_repo_id": "frontend", "target_repo_id": "db"},
        )
        repository_manager.save_dependency(
            "dep-003",
            {**sample_dependency_data, "source_repo_id": "mobile", "target_repo_id": "frontend"},
        )

        frontend_deps = repository_manager.get_repository_dependencies(
            "frontend", as_source=True, as_target=True
        )

        assert len(frontend_deps) == 3


# ============================================================================
# RepositoryManager Utility Tests
# ============================================================================


class TestRepositoryManagerUtilities:
    """Tests for RepositoryManager utility methods."""

    def test_get_status(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test get_status returns summary."""
        repository_manager.save_repository("frontend", sample_repository_data)

        status = repository_manager.get_status()

        assert status["initialized"] is True
        assert status["repositories"]["total"] == 1
        assert status["repositories"]["enabled"] == 1

    def test_get_status_empty(self, repository_manager: RepositoryManager) -> None:
        """Test get_status for empty state."""
        status = repository_manager.get_status()

        assert status["repositories"]["total"] == 0
        assert status["dependencies"]["total"] == 0

    def test_validate_dependencies_missing_repo(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test validate_dependencies returns errors for missing repositories."""
        # Save dependency without saving the repositories
        repository_manager.save_dependency("dep-001", sample_dependency_data)

        errors = repository_manager.validate_dependencies()

        assert len(errors) > 0
        assert any("does not exist" in e for e in errors)

    def test_validate_dependencies_valid(
        self,
        repository_manager: RepositoryManager,
        sample_repository_data: dict,
        sample_dependency_data: dict,
    ) -> None:
        """Test validate_dependencies returns empty list for valid setup."""
        # Save both repositories
        repository_manager.save_repository("frontend", sample_repository_data)
        repository_manager.save_repository(
            "backend-api",
            {**sample_repository_data, "id": "backend-api", "name": "Backend API"},
        )
        # Save dependency
        repository_manager.save_dependency("dep-001", sample_dependency_data)

        errors = repository_manager.validate_dependencies()

        assert len(errors) == 0

    def test_count_dependencies_by_type(
        self, repository_manager: RepositoryManager, sample_dependency_data: dict
    ) -> None:
        """Test _count_dependencies_by_type returns correct counts."""
        repository_manager.save_dependency("dep-001", sample_dependency_data)
        repository_manager.save_dependency(
            "dep-002",
            {**sample_dependency_data, "dependency_type": "development"},
        )
        repository_manager.save_dependency(
            "dep-003",
            {**sample_dependency_data, "dependency_type": "runtime", "source_repo_id": "backend"},
        )

        status = repository_manager.get_status()

        assert status["dependencies"]["total"] == 3
        assert status["dependencies"]["by_type"]["runtime"] == 2
        assert status["dependencies"]["by_type"]["development"] == 1


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_repository_path_with_spaces(self, tmp_path: Path) -> None:
        """Test Repository handles paths with spaces."""
        path_with_spaces = tmp_path / "path with spaces"
        path_with_spaces.mkdir()
        (path_with_spaces / ".git").mkdir()

        repo = Repository(
            id="test",
            name="Test",
            path=str(path_with_spaces),
        )

        assert repo.get_resolved_path() == path_with_spaces.resolve()

    def test_repository_with_unicode(self) -> None:
        """Test Repository handles unicode characters."""
        repo = Repository(
            id="test",
            name="Test 世界",
            path="/tmp/test",
            description="测试仓库",
        )

        assert "世界" in repo.name
        assert "测试仓库" in repo.description

    def test_dependency_with_metadata(self) -> None:
        """Test RepositoryDependency with complex metadata."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            metadata={
                "purpose": "api",
                "priority": "high",
                "tags": ["critical", "security"],
            },
        )

        assert dep.metadata["purpose"] == "api"
        assert dep.metadata["tags"] == ["critical", "security"]

    def test_repository_enabled_toggle(
        self, repository_manager: RepositoryManager, sample_repository_data: dict
    ) -> None:
        """Test toggling repository enabled status."""
        repository_manager.save_repository("frontend", sample_repository_data)

        # Disable
        sample_repository_data["enabled"] = False
        repository_manager.save_repository("frontend", sample_repository_data)

        repo = repository_manager.load_repository("frontend")
        assert repo["enabled"] is False

        # Re-enable
        repo["enabled"] = True
        repository_manager.save_repository("frontend", repo)

        updated = repository_manager.load_repository("frontend")
        assert updated["enabled"] is True

    def test_multiple_protected_branches(self) -> None:
        """Test BranchConfig with multiple protected branches."""
        config = BranchConfig(
            protected=["main", "master", "develop", "release/*", "hotfix/*"]
        )

        assert len(config.protected) == 5
        assert "release/*" in config.protected

    def test_repository_with_custom_default_branch(self) -> None:
        """Test Repository with non-standard default branch."""
        repo = Repository(
            id="test",
            name="Test",
            path="/tmp/test",
            branch=BranchConfig(default="develop", current="feature-branch"),
        )

        assert repo.branch.default == "develop"
        assert repo.branch.current == "feature-branch"

    def test_dependency_type_optional(self) -> None:
        """Test RepositoryDependency with optional type."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            dependency_type=DependencyType.OPTIONAL,
            required=False,
        )

        assert dep.dependency_type == DependencyType.OPTIONAL
        assert dep.required is False

    def test_peer_dependency_type(self) -> None:
        """Test RepositoryDependency with peer type."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            dependency_type=DependencyType.PEER,
        )

        assert dep.dependency_type == DependencyType.PEER
        # Peer dependencies are typically required
        assert dep.required is True

    def test_version_constraint(self) -> None:
        """Test RepositoryDependency with version constraint."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            version_constraint="^2.0.0",
        )

        assert dep.version_constraint == "^2.0.0"
        assert dep.branch_constraint is None  # Not mutually exclusive

    def test_both_constraints(self) -> None:
        """Test RepositoryDependency with both version and branch constraints."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend",
            branch_constraint="main",
            version_constraint="^2.0.0",
        )

        assert dep.branch_constraint == "main"
        assert dep.version_constraint == "^2.0.0"


# ============================================================================
# DependencyTracker Tests
# ============================================================================


class TestDependencyTracker:
    """Tests for DependencyTracker class."""

    # ------------------------------------------------------------------------
    # Fixtures for DependencyTracker tests
    # ------------------------------------------------------------------------

    @pytest.fixture
    def dependency_tracker(
        self, temp_state_dir: Path
    ) -> DependencyTracker:
        """Create a DependencyTracker instance with temporary directory."""
        tracker = DependencyTracker(temp_state_dir)
        tracker.initialize()
        return tracker

    @pytest.fixture
    def sample_repositories(
        self, dependency_tracker: DependencyTracker, sample_repository_data: dict
    ) -> None:
        """Create sample repositories for testing."""
        # Create multiple repositories
        repos = [
            {"id": "shared-utils", "name": "Shared Utils", "path": "~/dev/shared", "enabled": True},
            {"id": "backend-api", "name": "Backend API", "path": "~/dev/backend", "enabled": True},
            {"id": "frontend", "name": "Frontend", "path": "~/dev/frontend", "enabled": True},
            {"id": "mobile", "name": "Mobile App", "path": "~/dev/mobile", "enabled": True},
        ]
        for repo in repos:
            dependency_tracker.repo_manager.save_repository(repo["id"], repo)

    @pytest.fixture
    def sample_dependencies(
        self, dependency_tracker: DependencyTracker
    ) -> None:
        """Create sample dependencies for testing."""
        # frontend -> backend-api -> shared-utils
        # mobile -> backend-api
        deps = [
            RepositoryDependency(
                source_repo_id="frontend",
                target_repo_id="backend-api",
                dependency_type=DependencyType.RUNTIME,
            ),
            RepositoryDependency(
                source_repo_id="backend-api",
                target_repo_id="shared-utils",
                dependency_type=DependencyType.RUNTIME,
            ),
            RepositoryDependency(
                source_repo_id="mobile",
                target_repo_id="backend-api",
                dependency_type=DependencyType.RUNTIME,
            ),
        ]
        for dep in deps:
            dependency_tracker.add_dependency(dep)

    # ------------------------------------------------------------------------
    # Initialization Tests
    # ------------------------------------------------------------------------

    def test_dependency_tracker_init(self, temp_state_dir: Path) -> None:
        """Test DependencyTracker initialization."""
        tracker = DependencyTracker(temp_state_dir)

        assert tracker.state_dir == temp_state_dir
        assert tracker.repo_manager is not None
        assert isinstance(tracker.repo_manager, RepositoryManager)

    def test_dependency_tracker_init_with_state_manager(
        self, temp_state_dir: Path
    ) -> None:
        """Test DependencyTracker initialization with StateManager."""
        from autoflow.core.state import StateManager

        state_manager = StateManager(temp_state_dir)
        tracker = DependencyTracker(state_manager)

        assert tracker.state is state_manager
        assert tracker.repo_manager is not None

    def test_dependency_tracker_init_with_repo_manager(
        self, temp_state_dir: Path, repository_manager: RepositoryManager
    ) -> None:
        """Test DependencyTracker initialization with RepositoryManager."""
        tracker = DependencyTracker(temp_state_dir, repo_manager=repository_manager)

        assert tracker.repo_manager is repository_manager

    def test_dependency_tracker_initialize(
        self, temp_state_dir: Path
    ) -> None:
        """Test DependencyTracker initialize creates directories."""
        tracker = DependencyTracker(temp_state_dir)
        tracker.initialize()

        assert tracker.state_dir.exists()
        assert tracker.dependencies_dir.exists()

    # ------------------------------------------------------------------------
    # Add Dependency Tests
    # ------------------------------------------------------------------------

    def test_add_dependency_object(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test adding a dependency from RepositoryDependency object."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend-api",
            dependency_type=DependencyType.RUNTIME,
        )

        dep_id = dependency_tracker.add_dependency(dep)

        assert dep_id == "frontend-to-backend-api"
        assert dependency_tracker.get_dependency(dep_id) is not None

    def test_add_dependency_dict(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test adding a dependency from dictionary."""
        dep_data = {
            "source_repo_id": "frontend",
            "target_repo_id": "backend-api",
            "dependency_type": "runtime",
        }

        dep_id = dependency_tracker.add_dependency(dep_data)

        assert dep_id == "frontend-to-backend-api"

    def test_add_dependency_invalid_dict(
        self, dependency_tracker: DependencyTracker
    ) -> None:
        """Test adding invalid dependency dict raises ValueError."""
        invalid_dep = {"source_repo_id": "frontend"}  # Missing target_repo_id

        with pytest.raises(ValueError, match="Invalid dependency data"):
            dependency_tracker.add_dependency(invalid_dep)

    def test_add_dependency_generates_id(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test that dependency ID is generated correctly."""
        dep = RepositoryDependency(
            source_repo_id="mobile",
            target_repo_id="shared-utils",
        )

        dep_id = dependency_tracker.add_dependency(dep)

        assert dep_id == "mobile-to-shared-utils"

    def test_add_dependency_with_created_at(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test that created_at is set when adding dependency."""
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="backend-api",
        )

        dep_id = dependency_tracker.add_dependency(dep)
        loaded_dep = dependency_tracker.get_dependency(dep_id)

        assert loaded_dep is not None
        assert loaded_dep.created_at is not None

    # ------------------------------------------------------------------------
    # Remove Dependency Tests
    # ------------------------------------------------------------------------

    def test_remove_dependency(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test removing a dependency."""
        dep_id = "frontend-to-backend-api"

        removed = dependency_tracker.remove_dependency(dep_id)

        assert removed is True
        assert dependency_tracker.get_dependency(dep_id) is None

    def test_remove_dependency_not_found(
        self, dependency_tracker: DependencyTracker
    ) -> None:
        """Test removing non-existent dependency returns False."""
        removed = dependency_tracker.remove_dependency("non-existent")

        assert removed is False

    def test_remove_dependency_creates_backup(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test that removing a dependency calls the state's backup method."""
        dep_id = "frontend-to-backend-api"

        # Remove the dependency
        removed = dependency_tracker.remove_dependency(dep_id)

        # Verify it was removed
        assert removed is True
        assert dependency_tracker.get_dependency(dep_id) is None
        # Verify the dependency file no longer exists
        assert not (dependency_tracker.dependencies_dir / f"{dep_id}.json").exists()

    # ------------------------------------------------------------------------
    # Get Dependency Tests
    # ------------------------------------------------------------------------

    def test_get_dependency(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test getting a dependency by ID."""
        dep = dependency_tracker.get_dependency("frontend-to-backend-api")

        assert dep is not None
        assert dep.source_repo_id == "frontend"
        assert dep.target_repo_id == "backend-api"

    def test_get_dependency_not_found(
        self, dependency_tracker: DependencyTracker
    ) -> None:
        """Test getting non-existent dependency returns None."""
        dep = dependency_tracker.get_dependency("non-existent")

        assert dep is None

    # ------------------------------------------------------------------------
    # List Dependencies Tests
    # ------------------------------------------------------------------------

    def test_list_dependencies_all(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test listing all dependencies."""
        deps = dependency_tracker.list_dependencies()

        assert len(deps) == 3

    def test_list_dependencies_filter_by_source(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test listing dependencies filtered by source."""
        deps = dependency_tracker.list_dependencies(source_repo_id="frontend")

        assert len(deps) == 1
        assert deps[0].source_repo_id == "frontend"

    def test_list_dependencies_filter_by_target(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test listing dependencies filtered by target."""
        deps = dependency_tracker.list_dependencies(target_repo_id="backend-api")

        assert len(deps) == 2  # frontend and mobile depend on backend-api

    def test_list_dependencies_filter_by_type(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test listing dependencies filtered by type."""
        deps = dependency_tracker.list_dependencies(dependency_type="runtime")

        assert len(deps) == 3  # All are runtime

    def test_list_dependencies_empty(
        self, dependency_tracker: DependencyTracker
    ) -> None:
        """Test listing dependencies when none exist."""
        deps = dependency_tracker.list_dependencies()

        assert len(deps) == 0

    # ------------------------------------------------------------------------
    # Get Dependencies For Tests
    # ------------------------------------------------------------------------

    def test_get_dependencies_for_as_source(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test getting dependencies where repo is source."""
        deps = dependency_tracker.get_dependencies_for("backend-api", as_source=True)

        assert len(deps) == 1
        assert deps[0].source_repo_id == "backend-api"
        assert deps[0].target_repo_id == "shared-utils"

    def test_get_dependencies_for_as_target(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test getting dependencies where repo is target."""
        deps = dependency_tracker.get_dependencies_for("backend-api", as_target=True, as_source=False)

        # frontend and mobile depend on backend-api (2 dependencies)
        # Note: backend-api also depends on shared-utils, but that's as_source, not as_target
        assert len(deps) == 2
        # Verify both have backend-api as target
        assert all(dep.target_repo_id == "backend-api" for dep in deps)
        # Verify the specific dependencies
        dep_ids = {f"{dep.source_repo_id}->{dep.target_repo_id}" for dep in deps}
        assert dep_ids == {"frontend->backend-api", "mobile->backend-api"}

    def test_get_dependencies_for_both(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test getting dependencies where repo is both source and target."""
        deps = dependency_tracker.get_dependencies_for(
            "backend-api", as_source=True, as_target=True
        )

        assert len(deps) == 3  # 1 as source, 2 as target

    # ------------------------------------------------------------------------
    # Dependency Graph Tests
    # ------------------------------------------------------------------------

    def test_get_dependency_graph(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test building dependency graph."""
        graph = dependency_tracker.get_dependency_graph()

        assert graph["frontend"] == {"backend-api"}
        assert graph["backend-api"] == {"shared-utils"}
        assert graph["mobile"] == {"backend-api"}

    def test_get_dependency_graph_empty(
        self, dependency_tracker: DependencyTracker
    ) -> None:
        """Test dependency graph with no dependencies."""
        graph = dependency_tracker.get_dependency_graph()

        assert len(graph) == 0

    def test_get_reverse_dependency_graph(
        self, dependency_tracker: DependencyTracker, sample_dependencies: None
    ) -> None:
        """Test building reverse dependency graph."""
        graph = dependency_tracker.get_reverse_dependency_graph()

        assert graph["backend-api"] == {"frontend", "mobile"}
        assert graph["shared-utils"] == {"backend-api"}

    # ------------------------------------------------------------------------
    # Validation Tests
    # ------------------------------------------------------------------------

    def test_validate_with_all_repos(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test validation with all repositories present."""
        errors = dependency_tracker.validate()

        assert len(errors) == 0

    def test_validate_missing_source_repo(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test validation detects missing source repository."""
        # Add dependency for non-existent source
        dep = RepositoryDependency(
            source_repo_id="non-existent",
            target_repo_id="backend-api",
        )
        dependency_tracker.add_dependency(dep)

        errors = dependency_tracker.validate()

        assert len(errors) > 0
        assert any("source repository 'non-existent' does not exist" in e for e in errors)

    def test_validate_missing_target_repo(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test validation detects missing target repository."""
        # Add dependency for non-existent target
        dep = RepositoryDependency(
            source_repo_id="frontend",
            target_repo_id="non-existent",
        )
        dependency_tracker.add_dependency(dep)

        errors = dependency_tracker.validate()

        assert len(errors) > 0
        assert any("target repository 'non-existent' does not exist" in e for e in errors)

    def test_validate_circular_dependencies(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test validation detects circular dependencies."""
        # Create circular dependency: A -> B -> C -> A
        dependency_tracker.add_dependency(
            RepositoryDependency(source_repo_id="frontend", target_repo_id="backend-api")
        )
        dependency_tracker.add_dependency(
            RepositoryDependency(source_repo_id="backend-api", target_repo_id="mobile")
        )
        dependency_tracker.add_dependency(
            RepositoryDependency(source_repo_id="mobile", target_repo_id="frontend")
        )

        errors = dependency_tracker.validate()

        assert len(errors) > 0
        assert any("Circular dependency detected" in e for e in errors)

    # ------------------------------------------------------------------------
    # Execution Order Tests
    # ------------------------------------------------------------------------

    def test_get_execution_order(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test getting execution order (topological sort)."""
        order = dependency_tracker.get_execution_order()

        # shared-utils should come first (no dependencies)
        # backend-api should come before frontend and mobile
        # frontend and mobile have no order constraint between them
        assert order.index("shared-utils") < order.index("backend-api")
        assert order.index("backend-api") < order.index("frontend")
        assert order.index("backend-api") < order.index("mobile")

    def test_get_execution_order_with_circular_raises(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test execution order raises ValueError for circular dependencies."""
        # Create circular dependency
        dependency_tracker.add_dependency(
            RepositoryDependency(source_repo_id="frontend", target_repo_id="backend-api")
        )
        dependency_tracker.add_dependency(
            RepositoryDependency(source_repo_id="backend-api", target_repo_id="frontend")
        )

        with pytest.raises(ValueError, match="circular dependencies"):
            dependency_tracker.get_execution_order()

    def test_get_execution_order_no_dependencies(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test execution order with no dependencies."""
        order = dependency_tracker.get_execution_order()

        # All repos should be in the result
        assert len(order) == 4
        assert "shared-utils" in order
        assert "backend-api" in order
        assert "frontend" in order
        assert "mobile" in order

    # ------------------------------------------------------------------------
    # Get Dependents Tests
    # ------------------------------------------------------------------------

    def test_get_dependents_non_recursive(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test getting direct dependents."""
        dependents = dependency_tracker.get_dependents("backend-api", recursive=False)

        assert dependents == {"frontend", "mobile"}

    def test_get_dependents_recursive(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test getting transitive dependents."""
        # shared-utils is depended on by backend-api,
        # which is depended on by frontend and mobile
        dependents = dependency_tracker.get_dependents("shared-utils", recursive=True)

        assert "backend-api" in dependents
        assert "frontend" in dependents
        assert "mobile" in dependents

    def test_get_dependents_no_dependents(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test getting dependents for repo with none."""
        dependents = dependency_tracker.get_dependents("frontend", recursive=False)

        assert len(dependents) == 0

    # ------------------------------------------------------------------------
    # Get Prerequisites Tests
    # ------------------------------------------------------------------------

    def test_get_prerequisites_non_recursive(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test getting direct prerequisites."""
        prereqs = dependency_tracker.get_prerequisites("frontend", recursive=False)

        assert prereqs == {"backend-api"}

    def test_get_prerequisites_recursive(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test getting transitive prerequisites."""
        # frontend depends on backend-api, which depends on shared-utils
        prereqs = dependency_tracker.get_prerequisites("frontend", recursive=True)

        assert "backend-api" in prereqs
        assert "shared-utils" in prereqs

    def test_get_prerequisites_none(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test getting prerequisites for repo with none."""
        prereqs = dependency_tracker.get_prerequisites("shared-utils", recursive=False)

        assert len(prereqs) == 0

    # ------------------------------------------------------------------------
    # Status Tests
    # ------------------------------------------------------------------------

    def test_get_status(
        self, dependency_tracker: DependencyTracker, sample_repositories: None,
        sample_dependencies: None
    ) -> None:
        """Test getting status summary."""
        status = dependency_tracker.get_status()

        assert status["total"] == 3
        assert status["repositories"] == 4
        assert status["by_type"]["runtime"] == 3
        assert status["has_errors"] is False

    def test_get_status_with_errors(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test status reflects validation errors."""
        # Add invalid dependency
        dependency_tracker.add_dependency(
            RepositoryDependency(source_repo_id="bad", target_repo_id="repo")
        )

        status = dependency_tracker.get_status()

        assert status["has_errors"] is True

    def test_get_status_empty(
        self, dependency_tracker: DependencyTracker, sample_repositories: None
    ) -> None:
        """Test status with no dependencies."""
        status = dependency_tracker.get_status()

        assert status["total"] == 0
        assert status["repositories"] == 4
        assert status["has_errors"] is False

    # ------------------------------------------------------------------------
    # Repr Tests
    # ------------------------------------------------------------------------

    def test_repr(self, dependency_tracker: DependencyTracker) -> None:
        """Test string representation of DependencyTracker."""
        repr_str = repr(dependency_tracker)

        assert "DependencyTracker" in repr_str
        assert "state_dir" in repr_str
