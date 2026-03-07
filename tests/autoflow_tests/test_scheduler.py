"""
Tests for the scheduler module.
"""

import json
import pytest
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock, AsyncMock
import tempfile

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from scheduler import (
    SchedulerConfig,
    JobRegistry,
    cmd_status,
    cmd_add_job,
    cmd_list_jobs,
    cmd_remove_job,
    cmd_run_once,
    APSCHEDULER_AVAILABLE,
)


class TestSchedulerConfig:
    """Tests for SchedulerConfig class."""

    def test_default_config(self):
        """Test that default configuration is loaded."""
        config = SchedulerConfig()
        assert config.timezone == "UTC"
        assert config.max_instances >= 1

    def test_jobs_property(self):
        """Test that jobs property returns configured jobs."""
        config = SchedulerConfig()
        jobs = config.jobs
        assert isinstance(jobs, dict)

    def test_job_defaults_property(self):
        """Test that job_defaults property returns defaults."""
        config = SchedulerConfig()
        defaults = config.job_defaults
        assert isinstance(defaults, dict)

    def test_get_job_config_existing(self):
        """Test getting configuration for an existing job type."""
        config = SchedulerConfig()
        # Check if any jobs exist first
        if config.jobs:
            job_type = list(config.jobs.keys())[0]
            job_config = config.get_job_config(job_type)
            assert job_config is not None

    def test_get_job_config_nonexistent(self):
        """Test getting configuration for a nonexistent job type."""
        config = SchedulerConfig()
        job_config = config.get_job_config("nonexistent_job_type")
        assert job_config is None

    def test_custom_config_path(self, tmp_path):
        """Test loading config from custom path."""
        config_path = tmp_path / "custom_scheduler_config.json"
        custom_config = {
            "scheduler": {
                "timezone": "America/New_York",
                "max_instances": 5
            },
            "jobs": {},
            "job_defaults": {}
        }
        with open(config_path, "w") as f:
            json.dump(custom_config, f)

        config = SchedulerConfig(config_path)
        assert config.timezone == "America/New_York"
        assert config.max_instances == 5

    def test_save_config(self, tmp_path):
        """Test saving configuration to file."""
        config_path = tmp_path / "config" / "scheduler_config.json"
        config = SchedulerConfig(config_path)
        config.save()

        assert config_path.exists()


class TestJobRegistry:
    """Tests for JobRegistry class."""

    def test_registry_initialization(self):
        """Test that registry can be initialized."""
        registry = JobRegistry()
        assert registry is not None

    def test_builtin_jobs_registered(self):
        """Test that built-in jobs are registered."""
        registry = JobRegistry()
        jobs = registry.list_jobs()

        assert "continuous_iteration" in jobs
        assert "nightly_maintenance" in jobs
        assert "weekly_consolidation" in jobs
        assert "monthly_dependency_update" in jobs

    def test_get_existing_job(self):
        """Test getting an existing job function."""
        registry = JobRegistry()
        job_func = registry.get("continuous_iteration")

        assert job_func is not None
        assert callable(job_func)

    def test_get_nonexistent_job(self):
        """Test getting a nonexistent job function."""
        registry = JobRegistry()
        job_func = registry.get("nonexistent_job")

        assert job_func is None

    def test_list_jobs(self):
        """Test listing all registered jobs."""
        registry = JobRegistry()
        jobs = registry.list_jobs()

        assert isinstance(jobs, list)
        assert len(jobs) >= 4  # At least the 4 built-in jobs

    def test_register_custom_job(self):
        """Test registering a custom job."""
        registry = JobRegistry()

        async def custom_job():
            return {"success": True}

        registry.register("custom_job", custom_job)

        assert "custom_job" in registry.list_jobs()
        assert registry.get("custom_job") == custom_job


class TestJobRegistryJobExecution:
    """Tests for JobRegistry job execution."""

    @pytest.mark.asyncio
    async def test_continuous_iteration_job(self):
        """Test continuous iteration job execution."""
        registry = JobRegistry()
        job_func = registry.get("continuous_iteration")

        result = await job_func()

        assert "job" in result
        assert result["job"] == "continuous_iteration"
        assert "success" in result

    @pytest.mark.asyncio
    async def test_nightly_maintenance_job(self):
        """Test nightly maintenance job execution."""
        registry = JobRegistry()
        job_func = registry.get("nightly_maintenance")

        result = await job_func()

        assert "job" in result
        assert result["job"] == "nightly_maintenance"
        assert "success" in result

    @pytest.mark.asyncio
    async def test_weekly_consolidation_job(self):
        """Test weekly consolidation job execution."""
        registry = JobRegistry()
        job_func = registry.get("weekly_consolidation")

        result = await job_func()

        assert "job" in result
        assert result["job"] == "weekly_consolidation"
        assert "success" in result

    @pytest.mark.asyncio
    async def test_monthly_dependency_update_job(self):
        """Test monthly dependency update job execution."""
        registry = JobRegistry()
        job_func = registry.get("monthly_dependency_update")

        result = await job_func()

        assert "job" in result
        assert result["job"] == "monthly_dependency_update"
        assert "success" in result


class TestCmdStatus:
    """Tests for cmd_status function."""

    def test_cmd_status_returns_zero(self):
        """Test that status command returns 0."""
        args = MagicMock()

        result = cmd_status(args)

        assert result == 0


class TestCmdAddJob:
    """Tests for cmd_add_job function."""

    def test_cmd_add_job(self, tmp_path, monkeypatch):
        """Test adding a job via CLI."""
        config_path = tmp_path / "config" / "scheduler_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create initial config
        initial_config = {
            "scheduler": {"timezone": "UTC", "max_instances": 3},
            "jobs": {},
            "job_defaults": {"max_instances": 1}
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        args.job_type = "custom_job"
        args.cron = "*/10 * * * *"
        args.job_id = None
        args.max_instances = 1
        args.description = "Test job"

        result = cmd_add_job(args)

        assert result == 0


class TestCmdListJobs:
    """Tests for cmd_list_jobs function."""

    def test_cmd_list_jobs_empty(self, tmp_path, monkeypatch):
        """Test listing jobs when none configured."""
        config_path = tmp_path / "config" / "scheduler_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        initial_config = {
            "scheduler": {"timezone": "UTC", "max_instances": 3},
            "jobs": {},
            "job_defaults": {"max_instances": 1}
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        result = cmd_list_jobs(args)

        assert result == 0

    def test_cmd_list_jobs_with_jobs(self, tmp_path, monkeypatch):
        """Test listing jobs with configured jobs."""
        config_path = tmp_path / "config" / "scheduler_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        initial_config = {
            "scheduler": {"timezone": "UTC", "max_instances": 3},
            "jobs": {
                "test_job": {
                    "enabled": True,
                    "cron": "*/5 * * * *",
                    "description": "Test job"
                }
            },
            "job_defaults": {"max_instances": 1}
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        result = cmd_list_jobs(args)

        assert result == 0


class TestCmdRemoveJob:
    """Tests for cmd_remove_job function."""

    def test_cmd_remove_job_existing(self, tmp_path, monkeypatch):
        """Test removing an existing job."""
        config_path = tmp_path / "config" / "scheduler_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        initial_config = {
            "scheduler": {"timezone": "UTC", "max_instances": 3},
            "jobs": {
                "job_to_remove": {
                    "enabled": True,
                    "cron": "*/5 * * * *"
                }
            },
            "job_defaults": {"max_instances": 1}
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        args.job_id = "job_to_remove"
        result = cmd_remove_job(args)

        assert result == 0

    def test_cmd_remove_job_nonexistent(self, tmp_path, monkeypatch):
        """Test removing a nonexistent job."""
        config_path = tmp_path / "config" / "scheduler_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        initial_config = {
            "scheduler": {"timezone": "UTC", "max_instances": 3},
            "jobs": {},
            "job_defaults": {"max_instances": 1}
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        args.job_id = "nonexistent_job"
        result = cmd_remove_job(args)

        assert result == 1


class TestCmdRunOnce:
    """Tests for cmd_run_once function."""

    def test_cmd_run_once_unknown_job(self):
        """Test running an unknown job type."""
        args = MagicMock()
        args.job_type = "unknown_job_type"
        args.verbose = False

        result = cmd_run_once(args)

        assert result == 1

    def test_cmd_run_once_known_job(self):
        """Test running a known job type."""
        args = MagicMock()
        args.job_type = "weekly_consolidation"  # Simple job that doesn't require subprocess
        args.verbose = True

        result = cmd_run_once(args)

        assert result == 0


class TestSchedulerAvailability:
    """Tests for scheduler availability check."""

    def test_apscheduler_available_flag(self):
        """Test that APSCHEDULER_AVAILABLE flag is set correctly."""
        # This should be a boolean
        assert isinstance(APSCHEDULER_AVAILABLE, bool)
