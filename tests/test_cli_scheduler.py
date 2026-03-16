"""
Unit Tests for Autoflow CLI Scheduler Commands

Tests the scheduler start, stop, and status commands.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from autoflow.cli.scheduler import scheduler, scheduler_start, scheduler_stop, scheduler_status
from autoflow.core.config import Config


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
def sample_config(temp_state_dir: Path) -> Config:
    """Create a sample config for testing."""
    config = Config(state_dir=str(temp_state_dir))
    # Enable scheduler
    config.scheduler = MagicMock()
    config.scheduler.enabled = True
    config.scheduler.check_interval_seconds = 60
    config.scheduler.jobs = [
        MagicMock(id="job-001", cron="0 * * * *", handler="test_handler", enabled=True),
        MagicMock(id="job-002", cron="*/30 * * * *", handler="another_handler", enabled=False),
    ]
    return config


@pytest.fixture
def disabled_config(temp_state_dir: Path) -> Config:
    """Create a config with scheduler disabled for testing."""
    config = Config(state_dir=str(temp_state_dir))
    config.scheduler = MagicMock()
    config.scheduler.enabled = False
    config.scheduler.check_interval_seconds = 60
    config.scheduler.jobs = []
    return config


# ============================================================================
# Scheduler Start Command Tests - Basic Functionality
# ============================================================================


class TestSchedulerStartBasic:
    """Tests for basic scheduler start command functionality."""

    def test_scheduler_start_displays_info(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler start displays startup information."""
        result = runner.invoke(
            scheduler_start,
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Starting scheduler daemon" in result.output
        assert "Port:" in result.output
        assert "8080" in result.output
        assert "Daemon mode: False" in result.output
        assert "Jobs configured: 2" in result.output

    def test_scheduler_start_with_daemon_flag(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler start --daemon sets daemon mode."""
        result = runner.invoke(
            scheduler_start,
            ["--daemon"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Daemon mode: True" in result.output

    def test_scheduler_start_with_custom_port(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler start --port sets custom port."""
        result = runner.invoke(
            scheduler_start,
            ["--port", "9000"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Port: 9000" in result.output

    def test_scheduler_start_short_flags(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler start short flags work."""
        result = runner.invoke(
            scheduler_start,
            ["-d", "-p", "8081"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Daemon mode: True" in result.output
        assert "Port: 8081" in result.output

    def test_scheduler_start_shows_placeholder_note(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler start shows placeholder note."""
        result = runner.invoke(
            scheduler_start,
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "placeholder" in result.output.lower()
        assert "async runtime" in result.output.lower()


# ============================================================================
# Scheduler Start Command Tests - Error Handling
# ============================================================================


class TestSchedulerStartErrors:
    """Tests for scheduler start command error handling."""

    def test_scheduler_start_without_config(self, runner: CliRunner) -> None:
        """Test scheduler start without config returns error."""
        result = runner.invoke(
            scheduler_start,
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Configuration not loaded" in result.output

    def test_scheduler_start_when_disabled(self, runner: CliRunner, disabled_config: Config) -> None:
        """Test scheduler start when scheduler is disabled returns error."""
        result = runner.invoke(
            scheduler_start,
            obj={"config": disabled_config, "output_json": False},
        )

        assert result.exit_code == 1
        assert "disabled in configuration" in result.output.lower()


# ============================================================================
# Scheduler Start Command Tests - JSON Output
# ============================================================================


class TestSchedulerStartJSON:
    """Tests for scheduler start --json functionality."""

    def test_scheduler_start_json_output(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler start returns valid JSON."""
        result = runner.invoke(
            scheduler_start,
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["status"] == "starting"
        assert output["daemon"] is False
        assert output["port"] == 8080
        assert output["jobs_count"] == 2

    def test_scheduler_start_json_with_options(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler start --json includes command options."""
        result = runner.invoke(
            scheduler_start,
            ["--daemon", "--port", "9000"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["daemon"] is True
        assert output["port"] == 9000


# ============================================================================
# Scheduler Stop Command Tests - Basic Functionality
# ============================================================================


class TestSchedulerStopBasic:
    """Tests for basic scheduler stop command functionality."""

    def test_scheduler_stop_displays_message(self, runner: CliRunner) -> None:
        """Test scheduler stop displays stop message."""
        result = runner.invoke(
            scheduler_stop,
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "stopped" in result.output.lower()

    def test_scheduler_stop_without_config(self, runner: CliRunner) -> None:
        """Test scheduler stop works without config (no dependency)."""
        result = runner.invoke(
            scheduler_stop,
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 0
        # Should still work as it's a placeholder


# ============================================================================
# Scheduler Stop Command Tests - JSON Output
# ============================================================================


class TestSchedulerStopJSON:
    """Tests for scheduler stop --json functionality."""

    def test_scheduler_stop_json_output(self, runner: CliRunner) -> None:
        """Test scheduler stop returns valid JSON."""
        result = runner.invoke(
            scheduler_stop,
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["status"] == "stopped"


# ============================================================================
# Scheduler Status Command Tests - Basic Functionality
# ============================================================================


class TestSchedulerStatusBasic:
    """Tests for basic scheduler status command functionality."""

    def test_scheduler_status_displays_header(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler status displays proper header."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Scheduler Status" in result.output
        assert "=" * 60 in result.output

    def test_scheduler_status_shows_enabled(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler status shows enabled status."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Enabled: True" in result.output

    def test_scheduler_status_shows_job_count(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler status shows job count."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Jobs configured: 2" in result.output

    def test_scheduler_status_lists_jobs(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler status lists configured jobs."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Jobs:" in result.output
        assert "[job-001]" in result.output
        assert "[job-002]" in result.output

    def test_scheduler_status_shows_job_details(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler status shows job cron and handler."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "0 * * * *" in result.output
        assert "test_handler" in result.output
        assert "*/30 * * * *" in result.output
        assert "another_handler" in result.output

    def test_scheduler_status_shows_job_enabled_status(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler status shows job enabled status."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "(enabled)" in result.output
        assert "(disabled)" in result.output

    def test_scheduler_status_when_disabled(self, runner: CliRunner, disabled_config: Config) -> None:
        """Test scheduler status shows disabled status."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": disabled_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Enabled: False" in result.output

    def test_scheduler_status_with_no_jobs(self, runner: CliRunner, disabled_config: Config) -> None:
        """Test scheduler status with no configured jobs."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": disabled_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Jobs configured: 0" in result.output


# ============================================================================
# Scheduler Status Command Tests - Error Handling
# ============================================================================


class TestSchedulerStatusErrors:
    """Tests for scheduler status command error handling."""

    def test_scheduler_status_without_config(self, runner: CliRunner) -> None:
        """Test scheduler status without config returns error."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Configuration not loaded" in result.output


# ============================================================================
# Scheduler Status Command Tests - JSON Output
# ============================================================================


class TestSchedulerStatusJSON:
    """Tests for scheduler status --json functionality."""

    def test_scheduler_status_json_output(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler status returns valid JSON."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert "enabled" in output
        assert "jobs" in output
        assert output["enabled"] is True
        assert len(output["jobs"]) == 2

    def test_scheduler_status_json_job_details(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler status --json includes job details."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        jobs = output["jobs"]

        assert jobs[0]["id"] == "job-001"
        assert jobs[0]["cron"] == "0 * * * *"
        assert jobs[0]["handler"] == "test_handler"
        assert jobs[0]["enabled"] is True

        assert jobs[1]["id"] == "job-002"
        assert jobs[1]["enabled"] is False

    def test_scheduler_status_json_when_disabled(self, runner: CliRunner, disabled_config: Config) -> None:
        """Test scheduler status --json with scheduler disabled."""
        result = runner.invoke(
            scheduler_status,
            obj={"config": disabled_config, "output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["enabled"] is False
        assert len(output["jobs"]) == 0


# ============================================================================
# Scheduler Command Tests - Integration
# ============================================================================


class TestSchedulerIntegration:
    """Tests for scheduler command integration."""

    def test_scheduler_commands_all_work(self, runner: CliRunner, sample_config: Config) -> None:
        """Test all scheduler commands can be invoked."""
        # Test start
        result_start = runner.invoke(
            scheduler_start,
            obj={"config": sample_config, "output_json": True},
        )
        assert result_start.exit_code == 0

        # Test status
        result_status = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": True},
        )
        assert result_status.exit_code == 0

        # Test stop
        result_stop = runner.invoke(
            scheduler_stop,
            obj={"output_json": True},
        )
        assert result_stop.exit_code == 0


# ============================================================================
# Scheduler Command Tests - Edge Cases
# ============================================================================


class TestSchedulerEdgeCases:
    """Tests for scheduler command edge cases."""

    def test_scheduler_start_with_zero_jobs(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test scheduler start with no configured jobs."""
        config = Config(state_dir=str(temp_state_dir))
        config.scheduler = MagicMock()
        config.scheduler.enabled = True
        config.scheduler.check_interval_seconds = 60
        config.scheduler.jobs = []

        result = runner.invoke(
            scheduler_start,
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["jobs_count"] == 0

    def test_scheduler_start_with_many_jobs(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test scheduler start with many configured jobs."""
        config = Config(state_dir=str(temp_state_dir))
        config.scheduler = MagicMock()
        config.scheduler.enabled = True
        config.scheduler.check_interval_seconds = 60

        # Create 10 mock jobs
        config.scheduler.jobs = [
            MagicMock(id=f"job-{i:03d}", cron=f"{i} * * * *", handler=f"handler_{i}", enabled=True)
            for i in range(10)
        ]

        result = runner.invoke(
            scheduler_start,
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["jobs_count"] == 10

    def test_scheduler_status_with_unicode_job_id(self, runner: CliRunner, temp_state_dir: Path) -> None:
        """Test scheduler status handles unicode in job data."""
        config = Config(state_dir=str(temp_state_dir))
        config.scheduler = MagicMock()
        config.scheduler.enabled = True
        config.scheduler.check_interval_seconds = 60
        config.scheduler.jobs = [
            MagicMock(id="job-测试", cron="0 * * * *", handler="test_handler", enabled=True),
        ]

        result = runner.invoke(
            scheduler_status,
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert len(output["jobs"]) == 1

    def test_scheduler_start_port_boundary_values(self, runner: CliRunner, sample_config: Config) -> None:
        """Test scheduler start with boundary port values."""
        # Test minimum valid port
        result_min = runner.invoke(
            scheduler_start,
            ["--port", "1"],
            obj={"config": sample_config, "output_json": True},
        )
        assert result_min.exit_code == 0

        # Test maximum valid port
        result_max = runner.invoke(
            scheduler_start,
            ["--port", "65535"],
            obj={"config": sample_config, "output_json": True},
        )
        assert result_max.exit_code == 0

    def test_scheduler_multiple_status_calls_consistent(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test scheduler status returns consistent data across calls."""
        result1 = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": True},
        )
        result2 = runner.invoke(
            scheduler_status,
            obj={"config": sample_config, "output_json": True},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0

        output1 = json.loads(result1.output)
        output2 = json.loads(result2.output)

        assert output1 == output2
