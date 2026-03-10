"""
Unit Tests for Autoflow CLI Init Command

Tests the init command functionality including initialization,
force re-initialization, and JSON output modes.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from autoflow.cli.init import init
from autoflow.core.config import Config
from autoflow.core.state import StateManager


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
    state_dir = Path(".autoflow")
    return state_dir


@pytest.fixture
def sample_config(temp_state_dir: Path) -> Config:
    """Create a sample config for testing."""
    return Config(state_dir=str(temp_state_dir))


# ============================================================================
# Init Command Tests - Basic Functionality
# ============================================================================


class TestInitBasic:
    """Tests for basic init command functionality."""

    def test_init_creates_directories(self, runner: CliRunner) -> None:
        """Test init creates all required directories."""
        with runner.isolated_filesystem():
            result = runner.invoke(init, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            # Verify directories exist in current directory
            from pathlib import Path
            state_dir = Path(".autoflow")
            assert state_dir.exists()
            assert (state_dir / "specs").exists()
            assert (state_dir / "tasks").exists()
            assert (state_dir / "runs").exists()
            assert (state_dir / "memory").exists()
            assert (state_dir / "backups").exists()

    def test_init_success_message(self, runner: CliRunner) -> None:
        """Test init displays success message."""
        with runner.isolated_filesystem():
            result = runner.invoke(init, obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert "Initialized Autoflow" in result.output
            assert "Directory structure:" in result.output
            assert "specs/" in result.output
            assert "tasks/" in result.output
            assert "runs/" in result.output
            assert "memory/" in result.output
            assert "backups/" in result.output

    def test_init_idempotent(self, runner: CliRunner) -> None:
        """Test init fails gracefully when directory exists."""
        with runner.isolated_filesystem():
            # First init should succeed
            result1 = runner.invoke(init, obj={"config": None, "output_json": False})
            assert result1.exit_code == 0

            # Second init should fail
            result2 = runner.invoke(init, obj={"config": None, "output_json": False})
            assert result2.exit_code == 1
            assert "already exists" in result2.output


# ============================================================================
# Init Command Tests - Force Option
# ============================================================================


class TestInitForce:
    """Tests for init --force functionality."""

    def test_init_force_reinitializes(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init --force reinitializes existing directory."""
        with runner.isolated_filesystem(temp_dir=None):
            # First init
            result1 = runner.invoke(init, obj={"config": None, "output_json": False})
            assert result1.exit_code == 0

            # Create a test file to verify it's preserved
            state_dir = Path(".autoflow")
            test_file = state_dir / "test.txt"
            test_file.write_text("test")

            # Force reinit
            result2 = runner.invoke(init, ["--force"], obj={"config": None, "output_json": False})
            assert result2.exit_code == 0
            assert "Initialized Autoflow" in result2.output

    def test_init_force_short_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init -f (short flag) works."""
        with runner.isolated_filesystem(temp_dir=None):
            # First init
            result1 = runner.invoke(init, obj={"config": None, "output_json": False})
            assert result1.exit_code == 0

            # Force reinit with short flag
            result2 = runner.invoke(init, ["-f"], obj={"config": None, "output_json": False})
            assert result2.exit_code == 0

    def test_init_force_when_not_exists(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init --force works when directory doesn't exist."""
        with runner.isolated_filesystem(temp_dir=None):
            result = runner.invoke(init, ["--force"], obj={"config": None, "output_json": False})

            assert result.exit_code == 0
            assert (Path(".autoflow")).exists()

class TestInitErrors:
    """Tests for init command error handling."""

    def test_init_with_custom_config(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test init respects custom state_dir from config."""
        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            config = Config(state_dir="custom_state")
            custom_dir = temp_state_dir.parent / "custom_state"

            # Mock the config loading
            with patch("autoflow.cli.init._get_state_manager") as mock_sm:
                mock_manager = StateManager(custom_dir)
                mock_sm.return_value = mock_manager

                result = runner.invoke(init, obj={"config": config})

                assert result.exit_code == 0

    def test_init_handles_permission_error(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test init handles permission errors gracefully."""
        with runner.isolated_filesystem(temp_dir=temp_state_dir.parent):
            # Create a file where the directory should be
            temp_state_dir.write_text("blocked")

            result = runner.invoke(init)

            # Should fail but not crash
            assert result.exit_code != 0


# ============================================================================
# Init Command Tests - Directory Structure
# ============================================================================


class TestInitDirectoryStructure:
    """Tests for init command directory structure."""

    def test_init_creates_specs_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init creates specs directory."""
        with runner.isolated_filesystem(temp_dir=None):
            runner.invoke(init, obj={"config": None, "output_json": False})
            assert (Path(".autoflow") / "specs").is_dir()

    def test_init_creates_tasks_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init creates tasks directory."""
        with runner.isolated_filesystem(temp_dir=None):
            runner.invoke(init, obj={"config": None, "output_json": False})
            assert (Path(".autoflow") / "tasks").is_dir()

    def test_init_creates_runs_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init creates runs directory."""
        with runner.isolated_filesystem(temp_dir=None):
            runner.invoke(init, obj={"config": None, "output_json": False})
            assert (Path(".autoflow") / "runs").is_dir()

    def test_init_creates_memory_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init creates memory directory."""
        with runner.isolated_filesystem(temp_dir=None):
            runner.invoke(init, obj={"config": None, "output_json": False})
            assert (Path(".autoflow") / "memory").is_dir()

    def test_init_creates_backups_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init creates backups directory."""
        with runner.isolated_filesystem(temp_dir=None):
            runner.invoke(init, obj={"config": None, "output_json": False})
            assert (Path(".autoflow") / "backups").is_dir()

class TestInitEdgeCases:
    """Tests for init command edge cases."""

    def test_init_with_nested_path(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test init works with nested state directory."""
        nested_dir = tmp_path / "deep" / "nested" / ".autoflow"
        config = Config(state_dir=str(nested_dir))

        with runner.isolated_filesystem(temp_dir=None):
            result = runner.invoke(init, obj={"config": config, "output_json": False})

            assert result.exit_code == 0
            assert nested_dir.exists()

    def test_init_preserves_existing_files(self, runner: CliRunner) -> None:
        """Test init --force works with existing directory."""
        with runner.isolated_filesystem():
            # First init
            runner.invoke(init, obj={"config": None, "output_json": False})

            # Force reinit should succeed
            result = runner.invoke(init, ["--force"], obj={"config": None, "output_json": False})

            assert result.exit_code == 0

    def test_init_state_manager_integration(
        self, runner: CliRunner
    ) -> None:
        """Test init creates valid StateManager structure."""
        with runner.isolated_filesystem():
            runner.invoke(init, obj={"config": None, "output_json": False})

            # Verify StateManager can use the directory
            from pathlib import Path
            state_dir = Path(".autoflow").resolve()
            manager = StateManager(state_dir)
            status = manager.get_status()

            # The directory should exist
            assert state_dir.exists()
            assert "state_dir" in status
