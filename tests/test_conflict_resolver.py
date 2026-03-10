"""
Unit Tests for Conflict Resolver

Tests the ConflictResolver, ConflictResult, and related classes for
automatic merge conflict resolution.

These tests mock subprocess execution and file operations to avoid requiring
actual git repositories or conflict markers in the test environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from autoflow.git.conflict_resolver import (
    ConflictError,
    ConflictMarker,
    ConflictResolutionType,
    ConflictResolver,
    ConflictResult,
    create_conflict_resolver,
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
def conflict_resolver(mock_repo_path: Path) -> ConflictResolver:
    """Create a ConflictResolver instance with mocked git repo check."""
    with pytest.MonkeyPatch.context() as m:
        # Mock .git directory existence
        def mock_exists(self):
            if self.name == ".git":
                return True
            return False

        m.setattr(Path, "exists", mock_exists)

        # Mock git rev-parse to confirm it's a repo
        def mock_run(*args, **kwargs):
            process = MagicMock()
            process.returncode = 0
            process.stdout = "true"
            process.stderr = ""
            return process

        m.setattr("subprocess.run", mock_run)

        resolver = ConflictResolver(repo_path=mock_repo_path)
        return resolver


# ============================================================================
# ConflictError Tests
# ============================================================================


class TestConflictError:
    """Tests for ConflictError exception."""

    def test_conflict_error_init(self) -> None:
        """Test ConflictError initialization."""
        error = ConflictError("Test error")

        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.exit_code is None
        assert error.command is None
        assert error.repo_path is None

    def test_conflict_error_with_exit_code(self) -> None:
        """Test ConflictError with exit code."""
        error = ConflictError("Failed", exit_code=1)

        assert error.exit_code == 1

    def test_conflict_error_with_command(self) -> None:
        """Test ConflictError with command."""
        error = ConflictError("Git failed", command=["git", "status"])

        assert error.command == ["git", "status"]

    def test_conflict_error_with_repo_path(self) -> None:
        """Test ConflictError with repo path."""
        path = Path("/test/repo")
        error = ConflictError("Not a repo", repo_path=path)

        assert error.repo_path == path

    def test_conflict_error_all_fields(self) -> None:
        """Test ConflictError with all fields."""
        error = ConflictError(
            message="Comprehensive error",
            exit_code=128,
            command=["git", "checkout"],
            repo_path=Path("/repo"),
        )

        assert error.message == "Comprehensive error"
        assert error.exit_code == 128
        assert error.command == ["git", "checkout"]
        assert error.repo_path == Path("/repo")


# ============================================================================
# ConflictResolutionType Tests
# ============================================================================


class TestConflictResolutionType:
    """Tests for ConflictResolutionType enum."""

    def test_resolution_types(self) -> None:
        """Test all resolution type values."""
        assert ConflictResolutionType.THEIRS_FULL.value == "theirs_full"
        assert ConflictResolutionType.OURS_FULL.value == "ours_full"
        assert ConflictResolutionType.MARKER_RESOLUTION.value == "marker_resolution"
        assert ConflictResolutionType.MANUAL.value == "manual"


# ============================================================================
# ConflictMarker Tests
# ============================================================================


class TestConflictMarker:
    """Tests for ConflictMarker dataclass."""

    def test_conflict_marker_init(self) -> None:
        """Test ConflictMarker initialization."""
        marker = ConflictMarker(
            file_path="test.py",
            start_line=10,
            end_line=20,
        )

        assert marker.file_path == "test.py"
        assert marker.start_line == 10
        assert marker.end_line == 20
        assert marker.ours_content == []
        assert marker.theirs_content == []
        assert marker.base_content is None

    def test_conflict_marker_with_content(self) -> None:
        """Test ConflictMarker with content."""
        marker = ConflictMarker(
            file_path="test.py",
            start_line=10,
            end_line=20,
            ours_content=["line1\n", "line2\n"],
            theirs_content=["line3\n", "line4\n"],
        )

        assert len(marker.ours_content) == 2
        assert len(marker.theirs_content) == 2
        assert marker.ours_content[0] == "line1\n"

    def test_conflict_marker_repr(self) -> None:
        """Test ConflictMarker repr."""
        marker = ConflictMarker(
            file_path="test.py",
            start_line=10,
            end_line=20,
        )

        repr_str = repr(marker)
        assert "test.py" in repr_str
        assert "10-20" in repr_str


# ============================================================================
# ConflictResult Tests
# ============================================================================


class TestConflictResult:
    """Tests for ConflictResult dataclass."""

    def test_conflict_result_init_default(self) -> None:
        """Test ConflictResult initialization with defaults."""
        result = ConflictResult()

        assert result.success is False
        assert result.strategy_used == ConflictResolutionType.MANUAL
        assert result.resolved_files == []
        assert result.conflicted_files == []
        assert result.markers == []
        assert result.error is None
        assert result.resolution_summary is None

    def test_conflict_result_success(self) -> None:
        """Test ConflictResult for successful resolution."""
        result = ConflictResult(
            success=True,
            strategy_used=ConflictResolutionType.THEIRS_FULL,
            resolved_files=["file1.py", "file2.py"],
        )

        assert result.success is True
        assert result.strategy_used == ConflictResolutionType.THEIRS_FULL
        assert len(result.resolved_files) == 2
        assert "file1.py" in result.resolved_files

    def test_conflict_result_with_conflicts(self) -> None:
        """Test ConflictResult with remaining conflicts."""
        result = ConflictResult(
            success=False,
            strategy_used=ConflictResolutionType.MARKER_RESOLUTION,
            resolved_files=["file1.py"],
            conflicted_files=["file2.py", "file3.py"],
            error="Could not resolve all conflicts",
        )

        assert result.success is False
        assert len(result.resolved_files) == 1
        assert len(result.conflicted_files) == 2
        assert result.error == "Could not resolve all conflicts"

    def test_conflict_result_repr_success(self) -> None:
        """Test ConflictResult repr for success."""
        result = ConflictResult(
            success=True,
            strategy_used=ConflictResolutionType.THEIRS_FULL,
            resolved_files=["file1.py"],
        )

        repr_str = repr(result)
        assert "✓" in repr_str
        assert "theirs_full" in repr_str
        assert "resolved=1" in repr_str

    def test_conflict_result_repr_failure(self) -> None:
        """Test ConflictResult repr for failure."""
        result = ConflictResult(
            success=False,
            conflicted_files=["file1.py"],
        )

        repr_str = repr(result)
        assert "✗" in repr_str


# ============================================================================
# ConflictResolver Init Tests
# ============================================================================


class TestConflictResolverInit:
    """Tests for ConflictResolver initialization."""

    def test_init_with_path(self, mock_repo_path: Path) -> None:
        """Test initialization with repo path."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "exists", lambda self: True)

            def mock_run(*args, **kwargs):
                process = MagicMock()
                process.returncode = 0
                process.stdout = "true"
                process.stderr = ""
                return process

            m.setattr("subprocess.run", mock_run)

            resolver = ConflictResolver(repo_path=mock_repo_path)

            assert resolver.repo_path == mock_repo_path
            assert resolver.verbose is False

    def test_init_with_verbose(self, mock_repo_path: Path) -> None:
        """Test initialization with verbose mode."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "exists", lambda self: True)

            def mock_run(*args, **kwargs):
                process = MagicMock()
                process.returncode = 0
                process.stdout = "true"
                process.stderr = ""
                return process

            m.setattr("subprocess.run", mock_run)

            resolver = ConflictResolver(repo_path=mock_repo_path, verbose=True)

            assert resolver.verbose is True

    def test_init_not_a_git_repo(self, tmp_path: Path) -> None:
        """Test initialization fails when not a git repo."""
        with pytest.MonkeyPatch.context() as m:
            # Mock .git directory not existing
            def mock_exists(self):
                return False

            m.setattr(Path, "exists", mock_exists)

            # Mock git rev-parse failure
            def mock_run(*args, **kwargs):
                process = MagicMock()
                process.returncode = 128
                process.stdout = "false"
                process.stderr = "Not a git repository"
                return process

            m.setattr("subprocess.run", mock_run)

            with pytest.raises(ConflictError) as exc_info:
                ConflictResolver(repo_path=tmp_path)

            assert "Not a git repository" in str(exc_info.value)


# ============================================================================
# ConflictResolver _run_git Tests
# ============================================================================


class TestConflictResolverRunGit:
    """Tests for ConflictResolver._run_git method."""

    def test_run_git_success(
        self,
        conflict_resolver: ConflictResolver,
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
            result = conflict_resolver._run_git(["status"])

            assert result.returncode == 0
            assert result.stdout == "output"

    def test_run_git_failure_raises(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test that git command failure raises ConflictError."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                import subprocess
                raise subprocess.CalledProcessError(
                    1, ["git", "status"], stderr="error"
                )
            m.setattr("subprocess.run", mock_run)

            with pytest.raises(ConflictError) as exc_info:
                conflict_resolver._run_git(["status"], check=True)

            assert "Git command failed" in str(exc_info.value)

    def test_run_git_not_found(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test that missing git raises ConflictError."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                raise FileNotFoundError("git not found")
            m.setattr("subprocess.run", mock_run)

            with pytest.raises(ConflictError) as exc_info:
                conflict_resolver._run_git(["status"])

            assert "Git not found" in str(exc_info.value)


# ============================================================================
# ConflictResolver has_conflicts Tests
# ============================================================================


class TestConflictResolverHasConflicts:
    """Tests for ConflictResolver.has_conflicts method."""

    def test_has_conflicts_true(self, conflict_resolver: ConflictResolver) -> None:
        """Test detecting merge conflicts."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "UU file.py\nAA other.py"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            assert conflict_resolver.has_conflicts() is True

    def test_has_conflicts_false(self, conflict_resolver: ConflictResolver) -> None:
        """Test no merge conflicts."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = "M file.py"
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            assert conflict_resolver.has_conflicts() is False

    def test_has_conflicts_error(self, conflict_resolver: ConflictResolver) -> None:
        """Test git error returns False."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                import subprocess
                raise subprocess.CalledProcessError(
                    1, ["git", "status"], stderr="error"
                )
            m.setattr("subprocess.run", mock_run)

            assert conflict_resolver.has_conflicts() is False


# ============================================================================
# ConflictResolver get_conflicted_files Tests
# ============================================================================


class TestConflictResolverGetConflictedFiles:
    """Tests for ConflictResolver.get_conflicted_files method."""

    def test_get_conflicted_files_multiple(
        self,
        conflict_resolver: ConflictResolver,
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

            files = conflict_resolver.get_conflicted_files()

            assert len(files) == 3
            assert "file1.py" in files
            assert "file2.py" in files
            assert "file3.py" in files

    def test_get_conflicted_files_empty(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test getting conflicted files when none exist."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
                return result

            m.setattr("subprocess.run", mock_run)

            files = conflict_resolver.get_conflicted_files()

            assert len(files) == 0

    def test_get_conflicted_files_error(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test git error returns empty list."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(*args, **kwargs):
                import subprocess
                raise subprocess.CalledProcessError(
                    1, ["git", "diff"], stderr="error"
                )
            m.setattr("subprocess.run", mock_run)

            files = conflict_resolver.get_conflicted_files()

            assert files == []


# ============================================================================
# ConflictResolver get_conflict_markers Tests
# ============================================================================


class TestConflictResolverGetConflictMarkers:
    """Tests for ConflictResolver.get_conflict_markers method."""

    def test_get_conflict_markers_no_file(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test getting markers from non-existent file."""
        markers = conflict_resolver.get_conflict_markers("nonexistent.py")

        assert markers == []

    def test_get_conflict_markers_with_markers(
        self,
        conflict_resolver: ConflictResolver,
        tmp_path: Path,
    ) -> None:
        """Test extracting conflict markers from a file."""
        # Create a test file with conflict markers
        test_file = tmp_path / "test_repo" / "conflicted.py"
        test_file.write_text("""line1
<<<<<<<
ours_content
=======
theirs_content
>>>>>>>
line2
""")

        markers = conflict_resolver.get_conflict_markers("conflicted.py")

        assert len(markers) == 1
        assert markers[0].file_path == "conflicted.py"
        assert markers[0].start_line == 2
        assert markers[0].end_line == 6
        assert len(markers[0].ours_content) == 1
        assert len(markers[0].theirs_content) == 1

    def test_get_conflict_markers_multiple(
        self,
        conflict_resolver: ConflictResolver,
        tmp_path: Path,
    ) -> None:
        """Test extracting multiple conflict markers."""
        test_file = tmp_path / "test_repo" / "conflicted.py"
        test_file.write_text("""line1
<<<<<<<
ours1
=======
theirs1
>>>>>>>
line2
<<<<<<<
ours2
=======
theirs2
>>>>>>>
line3
""")

        markers = conflict_resolver.get_conflict_markers("conflicted.py")

        assert len(markers) == 2
        assert markers[0].start_line == 2
        assert markers[1].start_line == 8


# ============================================================================
# ConflictResolver attempt_resolution Tests
# ============================================================================


class TestConflictResolverAttemptResolution:
    """Tests for ConflictResolver.attempt_resolution method."""

    def test_attempt_resolution_no_conflicts(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test resolution when no conflicts exist."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                conflict_resolver,
                "get_conflicted_files",
                lambda: [],
            )

            result = conflict_resolver.attempt_resolution()

            assert result.success is True
            assert result.resolved_files == []
            assert result.conflicted_files == []
            assert "No conflicts to resolve" in result.resolution_summary

    def test_attempt_resolution_theirs_full(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test resolution with theirs_full strategy."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                conflict_resolver,
                "get_conflicted_files",
                lambda: ["file1.py", "file2.py"],
            )

            m.setattr(
                conflict_resolver,
                "_resolve_theirs_full",
                lambda files: ["file1.py", "file2.py"],
            )

            result = conflict_resolver.attempt_resolution(
                strategy=ConflictResolutionType.THEIRS_FULL
            )

            assert result.success is True
            assert len(result.resolved_files) == 2
            assert result.strategy_used == ConflictResolutionType.THEIRS_FULL

    def test_attempt_resolution_ours_full(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test resolution with ours_full strategy."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                conflict_resolver,
                "get_conflicted_files",
                lambda: ["file1.py"],
            )

            m.setattr(
                conflict_resolver,
                "_resolve_ours_full",
                lambda files: ["file1.py"],
            )

            result = conflict_resolver.attempt_resolution(
                strategy=ConflictResolutionType.OURS_FULL
            )

            assert result.success is True
            assert result.strategy_used == ConflictResolutionType.OURS_FULL

    def test_attempt_resolution_manual(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test manual resolution strategy."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                conflict_resolver,
                "get_conflicted_files",
                lambda: ["file1.py"],
            )

            result = conflict_resolver.attempt_resolution(
                strategy=ConflictResolutionType.MANUAL
            )

            assert result.success is False
            assert result.strategy_used == ConflictResolutionType.MANUAL
            assert len(result.conflicted_files) == 1


# ============================================================================
# ConflictResolver _resolve_theirs_full Tests
# ============================================================================


class TestConflictResolverResolveTheirsFull:
    """Tests for ConflictResolver._resolve_theirs_full method."""

    def test_resolve_theirs_full_success(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test successful theirs_full resolution."""
        with pytest.MonkeyPatch.context() as m:
            call_count = [0]

            def mock_run(self, args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
                call_count[0] += 1
                return result

            m.setattr(ConflictResolver, "_run_git", mock_run)

            resolved = conflict_resolver._resolve_theirs_full(["file1.py", "file2.py"])

            assert len(resolved) == 2
            assert "file1.py" in resolved
            assert "file2.py" in resolved
            # Should call checkout and add for each file
            assert call_count[0] == 4

    def test_resolve_theirs_full_partial_failure(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test theirs_full with some failures."""
        with pytest.MonkeyPatch.context() as m:
            def mock_run(self, args, **kwargs):
                if "file2.py" in args:
                    raise ConflictError("Failed")
                result = MagicMock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
                return result

            m.setattr(ConflictResolver, "_run_git", mock_run)

            resolved = conflict_resolver._resolve_theirs_full(["file1.py", "file2.py"])

            assert len(resolved) == 1
            assert "file1.py" in resolved


# ============================================================================
# ConflictResolver _resolve_ours_full Tests
# ============================================================================


class TestConflictResolverResolveOursFull:
    """Tests for ConflictResolver._resolve_ours_full method."""

    def test_resolve_ours_full_success(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test successful ours_full resolution."""
        with pytest.MonkeyPatch.context() as m:
            call_count = [0]

            def mock_run(self, args, **kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
                call_count[0] += 1
                return result

            m.setattr(ConflictResolver, "_run_git", mock_run)

            resolved = conflict_resolver._resolve_ours_full(["file1.py"])

            assert len(resolved) == 1
            assert "file1.py" in resolved
            assert call_count[0] == 2


# ============================================================================
# ConflictResolver _try_resolve_marker Tests
# ============================================================================


class TestConflictResolverTryResolveMarker:
    """Tests for ConflictResolver._try_resolve_marker method."""

    def test_try_resolve_marker_identical(self) -> None:
        """Test resolving marker with identical content."""
        marker = ConflictMarker(
            file_path="test.py",
            start_line=1,
            end_line=5,
            ours_content=["line1\n", "line2\n"],
            theirs_content=["line1\n", "line2\n"],
        )

        resolver = ConflictResolver.__new__(ConflictResolver)
        result = resolver._try_resolve_marker(Path("test.py"), marker)

        assert result is True

    def test_try_resolve_marker_ours_empty(self) -> None:
        """Test resolving marker when ours is only whitespace."""
        marker = ConflictMarker(
            file_path="test.py",
            start_line=1,
            end_line=5,
            ours_content=["\n", "  \n"],
            theirs_content=["content\n"],
        )

        resolver = ConflictResolver.__new__(ConflictResolver)
        result = resolver._try_resolve_marker(Path("test.py"), marker)

        assert result is True

    def test_try_resolve_marker_theirs_empty(self) -> None:
        """Test resolving marker when theirs is only whitespace."""
        marker = ConflictMarker(
            file_path="test.py",
            start_line=1,
            end_line=5,
            ours_content=["content\n"],
            theirs_content=["\n", "  \n"],
        )

        resolver = ConflictResolver.__new__(ConflictResolver)
        result = resolver._try_resolve_marker(Path("test.py"), marker)

        assert result is True

    def test_try_resolve_marker_cannot_resolve(self) -> None:
        """Test marker that cannot be auto-resolved."""
        marker = ConflictMarker(
            file_path="test.py",
            start_line=1,
            end_line=5,
            ours_content=["ours\n"],
            theirs_content=["theirs\n"],
        )

        resolver = ConflictResolver.__new__(ConflictResolver)
        result = resolver._try_resolve_marker(Path("test.py"), marker)

        assert result is False


# ============================================================================
# ConflictResolver extract_conflict_context Tests
# ============================================================================


class TestConflictResolverExtractConflictContext:
    """Tests for ConflictResolver.extract_conflict_context method."""

    def test_extract_conflict_context_no_conflicts(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test extracting context when no conflicts."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                conflict_resolver,
                "get_conflicted_files",
                lambda: [],
            )

            context = conflict_resolver.extract_conflict_context()

            assert context["total_conflicts"] == 0
            assert context["suggested_approach"] == "no_conflicts"
            assert len(context["conflicted_files"]) == 0

    def test_extract_conflict_context_single_file(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test extracting context for single file conflict."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                conflict_resolver,
                "get_conflicted_files",
                lambda: ["file1.py"],
            )

            marker = ConflictMarker(
                file_path="file1.py",
                start_line=10,
                end_line=20,
                ours_content=["ours\n"],
                theirs_content=["theirs\n"],
            )

            m.setattr(
                conflict_resolver,
                "get_conflict_markers",
                lambda f: [marker],
            )

            context = conflict_resolver.extract_conflict_context()

            assert context["total_conflicts"] == 1
            assert context["suggested_approach"] == "single_file"
            assert "file1.py" in context["file_details"]

    def test_extract_conflict_context_complex(
        self,
        conflict_resolver: ConflictResolver,
    ) -> None:
        """Test extracting context for complex conflicts."""
        with pytest.MonkeyPatch.context() as m:
            # Create 12 conflicts across multiple files
            m.setattr(
                conflict_resolver,
                "get_conflicted_files",
                lambda: [f"file{i}.py" for i in range(3)],
            )

            def mock_markers(f):
                # Return 4 markers per file = 12 total
                return [
                    ConflictMarker(
                        file_path=f,
                        start_line=i * 10,
                        end_line=i * 10 + 5,
                        ours_content=["ours\n"],
                        theirs_content=["theirs\n"],
                    )
                    for i in range(4)
                ]

            m.setattr(conflict_resolver, "get_conflict_markers", mock_markers)

            context = conflict_resolver.extract_conflict_context()

            assert context["total_conflicts"] == 12
            assert context["suggested_approach"] == "complex_manual"


# ============================================================================
# ConflictResolver __repr__ Tests
# ============================================================================


class TestConflictResolverRepr:
    """Tests for ConflictResolver.__repr__ method."""

    def test_repr_with_conflicts(self, conflict_resolver: ConflictResolver) -> None:
        """Test repr when conflicts exist."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                conflict_resolver,
                "has_conflicts",
                lambda: True,
            )

            repr_str = repr(conflict_resolver)

            assert "ConflictResolver" in repr_str
            assert "has_conflicts=True" in repr_str

    def test_repr_no_conflicts(self, conflict_resolver: ConflictResolver) -> None:
        """Test repr when no conflicts."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                conflict_resolver,
                "has_conflicts",
                lambda: False,
            )

            repr_str = repr(conflict_resolver)

            assert "ConflictResolver" in repr_str
            assert "has_conflicts=False" in repr_str


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestFactoryFunction:
    """Tests for create_conflict_resolver factory function."""

    def test_create_conflict_resolver(self, mock_repo_path: Path) -> None:
        """Test factory function creates ConflictResolver."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "exists", lambda self: True)

            def mock_run(*args, **kwargs):
                process = MagicMock()
                process.returncode = 0
                process.stdout = "true"
                process.stderr = ""
                return process

            m.setattr("subprocess.run", mock_run)

            resolver = create_conflict_resolver(mock_repo_path)

            assert isinstance(resolver, ConflictResolver)
            assert resolver.repo_path == mock_repo_path

    def test_create_conflict_resolver_with_verbose(
        self,
        mock_repo_path: Path,
    ) -> None:
        """Test factory function with verbose mode."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "exists", lambda self: True)

            def mock_run(*args, **kwargs):
                process = MagicMock()
                process.returncode = 0
                process.stdout = "true"
                process.stderr = ""
                return process

            m.setattr("subprocess.run", mock_run)

            resolver = create_conflict_resolver(mock_repo_path, verbose=True)

            assert isinstance(resolver, ConflictResolver)
            assert resolver.verbose is True
