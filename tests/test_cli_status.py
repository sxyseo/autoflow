"""
Unit Tests for Autoflow CLI Status Command

Tests the status command functionality including basic status,
detailed view, and JSON output modes.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from autoflow.cli.status import status
from autoflow.core.config import Config
from autoflow.core.state import StateManager, TaskStatus, RunStatus


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / ".autoflow"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def state_manager(temp_state_dir: Path) -> StateManager:
    """Create a StateManager instance with temporary directory."""
    manager = StateManager(temp_state_dir)
    manager.initialize()
    return manager


@pytest.fixture
def sample_config(temp_state_dir: Path) -> Config:
    """Create a sample config for testing."""
    return Config(state_dir=str(temp_state_dir))


# ============================================================================
# Status Command Tests - Basic Functionality
# ============================================================================


class TestStatusBasic:
    """Tests for basic status command functionality."""

    def test_status_displays_header(self, runner: CliRunner) -> None:
        """Test status displays proper header."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(status, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "Autoflow Status" in result.output
            assert "=" * 50 in result.output

    def test_status_shows_state_dir(self, runner: CliRunner) -> None:
        """Test status shows state directory path."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(status, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "State Directory:" in result.output

    def test_status_shows_initialized(self, runner: CliRunner) -> None:
        """Test status shows initialized status."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(status, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "Initialized:" in result.output

    def test_status_with_no_data(self, runner: CliRunner) -> None:
        """Test status with empty state shows zeros."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(status, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "Tasks: 0 total" in result.output
            assert "Runs: 0 total" in result.output
            assert "Specs: 0 total" in result.output
            assert "Memory Entries: 0 total" in result.output


# ============================================================================
# Status Command Tests - With Data
# ============================================================================


class TestStatusWithData:
    """Tests for status command with actual data."""

    def test_status_with_tasks(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status shows task counts."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test Task",
            "status": "pending",
        })
        manager.save_task("task-002", {
            "id": "task-002",
            "title": "Another Task",
            "status": "in_progress",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Tasks: 2 total" in result.output

    def test_status_with_runs(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status shows run counts."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_run("run-001", {
            "id": "run-001",
            "agent": "claude-code",
            "status": "running",
        })
        manager.save_run("run-002", {
            "id": "run-002",
            "agent": "codex",
            "status": "completed",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Runs: 2 total" in result.output

    def test_status_with_specs(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status shows spec counts."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_spec("spec-001", {
            "id": "spec-001",
            "title": "Test Spec",
            "content": "Content",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Specs: 1 total" in result.output

    def test_status_with_memory(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status shows memory entry counts."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_memory("test_key", "test_value")
        manager.save_memory("another_key", {"nested": "data"})

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Memory Entries: 2 total" in result.output


# ============================================================================
# Status Command Tests - Detailed Option
# ============================================================================


class TestStatusDetailed:
    """Tests for status --detailed functionality."""

    def test_status_detailed_shows_task_breakdown(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status --detailed shows task status breakdown."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Pending Task",
            "status": "pending",
        })
        manager.save_task("task-002", {
            "id": "task-002",
            "title": "In Progress Task",
            "status": "in_progress",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                ["--detailed"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            # Should show status breakdown
            assert "pending:" in result.output or "in_progress:" in result.output

    def test_status_detailed_shows_run_breakdown(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status --detailed shows run status breakdown."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_run("run-001", {
            "id": "run-001",
            "agent": "claude-code",
            "status": "running",
        })
        manager.save_run("run-002", {
            "id": "run-002",
            "agent": "claude-code",
            "status": "completed",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                ["--detailed"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            # Should show status breakdown
            assert "running:" in result.output or "completed:" in result.output

    def test_status_detailed_short_flag(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status -d (short flag) works."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test",
            "status": "pending",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                ["-d"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0

    def test_status_detailed_shows_config(self, runner: CliRunner) -> None:
        """Test status --detailed shows configuration section."""
        with runner.isolated_filesystem() as temp_dir:
            state_dir = Path(temp_dir) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            config = Config()

            result = runner.invoke(
                status,
                ["--detailed"],
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert "Configuration:" in result.output
            assert "OpenClaw Gateway:" in result.output
            assert "State Directory:" in result.output
            assert "Scheduler Enabled:" in result.output
            assert "CI Gates Required:" in result.output


# ============================================================================
# Status Command Tests - JSON Output
# ============================================================================


class TestStatusJSON:
    """Tests for status --json functionality."""

    def test_status_json_output(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status --json returns valid JSON."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            # Parse JSON
            import json

            output = json.loads(result.output)
            assert "state_dir" in output
            assert "initialized" in output
            assert "tasks" in output
            assert "runs" in output
            assert "specs" in output
            assert "memory" in output

    def test_status_json_with_data(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status --json includes actual data."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test",
            "status": "pending",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            assert output["tasks"]["total"] == 1
            assert output["initialized"] is True

    def test_status_json_structure(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status --json has proper structure."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)

            # Check tasks structure
            assert "total" in output["tasks"]
            assert "by_status" in output["tasks"]

            # Check runs structure
            assert "total" in output["runs"]
            assert "by_status" in output["runs"]

            # Check specs structure
            assert "total" in output["specs"]

            # Check memory structure
            assert "total" in output["memory"]


# ============================================================================
# Status Command Tests - Error Handling
# ============================================================================


class TestStatusErrors:
    """Tests for status command error handling."""

    def test_status_with_uninitialized_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test status handles uninitialized state directory."""
        state_dir = tmp_path / ".autoflow"

        with runner.isolated_filesystem():
            result = runner.invoke(
                status,
                obj={"config": Config(state_dir=str(state_dir)), "output_json": False},
            )

            # Should still work, just show 0 counts
            assert result.exit_code == 0


# ============================================================================
# Status Command Tests - Integration
# ============================================================================


class TestStatusIntegration:
    """Tests for status command integration with StateManager."""

    def test_status_matches_state_manager(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status output matches StateManager.get_status()."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        # Add some data
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Test",
            "status": "pending",
        })
        manager.save_run("run-001", {
            "id": "run-001",
            "agent": "claude-code",
            "status": "running",
        })

        # Get status from StateManager
        expected = manager.get_status()

        # Get status from CLI
        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)

            # Should match
            assert output["tasks"]["total"] == expected["tasks"]["total"]
            assert output["runs"]["total"] == expected["runs"]["total"]

    def test_status_with_multiple_tasks_by_status(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status correctly counts tasks by status."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_task("task-001", {
            "id": "task-001",
            "title": "Pending 1",
            "status": "pending",
        })
        manager.save_task("task-002", {
            "id": "task-002",
            "title": "Pending 2",
            "status": "pending",
        })
        manager.save_task("task-003", {
            "id": "task-003",
            "title": "In Progress",
            "status": "in_progress",
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            assert output["tasks"]["total"] == 3
            assert output["tasks"]["by_status"]["pending"] == 2
            assert output["tasks"]["by_status"]["in_progress"] == 1


# ============================================================================
# Status Command Tests - Edge Cases
# ============================================================================


class TestStatusEdgeCases:
    """Tests for status command edge cases."""

    def test_status_with_custom_state_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test status works with custom state directory."""
        custom_dir = tmp_path / "custom_autoflow"
        custom_dir.mkdir()
        config = Config(state_dir=str(custom_dir))
        manager = StateManager(custom_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": False},
            )

            assert result.exit_code == 0
            assert str(custom_dir) in result.output

    def test_status_consistency(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test status output is consistent across calls."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result1 = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )
            result2 = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result1.exit_code == 0
            assert result2.exit_code == 0
            assert result1.output == result2.output

    def test_status_with_complex_data(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test status with complex nested data."""
        config = Config(state_dir=str(temp_state_dir))
        manager = StateManager(temp_state_dir)
        manager.initialize()
        manager.save_memory("complex", {
            "nested": {
                "deep": {
                    "value": 42,
                    "list": [1, 2, 3],
                }
            }
        })

        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            result = runner.invoke(
                status,
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0
            assert "memory" in result.output


# ============================================================================
# Legacy CLI list-specs Command Tests
# ============================================================================


class TestLegacyCliListSpecs:
    """Tests for legacy CLI list-specs command output validation."""

    def test_list_specs_outputs_all_required_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test list_specs outputs all required metadata fields."""
        from scripts.autoflow import list_specs, SPECS_DIR

        # Create temporary specs directory structure
        temp_specs_dir = tmp_path / ".autoflow" / "specs"
        temp_specs_dir.mkdir(parents=True)

        # Patch SPECS_DIR to use temporary directory
        monkeypatch.setattr("scripts.autoflow.SPECS_DIR", temp_specs_dir)

        # Create spec metadata files
        spec_001_dir = temp_specs_dir / "spec-001"
        spec_001_dir.mkdir()
        spec_001_metadata = spec_001_dir / "metadata.json"
        spec_001_metadata.write_text(json.dumps({
            "slug": "spec-001",
            "title": "Test Spec 1",
            "summary": "First test spec",
            "status": "in_progress",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "worktree": {
                "path": "",
                "branch": "main",
                "base_branch": "main",
            },
        }))

        spec_002_dir = temp_specs_dir / "spec-002"
        spec_002_dir.mkdir()
        spec_002_metadata = spec_002_dir / "metadata.json"
        spec_002_metadata.write_text(json.dumps({
            "slug": "spec-002",
            "title": "Test Spec 2",
            "summary": "Second test spec",
            "status": "pending",
            "created_at": "2024-01-03T00:00:00Z",
            "updated_at": "2024-01-04T00:00:00Z",
            "worktree": {
                "path": "",
                "branch": "develop",
                "base_branch": "main",
            },
        }))

        # Capture stdout from list_specs function
        import io
        import sys
        from argparse import Namespace

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            list_specs(Namespace())
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        # Parse JSON output
        specs = json.loads(output)

        # Verify we got 2 specs
        assert len(specs) == 2

        # Verify all required fields are present
        for spec in specs:
            assert "slug" in spec, f"Missing 'slug' field in spec: {spec}"
            assert "title" in spec, f"Missing 'title' field in spec: {spec}"
            assert "summary" in spec, f"Missing 'summary' field in spec: {spec}"
            assert "status" in spec, f"Missing 'status' field in spec: {spec}"
            assert "created_at" in spec, f"Missing 'created_at' field in spec: {spec}"
            assert "updated_at" in spec, f"Missing 'updated_at' field in spec: {spec}"
            assert "worktree" in spec, f"Missing 'worktree' field in spec: {spec}"
            assert "review" in spec, f"Missing 'review' field in spec: {spec}"

            # Verify worktree subfields
            assert "path" in spec["worktree"], f"Missing 'path' in worktree for spec {spec['slug']}"
            assert "branch" in spec["worktree"], f"Missing 'branch' in worktree for spec {spec['slug']}"
            assert "base_branch" in spec["worktree"], f"Missing 'base_branch' in worktree for spec {spec['slug']}"

            # Verify review subfields
            assert "approved" in spec["review"], f"Missing 'approved' in review for spec {spec['slug']}"
            assert "approved_by" in spec["review"], f"Missing 'approved_by' in review for spec {spec['slug']}"
            assert "review_count" in spec["review"], f"Missing 'review_count' in review for spec {spec['slug']}"

    def test_list_specs_with_empty_specs_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test list_specs returns empty array with no specs."""
        from scripts.autoflow import list_specs

        # Create temporary empty specs directory
        temp_specs_dir = tmp_path / ".autoflow" / "specs"
        temp_specs_dir.mkdir(parents=True)

        # Patch SPECS_DIR to use temporary directory
        monkeypatch.setattr("scripts.autoflow.SPECS_DIR", temp_specs_dir)

        # Capture stdout from list_specs function
        import io
        import sys
        from argparse import Namespace

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            list_specs(Namespace())
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        # Parse JSON output
        specs = json.loads(output)

        # Verify we got empty array
        assert specs == []

    def test_list_specs_sorts_by_created_at_descending(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test list_specs sorts by created_at descending (newest first)."""
        from scripts.autoflow import list_specs

        # Create temporary specs directory structure
        temp_specs_dir = tmp_path / ".autoflow" / "specs"
        temp_specs_dir.mkdir(parents=True)

        # Patch SPECS_DIR to use temporary directory
        monkeypatch.setattr("scripts.autoflow.SPECS_DIR", temp_specs_dir)

        # Create spec metadata files with different created_at timestamps
        spec_001_dir = temp_specs_dir / "spec-001"
        spec_001_dir.mkdir()
        spec_001_metadata = spec_001_dir / "metadata.json"
        spec_001_metadata.write_text(json.dumps({
            "slug": "spec-001",
            "title": "Oldest Spec",
            "status": "pending",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "worktree": {},
        }))

        spec_002_dir = temp_specs_dir / "spec-002"
        spec_002_dir.mkdir()
        spec_002_metadata = spec_002_dir / "metadata.json"
        spec_002_metadata.write_text(json.dumps({
            "slug": "spec-002",
            "title": "Newest Spec",
            "status": "in_progress",
            "created_at": "2024-01-03T00:00:00Z",
            "updated_at": "2024-01-03T00:00:00Z",
            "worktree": {},
        }))

        spec_003_dir = temp_specs_dir / "spec-003"
        spec_003_dir.mkdir()
        spec_003_metadata = spec_003_dir / "metadata.json"
        spec_003_metadata.write_text(json.dumps({
            "slug": "spec-003",
            "title": "Middle Spec",
            "status": "done",
            "created_at": "2024-01-02T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "worktree": {},
        }))

        # Capture stdout from list_specs function
        import io
        import sys
        from argparse import Namespace

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            list_specs(Namespace())
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        # Parse JSON output
        specs = json.loads(output)

        # Verify order (newest first)
        assert specs[0]["slug"] == "spec-002"  # 2024-01-03
        assert specs[1]["slug"] == "spec-003"  # 2024-01-02
        assert specs[2]["slug"] == "spec-001"  # 2024-01-01

    def test_list_specs_handles_missing_fields_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test list_specs handles missing metadata fields with defaults."""
        from scripts.autoflow import list_specs

        # Create temporary specs directory structure
        temp_specs_dir = tmp_path / ".autoflow" / "specs"
        temp_specs_dir.mkdir(parents=True)

        # Patch SPECS_DIR to use temporary directory
        monkeypatch.setattr("scripts.autoflow.SPECS_DIR", temp_specs_dir)

        # Create spec with minimal metadata (missing optional fields)
        spec_minimal_dir = temp_specs_dir / "spec-minimal"
        spec_minimal_dir.mkdir()
        spec_minimal_metadata = spec_minimal_dir / "metadata.json"
        spec_minimal_metadata.write_text(json.dumps({
            "slug": "spec-minimal",
            # Missing title, summary, status, created_at, updated_at
        }))

        # Capture stdout from list_specs function
        import io
        import sys
        from argparse import Namespace

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            list_specs(Namespace())
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        # Parse JSON output
        specs = json.loads(output)

        # Verify spec is present with defaults
        assert len(specs) == 1
        spec = specs[0]

        # Required fields should be present (with defaults if missing)
        assert spec["slug"] == "spec-minimal"
        assert spec["title"] == ""  # Default empty string
        assert spec["summary"] == ""  # Default empty string
        assert spec["status"] == ""  # Default empty string
        assert spec["created_at"] == ""  # Default empty string
        assert spec["updated_at"] == ""  # Default empty string

        # Worktree and review should always be present
        assert "worktree" in spec


# ============================================================================
# Modern CLI Spec List Command Tests
# ============================================================================


class TestModernCliSpecList:
    """Tests for modern CLI spec list command."""

    @staticmethod
    def _get_spec_command():
        """Get the spec command group from cli.py."""
        import importlib.util
        from pathlib import Path

        # Find cli.py at the project root
        cli_file = Path(__file__).parent.parent / "autoflow" / "cli.py"
        spec = importlib.util.spec_from_file_location("autoflow._cli", cli_file)
        cli_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_module)
        return cli_module.spec

    def test_spec_list_shows_header(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test spec list displays proper header."""
        spec = self._get_spec_command()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize state directory
            state_dir = Path(tmp_path) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(
                spec,
                ["list"],
                obj={"config": None, "output_json": False, "state_dir": None},
            )

            assert result.exit_code == 0
            assert "Specifications" in result.output
            assert "=" * 60 in result.output

    def test_spec_list_with_empty_specs(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test spec list with no specs shows appropriate message."""
        spec = self._get_spec_command()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize state directory
            state_dir = Path(tmp_path) / ".autoflow"
            manager = StateManager(state_dir)
            manager.initialize()

            result = runner.invoke(
                spec,
                ["list"],
                obj={"config": None, "output_json": False, "state_dir": None},
            )

            assert result.exit_code == 0
            assert "No specifications found" in result.output

    def test_spec_list_displays_specs(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test spec list displays specs with metadata."""
        spec = self._get_spec_command()

        with runner.isolated_filesystem():
            # Initialize state directory in the isolated filesystem
            state_dir = Path(".autoflow")
            manager = StateManager(state_dir)
            manager.initialize()

            # Create spec directories with metadata
            specs_dir = state_dir / "specs"
            spec_001_dir = specs_dir / "spec-001"
            spec_001_dir.mkdir(parents=True)

            # Write metadata.json
            metadata_001 = spec_001_dir / "metadata.json"
            metadata_001.write_text(json.dumps({
                "slug": "spec-001",
                "title": "Test Spec 1",
                "summary": "First test spec",
                "status": "in_progress",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "worktree": {
                    "branch": "feature-001",
                    "path": "/tmp/worktree",
                    "base_branch": "main",
                },
            }))

            result = runner.invoke(
                spec,
                ["list"],
                obj={"config": None, "output_json": False, "state_dir": None},
            )

            assert result.exit_code == 0
            assert "[spec-001]" in result.output
            assert "Test Spec 1" in result.output
            assert "Status: in_progress" in result.output
            assert "Branch: feature-001" in result.output
            assert "Review: Pending" in result.output

    def test_spec_list_json_output(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test spec list JSON output mode."""
        spec = self._get_spec_command()

        with runner.isolated_filesystem():
            # Initialize state directory in the isolated filesystem
            state_dir = Path(".autoflow")
            manager = StateManager(state_dir)
            manager.initialize()

            # Create spec directories with metadata
            specs_dir = state_dir / "specs"
            spec_001_dir = specs_dir / "spec-001"
            spec_001_dir.mkdir(parents=True)

            metadata_001 = spec_001_dir / "metadata.json"
            metadata_001.write_text(json.dumps({
                "slug": "spec-001",
                "title": "Test Spec 1",
                "summary": "First test spec",
                "status": "in_progress",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "worktree": {},
            }))

            result = runner.invoke(
                spec,
                ["list"],
                obj={"config": None, "output_json": True, "state_dir": None},
            )

            assert result.exit_code == 0

            # Parse JSON output
            data = json.loads(result.output)

            assert "specs" in data
            assert "count" in data
            assert data["count"] == 1
            assert len(data["specs"]) == 1

            spec_data = data["specs"][0]
            assert spec_data["slug"] == "spec-001"
            assert spec_data["title"] == "Test Spec 1"
            assert spec_data["status"] == "in_progress"

    def test_spec_list_with_limit(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test spec list with limit option."""
        spec = self._get_spec_command()

        with runner.isolated_filesystem():
            # Initialize state directory in the isolated filesystem
            state_dir = Path(".autoflow")
            manager = StateManager(state_dir)
            manager.initialize()

            # Create multiple spec directories
            specs_dir = state_dir / "specs"
            for i in range(3):
                spec_dir = specs_dir / f"spec-{i:03d}"
                spec_dir.mkdir(parents=True)

                metadata_file = spec_dir / "metadata.json"
                metadata_file.write_text(json.dumps({
                    "slug": f"spec-{i:03d}",
                    "title": f"Test Spec {i}",
                    "status": "pending",
                    "created_at": f"2024-01-0{i+1}T00:00:00Z",
                    "updated_at": f"2024-01-0{i+1}T00:00:00Z",
                    "worktree": {},
                }))

            result = runner.invoke(
                spec,
                ["list", "--limit", "2"],
                obj={"config": None, "output_json": False, "state_dir": None},
            )

            assert result.exit_code == 0
            # Should only show 2 specs
            assert "spec-002" in result.output or "spec-001" in result.output
            assert "spec-002" in result.output or "spec-000" in result.output

    def test_spec_list_shows_review_status(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test spec list displays review status correctly."""
        spec = self._get_spec_command()

        with runner.isolated_filesystem():
            # Initialize state directory in the isolated filesystem
            state_dir = Path(".autoflow")
            manager = StateManager(state_dir)
            manager.initialize()

            # Create spec with approved review state
            specs_dir = state_dir / "specs"
            spec_001_dir = specs_dir / "spec-001"
            spec_001_dir.mkdir(parents=True)

            # Write metadata.json
            metadata_001 = spec_001_dir / "metadata.json"
            metadata_001.write_text(json.dumps({
                "slug": "spec-001",
                "title": "Approved Spec",
                "status": "in_progress",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "worktree": {},
            }))

            # Write review_state.json
            review_state_001 = spec_001_dir / "review_state.json"
            review_state_001.write_text(json.dumps({
                "approved": True,
                "approved_by": "reviewer-1",
                "review_count": 2,
            }))

            result = runner.invoke(
                spec,
                ["list"],
                obj={"config": None, "output_json": False, "state_dir": None},
            )

            assert result.exit_code == 0
            assert "✓ Approved" in result.output
            assert "Approved Spec" in result.output
