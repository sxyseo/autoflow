"""
Tests for the scheduler module.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from scheduler import (
    APSCHEDULER_AVAILABLE,
    JobRegistry,
    SchedulerConfig,
    cmd_add_job,
    cmd_list_jobs,
    cmd_remove_job,
    cmd_run_once,
    cmd_status,
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
            "scheduler": {"timezone": "America/New_York", "max_instances": 5},
            "jobs": {},
            "job_defaults": {},
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
        """Test continuous iteration job execution with configured args."""
        config_path = Path(__file__).parent / "scheduler-job-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "scheduler": {"timezone": "UTC", "max_instances": 3},
                    "jobs": {
                        "continuous_iteration": {
                            "enabled": True,
                            "cron": "*/5 * * * *",
                            "max_instances": 1,
                            "args": {
                                "spec": "demo-spec",
                                "config": "config/continuous-iteration.example.json",
                                "dispatch": True,
                                "commit_if_dirty": False,
                                "push": False,
                            },
                        }
                    },
                    "job_defaults": {"max_instances": 1},
                }
            ),
            encoding="utf-8",
        )
        registry = JobRegistry(SchedulerConfig(config_path))
        job_func = registry.get("continuous_iteration")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"dispatch":{"dispatched":true}}\n',
            stderr="",
        )
        try:
            with patch("scheduler.subprocess.run", return_value=completed) as mock_run:
                result = await job_func()
        finally:
            config_path.unlink(missing_ok=True)

        assert "job" in result
        assert result["job"] == "continuous_iteration"
        assert result["success"] is True
        assert "--spec" in result["command"]
        assert "demo-spec" in result["command"]
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_continuous_iteration_job_requires_spec(self):
        """Test continuous iteration job fails clearly when spec is missing."""
        config_path = Path(__file__).parent / "scheduler-job-config-missing-spec.json"
        config_path.write_text(
            json.dumps(
                {
                    "scheduler": {"timezone": "UTC", "max_instances": 3},
                    "jobs": {
                        "continuous_iteration": {
                            "enabled": True,
                            "cron": "*/5 * * * *",
                            "max_instances": 1,
                            "args": {},
                        }
                    },
                    "job_defaults": {"max_instances": 1},
                }
            ),
            encoding="utf-8",
        )
        registry = JobRegistry(SchedulerConfig(config_path))
        job_func = registry.get("continuous_iteration")
        try:
            result = await job_func()
        finally:
            config_path.unlink(missing_ok=True)

        assert result["success"] is False
        assert "requires jobs.continuous_iteration.args.spec" in result["error"]

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
        args.config = ""

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
            "job_defaults": {"max_instances": 1},
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
        args.config = ""
        args.spec = ""
        args.iteration_config = ""
        args.dispatch = False
        args.commit_if_dirty = False
        args.push = False

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
            "job_defaults": {"max_instances": 1},
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        args.config = ""
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
                    "description": "Test job",
                }
            },
            "job_defaults": {"max_instances": 1},
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        args.config = ""
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
            "jobs": {"job_to_remove": {"enabled": True, "cron": "*/5 * * * *"}},
            "job_defaults": {"max_instances": 1},
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        args.job_id = "job_to_remove"
        args.config = ""
        result = cmd_remove_job(args)

        assert result == 0

    def test_cmd_remove_job_nonexistent(self, tmp_path, monkeypatch):
        """Test removing a nonexistent job."""
        config_path = tmp_path / "config" / "scheduler_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        initial_config = {
            "scheduler": {"timezone": "UTC", "max_instances": 3},
            "jobs": {},
            "job_defaults": {"max_instances": 1},
        }
        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        monkeypatch.setattr("scheduler.SCHEDULER_CONFIG_PATH", config_path)

        args = MagicMock()
        args.job_id = "nonexistent_job"
        args.config = ""
        result = cmd_remove_job(args)

        assert result == 1


class TestCmdRunOnce:
    """Tests for cmd_run_once function."""

    def test_cmd_run_once_unknown_job(self):
        """Test running an unknown job type."""
        args = MagicMock()
        args.job_type = "unknown_job_type"
        args.verbose = False
        args.config = ""

        result = cmd_run_once(args)

        assert result == 1

    def test_cmd_run_once_known_job(self):
        """Test running a known job type."""
        args = MagicMock()
        args.job_type = (
            "weekly_consolidation"  # Simple job that doesn't require subprocess
        )
        args.verbose = True
        args.config = ""

        result = cmd_run_once(args)

        assert result == 0

    def test_cmd_run_once_continuous_iteration_uses_custom_config(self, tmp_path):
        """Test run-once loads the provided scheduler config."""
        config_path = tmp_path / "scheduler_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "scheduler": {"timezone": "UTC", "max_instances": 3},
                    "jobs": {
                        "continuous_iteration": {
                            "enabled": True,
                            "cron": "*/5 * * * *",
                            "max_instances": 1,
                            "args": {"spec": "demo-spec", "config": "config/continuous-iteration.example.json"},
                        }
                    },
                    "job_defaults": {"max_instances": 1},
                }
            ),
            encoding="utf-8",
        )
        args = MagicMock()
        args.job_type = "continuous_iteration"
        args.verbose = True
        args.config = str(config_path)
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"dispatch":{"dispatched":true}}\n',
            stderr="",
        )

        with patch("scheduler.subprocess.run", return_value=completed):
            result = cmd_run_once(args)

        assert result == 0


class TestSchedulerAvailability:
    """Tests for scheduler availability check."""

    def test_apscheduler_available_flag(self):
        """Test that APSCHEDULER_AVAILABLE flag is set correctly."""
        # This should be a boolean
        assert isinstance(APSCHEDULER_AVAILABLE, bool)
