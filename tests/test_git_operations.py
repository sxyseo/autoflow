"""
Unit Tests for Git Operations

Tests the GitOperations, GitError, and related classes for git utilities.

These tests mock subprocess execution to avoid requiring actual
git repositories or git commands in the test environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from autoflow.git.operations import (
    BranchInfo,
    BranchType,
    GitError,
    GitOperations,
    RebaseResult,
    create_git_operations,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_repo_path(tmp_path: Path) -> Path:
    """Create a mock repository path."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    return repo


@pytest.fixture
def mock_subprocess_success() -> MagicMock:
    """Mock subprocess that returns success."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = "success"
    mock.stderr = ""
    return mock


@pytest.fixture
def mock_completed_process() -> MagicMock:
    """Mock CompletedProcess for subprocess.run."""
    mock = MagicMock()

    def create_process(
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> MagicMock:
        process = MagicMock()
        process.returncode = returncode
        process.stdout = stdout
        process.stderr = stderr
        return process

    mock.side_effect = create_process
    return mock


@pytest.fixture
def git_ops(mock_repo_path: Path) -> GitOperations:
    """Create a GitOperations instance with mocked git repo check."""
    with pytest.MonkeyPatch.context() as m:
        # Mock the git repo check to avoid actual git validation
        m.setattr(Path, "exists", lambda self: True)
        git = GitOperations(repo_path=mock_repo_path)
        return git


# ============================================================================
# GitError Tests
# ============================================================================


class TestGitError:
    """Tests for GitError exception."""

    def test_git_error_init(self) -> None:
        """Test GitError initialization."""
        error = GitError("Test error")

        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.exit_code is None
        assert error.command is None
        assert error.repo_path is None

    def test_git_error_with_exit_code(self) -> None:
        """Test GitError with exit code."""
        error = GitError("Failed", exit_code=1)

        assert error.exit_code == 1

    def test_git_error_with_command(self) -> None:
        """Test GitError with command."""
        error = GitError("Git failed", command=["git", "status"])

        assert error.command == ["git", "status"]

    def test_git_error_with_repo_path(self) -> None:
        """Test GitError with repo path."""
        path = Path("/test/repo")
        error = GitError("Not a repo", repo_path=path)

        assert error.repo_path == path

    def test_git_error_all_fields(self) -> None:
        """Test GitError with all fields."""
        error = GitError(
            message="Comprehensive error",
            exit_code=128,
            command=["git", "rev-parse"],
            repo_path=Path("/repo"),
        )

        assert error.message == "Comprehensive error"
        assert error.exit_code == 128
        assert error.command == ["git", "rev-parse"]
        assert error.repo_path == Path("/repo")


# ============================================================================
# BranchInfo Tests
# ============================================================================


class TestBranchInfo:
    """Tests for BranchInfo dataclass."""

    def test_branch_info_init(self) -> None:
        """Test BranchInfo initialization."""
        info = BranchInfo(name="main")

        assert info.name == "main"
        assert info.branch_type == BranchType.OTHER
        assert info.is_current is False
        assert info.is_remote is False
        assert info.commit_sha is None
        assert info.commit_message is None

    def test_branch_info_with_type(self) -> None:
        """Test BranchInfo with branch type."""
        info = BranchInfo(
            name="feature/test",
            branch_type=BranchType.FEATURE,
        )

        assert info.branch_type == BranchType.FEATURE

    def test_branch_info_current_branch(self) -> None:
        """Test BranchInfo for current branch."""
        info = BranchInfo(
            name="main",
            is_current=True,
        )

        assert info.is_current is True

    def test_branch_info_remote_branch(self) -> None:
        """Test BranchInfo for remote branch."""
        info = BranchInfo(
            name="origin/main",
            is_remote=True,
        )

        assert info.is_remote is True

    def test_branch_info_with_commit(self) -> None:
        """Test BranchInfo with commit info."""
        info = BranchInfo(
            name="main",
            commit_sha="abc123",
            commit_message="Initial commit",
        )

        assert info.commit_sha == "abc123"
        assert info.commit_message == "Initial commit"

    def test_branch_info_repr_current(self) -> None:
        """Test BranchInfo repr for current branch."""
        info = BranchInfo(
            name="main",
            branch_type=BranchType.MAIN,
            is_current=True,
        )
        repr_str = repr(info)

        assert "*" in repr_str
        assert "main" in repr_str
        assert "main" in repr_str

    def test_branch_info_repr_remote(self) -> None:
        """Test BranchInfo repr for remote branch."""
        info = BranchInfo(
            name="origin/main",
            is_remote=True,
        )
        repr_str = repr(info)

        assert "remotes/" in repr_str


# ============================================================================
# RebaseResult Tests
# ============================================================================


class TestRebaseResult:
    """Tests for RebaseResult dataclass."""

    def test_rebase_result_init_default(self) -> None:
        """Test RebaseResult initialization with defaults."""
        result = RebaseResult()

        assert result.success is False
        assert result.has_conflicts is False
        assert result.current_commit is None
        assert result.conflicted_files == []
        assert result.error is None

    def test_rebase_result_success(self) -> None:
        """Test RebaseResult for successful rebase."""
        result = RebaseResult(
            success=True,
            current_commit="abc123",
        )

        assert result.success is True
        assert result.current_commit == "abc123"
        assert result.has_conflicts is False

    def test_rebase_result_with_conflicts(self) -> None:
        """Test RebaseResult with conflicts."""
        result = RebaseResult(
            success=False,
            has_conflicts=True,
            conflicted_files=["file1.py", "file2.py"],
            error="Merge conflicts detected",
        )

        assert result.success is False
        assert result.has_conflicts is True
        assert len(result.conflicted_files) == 2
        assert "file1.py" in result.conflicted_files
        assert result.error == "Merge conflicts detected"

    def test_rebase_result_conflicted_files_auto_init(self) -> None:
        """Test that conflicted_files is initialized to empty list."""
        result = RebaseResult()

        # Should not raise AttributeError
        result.conflicted_files.append("test.py")

        assert len(result.conflicted_files) == 1


# ============================================================================
# GitOperations Init Tests
# ============================================================================


class TestGitOperationsInit:
    """Tests for GitOperations initialization."""

    def test_init_with_path(self, mock_repo_path: Path) -> None:
        """Test initialization with repo path."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "exists", lambda self: True)
            git = GitOperations(repo_path=mock_repo_path)

            assert git.repo_path == mock_repo_path
            assert git.verbose is False

    def test_init_default_path(self) -> None:
        """Test initialization with default path."""
        with pytest.MonkeyPatch.context() as m:
            # Mock both the git check and current directory
            m.setattr(Path, "exists", lambda self: True)
            m.setattr(Path, "cwd", lambda: Path("/test"))

            git = GitOperations()

            assert git.repo_path == Path("/test")

    def test_init_with_verbose(self, mock_repo_path: Path) -> None:
        """Test initialization with verbose mode."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "exists", lambda self: True)
            git = GitOperations(repo_path=mock_repo_path, verbose=True)

            assert git.verbose is True

    def test_init_not_a_git_repo(self, tmp_path: Path) -> None:
        """Test initialization fails when not a git repo."""
        with pytest.MonkeyPatch.context() as m:
            # Mock .git directory not existing
            def mock_exists(self):
                if self.name == ".git":
                    return False
                return True

            m.setattr(Path, "exists", mock_exists)

            with pytest.raises(GitError) as exc_info:
                GitOperations(repo_path=tmp_path)

            assert "Not a git repository" in str(exc_info.value)


# ============================================================================
# GitOperations _run_git Tests
# ============================================================================


class TestGitOperationsRunGit:
    """Tests for GitOperations._run_git method."""

    def test_run_git_success(
        self,
        git_ops: GitOperations,
        mock_completed_process: MagicMock,
    ) -> None:
        """Test running git command successfully."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "output"
        mock_process.stderr = ""

        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                return mock_process
            m.setattr("subprocess.run", mock_run)
            result = git_ops._run_git(["status"])

            assert result.returncode == 0
            assert result.stdout == "output"

    def test_run_git_failure_raises(
        self,
        git_ops: GitOperations,
    ) -> None:
        """Test that git command failure raises GitError."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                # Simulate CalledProcessError
                import subprocess
                raise subprocess.CalledProcessError(
                    1, ["git", "status"], stderr="error"
                )
            m.setattr("subprocess.run", mock_run)

            with pytest.raises(GitError) as exc_info:
                git_ops._run_git(["status"], check=True)

            assert "Git command failed" in str(exc_info.value)

    def test_run_git_check_false(
        self,
        git_ops: GitOperations,
    ) -> None:
        """Test running git command with check=False."""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = ""
        mock_process.stderr = "error"

        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                return mock_process
            m.setattr("subprocess.run", mock_run)
            result = git_ops._run_git(["status"], check=False)

            assert result.returncode == 1

    def test_run_git_not_found(
        self,
        git_ops: GitOperations,
    ) -> None:
        """Test that missing git raises GitError."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                raise FileNotFoundError("git not found")
            m.setattr("subprocess.run", mock_run)

            with pytest.raises(GitError) as exc_info:
                git_ops._run_git(["status"])

            assert "Git not found" in str(exc_info.value)


# ============================================================================
# GitOperations get_base_branch Tests
# ============================================================================


class TestGitOperationsGetBaseBranch:
    """Tests for GitOperations.get_base_branch method."""

    def test_get_base_branch_main(self, git_ops: GitOperations) -> None:
        """Test detecting main branch."""
        with pytest.MonkeyPatch.context() as m:
            # Mock successful rev-parse for main
            def mock_run(self, args, **kwargs):
                result = MagicMock()
                if "main" in args:
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                else:
                    result.returncode = 128
                return result

            m.setattr(GitOperations, "_run_git", mock_run)
            branch = git_ops.get_base_branch()

            assert branch == "main"

    def test_get_base_branch_master(self, git_ops: GitOperations) -> None:
        """Test detecting master branch."""
        with pytest.MonkeyPatch.context() as m:
            call_count = [0]

            def mock_run(self, args, **kwargs):
                result = MagicMock()
                call_count[0] += 1
                # First call (main) fails, second (master) succeeds
                if "main" in args:
                    result.returncode = 128
                elif "master" in args:
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                return result

            m.setattr(GitOperations, "_run_git", mock_run)
            branch = git_ops.get_base_branch()

            assert branch == "master"
            assert call_count[0] == 2

    def test_get_base_branch_develop(self, git_ops: GitOperations) -> None:
        """Test detecting develop branch."""
        with pytest.MonkeyPatch.context() as m:
            call_count = [0]

            def mock_run(self, args, **kwargs):
                result = MagicMock()
                call_count[0] += 1
                # main and master fail, develop succeeds
                if "develop" in args:
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                else:
                    result.returncode = 128
                return result

            m.setattr(GitOperations, "_run_git", mock_run)
            branch = git_ops.get_base_branch()

            assert branch == "develop"

    def test_get_base_branch_fallback(self, git_ops: GitOperations) -> None:
        """Test fallback to default when no branch found."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(self, args, **kwargs):
                result = MagicMock()
                result.returncode = 128
                return result

            m.setattr(GitOperations, "_run_git", mock_run)

            # Mock get_current_branch to also fail
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: (_ for _ in ()).throw(GitError("No branch")),
            )

            branch = git_ops.get_base_branch()

            assert branch == "main"


# ============================================================================
# GitOperations get_current_branch Tests
# ============================================================================


class TestGitOperationsGetCurrentBranch:
    """Tests for GitOperations.get_current_branch method."""

    def test_get_current_branch_success(self, git_ops: GitOperations) -> None:
        """Test getting current branch successfully."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "feature/test-branch\n"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)
            branch = git_ops.get_current_branch()

            assert branch == "feature/test-branch"

    def test_get_current_branch_detached_head(self, git_ops: GitOperations) -> None:
        """Test error when in detached HEAD state."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "\n"  # Empty output = detached HEAD
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            with pytest.raises(GitError) as exc_info:
                git_ops.get_current_branch()

            assert "Unable to determine current branch" in str(exc_info.value)


# ============================================================================
# GitOperations _classify_branch Tests
# ============================================================================


class TestGitOperationsClassifyBranch:
    """Tests for GitOperations._classify_branch method."""

    def test_classify_main(self, git_ops: GitOperations) -> None:
        """Test classifying main branch."""
        assert git_ops._classify_branch("main") == BranchType.MAIN
        assert git_ops._classify_branch("master") == BranchType.MAIN

    def test_classify_develop(self, git_ops: GitOperations) -> None:
        """Test classifying develop branch."""
        assert git_ops._classify_branch("develop") == BranchType.DEVELOP

    def test_classify_feature(self, git_ops: GitOperations) -> None:
        """Test classifying feature branch."""
        assert git_ops._classify_branch("feature/test") == BranchType.FEATURE
        assert git_ops._classify_branch("feature/abc-123") == BranchType.FEATURE

    def test_classify_bugfix(self, git_ops: GitOperations) -> None:
        """Test classifying bugfix branch."""
        assert git_ops._classify_branch("bugfix/fix") == BranchType.BUGFIX

    def test_classify_hotfix(self, git_ops: GitOperations) -> None:
        """Test classifying hotfix branch."""
        assert git_ops._classify_branch("hotfix/urgent") == BranchType.HOTFIX

    def test_classify_other(self, git_ops: GitOperations) -> None:
        """Test classifying other branch."""
        assert git_ops._classify_branch("random-branch") == BranchType.OTHER
        assert git_ops._classify_branch("release/v1.0") == BranchType.OTHER

    def test_classify_remote_branch(self, git_ops: GitOperations) -> None:
        """Test classifying remote branch removes prefix."""
        assert (
            git_ops._classify_branch("remotes/origin/main")
            == BranchType.MAIN
        )
        assert (
            git_ops._classify_branch("remotes/origin/feature/test")
            == BranchType.FEATURE
        )


# ============================================================================
# GitOperations get_branch_info Tests
# ============================================================================


class TestGitOperationsGetBranchInfo:
    """Tests for GitOperations.get_branch_info method."""

    def test_get_branch_info_current(
        self,
        git_ops: GitOperations,
    ) -> None:
        """Test getting info for current branch."""
        with pytest.MonkeyPatch.context() as m:
            # Mock get_current_branch
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: "feature/test",
            )

            info = git_ops.get_branch_info()

            assert info.name == "feature/test"
            assert info.branch_type == BranchType.FEATURE
            assert info.is_current is True

    def test_get_branch_info_specific(self, git_ops: GitOperations) -> None:
        """Test getting info for specific branch."""
        with pytest.MonkeyPatch.context() as m:
            # Mock get_current_branch to avoid calling git
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: "main",
            )
            info = git_ops.get_branch_info("main")

            assert info.name == "main"
            assert info.branch_type == BranchType.MAIN
            assert info.is_current is True

    def test_get_branch_info_with_commit(self, git_ops: GitOperations) -> None:
        """Test getting branch info with commit details."""
        with pytest.MonkeyPatch.context() as m:
            # Mock get_current_branch
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: "main",
            )

            def mock_run(self, args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "abc123|Test commit message"
                result.stderr = ""
                return result

            m.setattr(GitOperations, "_run_git", mock_run)

            info = git_ops.get_branch_info("main")

            assert info.commit_sha == "abc123"
            assert info.commit_message == "Test commit message"

    def test_get_branch_info_remote(self, git_ops: GitOperations) -> None:
        """Test getting info for remote branch."""
        with pytest.MonkeyPatch.context() as m:
            # Mock get_current_branch to avoid calling git
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: "main",
            )
            info = git_ops.get_branch_info("remotes/origin/main")

            assert info.name == "remotes/origin/main"
            assert info.is_remote is True


# ============================================================================
# GitOperations has_merge_conflicts Tests
# ============================================================================


class TestGitOperationsHasMergeConflicts:
    """Tests for GitOperations.has_merge_conflicts method."""

    def test_has_merge_conflicts_true(self, git_ops: GitOperations) -> None:
        """Test detecting merge conflicts."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "UU file.py\nAA other.py"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            assert git_ops.has_merge_conflicts() is True

    def test_has_merge_conflicts_false(self, git_ops: GitOperations) -> None:
        """Test no merge conflicts."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "M file.py"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            assert git_ops.has_merge_conflicts() is False

    def test_has_merge_conflicts_error(self, git_ops: GitOperations) -> None:
        """Test git error returns False."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                import subprocess
                raise subprocess.CalledProcessError(
                    1, ["git", "status"], stderr="error"
                )
            m.setattr("subprocess.run", mock_run)

            assert git_ops.has_merge_conflicts() is False


# ============================================================================
# GitOperations get_conflicted_files Tests
# ============================================================================


class TestGitOperationsGetConflictedFiles:
    """Tests for GitOperations.get_conflicted_files method."""

    def test_get_conflicted_files_multiple(
        self,
        git_ops: GitOperations,
    ) -> None:
        """Test getting multiple conflicted files."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "file1.py\nfile2.py\nfile3.py"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            files = git_ops.get_conflicted_files()

            assert len(files) == 3
            assert "file1.py" in files
            assert "file2.py" in files
            assert "file3.py" in files

    def test_get_conflicted_files_empty(self, git_ops: GitOperations) -> None:
        """Test getting conflicted files when none exist."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            files = git_ops.get_conflicted_files()

            assert len(files) == 0

    def test_get_conflicted_files_error(self, git_ops: GitOperations) -> None:
        """Test git error returns empty list."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                import subprocess
                raise subprocess.CalledProcessError(
                    1, ["git", "diff"], stderr="error"
                )
            m.setattr("subprocess.run", mock_run)

            files = git_ops.get_conflicted_files()

            assert files == []


# ============================================================================
# GitOperations is_clean_working_dir Tests
# ============================================================================


class TestGitOperationsIsCleanWorkingDir:
    """Tests for GitOperations.is_clean_working_dir method."""

    def test_is_clean_working_dir_true(self, git_ops: GitOperations) -> None:
        """Test clean working directory."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            assert git_ops.is_clean_working_dir() is True

    def test_is_clean_working_dir_false(self, git_ops: GitOperations) -> None:
        """Test dirty working directory."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "M file.py"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            assert git_ops.is_clean_working_dir() is False

    def test_is_clean_working_dir_error(self, git_ops: GitOperations) -> None:
        """Test git error returns False."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                import subprocess
                raise subprocess.CalledProcessError(
                    1, ["git", "status"], stderr="error"
                )
            m.setattr("subprocess.run", mock_run)

            assert git_ops.is_clean_working_dir() is False


# ============================================================================
# GitOperations get_repo_status Tests
# ============================================================================


class TestGitOperationsGetRepoStatus:
    """Tests for GitOperations.get_repo_status method."""

    def test_get_repo_status_clean(self, git_ops: GitOperations) -> None:
        """Test getting status for clean repo."""
        with pytest.MonkeyPatch.context() as m:
            # Mock get_current_branch
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: "main",
            )

            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            status = git_ops.get_repo_status()

            assert status["branch"] == "main"
            assert status["clean"] is True
            assert status["has_conflicts"] is False
            assert status["staged"] == 0
            assert status["unstaged"] == 0
            assert status["untracked"] == 0

    def test_get_repo_status_dirty(self, git_ops: GitOperations) -> None:
        """Test getting status for dirty repo."""
        with pytest.MonkeyPatch.context() as m:
            # Mock get_current_branch
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: "feature/test",
            )

            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                # M file.py (staged), ?? new.py (untracked)
                result.stdout = "M file.py\n?? new.py"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            status = git_ops.get_repo_status()

            assert status["branch"] == "feature/test"
            assert status["clean"] is False
            assert status["staged"] == 1
            assert status["untracked"] == 1

    def test_get_repo_status_staged(self, git_ops: GitOperations) -> None:
        """Test getting status with staged changes."""
        with pytest.MonkeyPatch.context() as m:
            # Mock get_current_branch
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: "main",
            )

            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                # M file.py means staged
                result.stdout = "M file.py"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            status = git_ops.get_repo_status()

            assert status["staged"] == 1


# ============================================================================
# GitOperations rebase_with_conflict_detection Tests
# ============================================================================


class TestGitOperationsRebase:
    """Tests for GitOperations.rebase_with_conflict_detection method."""

    def test_rebase_success(self, git_ops: GitOperations) -> None:
        """Test successful rebase."""
        with pytest.MonkeyPatch.context() as m:
            # Mock clean working directory
            m.setattr(
                GitOperations,
                "is_clean_working_dir",
                lambda self: True,
            )

            # Mock successful rebase
            def mock_run(self, args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "Successfully rebased"
                result.stderr = ""
                return result

            m.setattr(GitOperations, "_run_git", mock_run)

            result = git_ops.rebase_with_conflict_detection("main")

            assert result.success is True
            assert result.has_conflicts is False
            assert result.error is None

    def test_rebase_with_conflicts(self, git_ops: GitOperations) -> None:
        """Test rebase with merge conflicts."""
        with pytest.MonkeyPatch.context() as m:
            # Mock clean working directory
            m.setattr(
                GitOperations,
                "is_clean_working_dir",
                lambda self: True,
            )

            # Mock rebase that stops with conflicts
            def mock_run(self, args, **kwargs):
                result = MagicMock()
                result.returncode = 1
                result.stdout = ""
                result.stderr = "Merge conflict"
                return result

            m.setattr(GitOperations, "_run_git", mock_run)

            # Mock conflict detection
            m.setattr(
                GitOperations,
                "has_merge_conflicts",
                lambda self: True,
            )

            # Mock conflicted files
            m.setattr(
                GitOperations,
                "get_conflicted_files",
                lambda self: ["file1.py", "file2.py"],
            )

            result = git_ops.rebase_with_conflict_detection("main")

            assert result.success is False
            assert result.has_conflicts is True
            assert len(result.conflicted_files) == 2
            assert "merge conflicts" in result.error.lower()

    def test_rebase_dirty_working_dir(self, git_ops: GitOperations) -> None:
        """Test rebase fails with dirty working directory."""
        with pytest.MonkeyPatch.context() as m:
            # Mock dirty working directory
            m.setattr(
                GitOperations,
                "is_clean_working_dir",
                lambda self: False,
            )

            result = git_ops.rebase_with_conflict_detection("main")

            assert result.success is False
            assert "not clean" in result.error.lower()

    def test_rebase_with_onto(self, git_ops: GitOperations) -> None:
        """Test rebase with custom onto parameter."""
        with pytest.MonkeyPatch.context() as m:
            # Mock clean working directory
            m.setattr(
                GitOperations,
                "is_clean_working_dir",
                lambda self: True,
            )

            # Track what branch was used
            used_target = []

            def mock_run(self, args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "Success"
                result.stderr = ""
                if "rebase" in args:
                    used_target.append(args[1])
                return result

            m.setattr(GitOperations, "_run_git", mock_run)

            git_ops.rebase_with_conflict_detection(
                "main",
                onto="origin/main",
            )

            assert used_target[0] == "origin/main"


# ============================================================================
# GitOperations __repr__ Tests
# ============================================================================


class TestGitOperationsRepr:
    """Tests for GitOperations.__repr__ method."""

    def test_repr_with_branch(self, git_ops: GitOperations) -> None:
        """Test repr with current branch."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: "main",
            )

            repr_str = repr(git_ops)

            assert "GitOperations" in repr_str
            assert "main" in repr_str

    def test_repr_without_branch(self, git_ops: GitOperations) -> None:
        """Test repr when branch cannot be determined."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                GitOperations,
                "get_current_branch",
                lambda self: (_ for _ in ()).throw(
                    GitError("No branch")
                ),
            )

            repr_str = repr(git_ops)

            assert "GitOperations" in repr_str
            assert "repo_path" in repr_str


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestFactoryFunction:
    """Tests for create_git_operations factory function."""

    def test_create_git_operations(self, mock_repo_path: Path) -> None:
        """Test factory function creates GitOperations."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "exists", lambda self: True)
            git = create_git_operations(mock_repo_path)

            assert isinstance(git, GitOperations)
            assert git.repo_path == mock_repo_path

    def test_create_git_operations_default(self) -> None:
        """Test factory function with default path."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "exists", lambda self: True)
            m.setattr(Path, "cwd", lambda: Path("/test"))

            git = create_git_operations()

            assert isinstance(git, GitOperations)
