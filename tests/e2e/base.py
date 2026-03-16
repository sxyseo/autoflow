"""
E2E Test Framework Base Classes

Provides base classes and utilities for end-to-end testing of Autoflow.
This framework tests complete workflows in real environments without mocks.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import pytest
from pydantic import BaseModel

from autoflow.core.state import StateManager
from autoflow.scheduler.task_scheduler import ScheduledTask


class TestEnvironment(BaseModel):
    """Test environment configuration."""

    name: str
    base_dir: Path
    state_dir: Path
    work_dir: Path
    is_isolated: bool = True

    class Config:
        arbitrary_types_allowed = True


class E2EEnvironment:
    """
    Manages E2E test environment lifecycle.

    Creates isolated test environments with real dependencies
    for comprehensive end-to-end testing.
    """

    def __init__(
        self,
        name: str,
        isolated: bool = True,
        cleanup: bool = True,
    ) -> None:
        """
        Initialize E2E test environment.

        Args:
            name: Unique name for this test environment
            isolated: If True, creates isolated directories
            cleanup: If True, auto-cleanup on exit
        """
        self.name = name
        self._isolated = isolated
        self._auto_cleanup = cleanup
        self._initialized = False

        # Directory paths
        if isolated:
            self._temp_dir = tempfile.mkdtemp(prefix=f"autoflow_e2e_{name}_")
            self.base_dir = Path(self._temp_dir)
        else:
            self.base_dir = Path.cwd()

        self.state_dir = self.base_dir / ".autoflow"
        self.work_dir = self.base_dir / "work"
        self.specs_dir = self.state_dir / "specs"
        self.tasks_dir = self.state_dir / "tasks"
        self.runs_dir = self.state_dir / "runs"

        # Components
        self.state_manager: Optional[StateManager] = None
        self.scheduler: Optional[ScheduledTask] = None

    async def __aenter__(self) -> E2EEnvironment:
        """Async context manager entry."""
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._auto_cleanup:
            await self.cleanup()

    async def setup(self) -> None:
        """
        Setup the test environment.

        Creates directories, initializes state manager,
        and prepares the environment for testing.
        """
        if self._initialized:
            return

        # Create directories
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.specs_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state manager
        self.state_manager = StateManager(self.state_dir)
        self.state_manager.initialize()

        self._initialized = True

    async def cleanup(self) -> None:
        """
        Cleanup the test environment.

        Stops all running tasks, closes connections,
        and removes temporary directories.
        """
        if not self._initialized:
            return

        # Stop scheduler if running
        if self.scheduler:
            await self.scheduler.stop()
            self.scheduler = None

        # Cleanup state manager
        self.state_manager = None

        # Remove temp directory if isolated
        if self._isolated and self._temp_dir and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)

        self._initialized = False

    async def create_spec(
        self,
        slug: str,
        title: str,
        summary: str,
        **kwargs
    ) -> dict[str, Any]:
        """
        Create a spec in the test environment.

        Args:
            slug: Unique identifier for the spec
            title: Human-readable title
            summary: Brief description
            **kwargs: Additional spec fields

        Returns:
            Created spec data
        """
        if not self._initialized:
            raise RuntimeError("Environment not initialized")

        spec_data = {
            "slug": slug,
            "title": title,
            "summary": summary,
            **kwargs
        }

        spec_path = self.specs_dir / slug / "SPEC.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)

        # Write spec file
        spec_content = f"""# {title}

## Summary

{summary}

## Goals

{kwargs.get('goals', 'TBD')}

## Acceptance Criteria

{kwargs.get('acceptance_criteria', 'TBD')}
"""
        spec_path.write_text(spec_content)

        return spec_data

    async def create_tasks(
        self,
        spec_slug: str,
        tasks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Create tasks for a spec.

        Args:
            spec_slug: Spec identifier
            tasks: List of task definitions

        Returns:
            Tasks file data
        """
        if not self._initialized:
            raise RuntimeError("Environment not initialized")

        tasks_data = {
            "spec_slug": spec_slug,
            "updated_at": datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
            "tasks": tasks
        }

        tasks_path = self.tasks_dir / f"{spec_slug}.json"
        import json
        tasks_path.write_text(json.dumps(tasks_data, indent=2))

        return tasks_data

    async def create_run(
        self,
        spec_slug: str,
        task_id: str,
        role: str,
        agent: str,
        prompt: str,
    ) -> dict[str, Any]:
        """
        Create a run in the test environment.

        Args:
            spec_slug: Spec identifier
            task_id: Task identifier
            role: Role for the run
            agent: Agent to use
            prompt: Prompt for the agent

        Returns:
            Run metadata
        """
        if not self._initialized:
            raise RuntimeError("Environment not initialized")

        run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create run metadata
        run_metadata = {
            "run_id": run_id,
            "spec_slug": spec_slug,
            "task_id": task_id,
            "role": role,
            "agent": agent,
            "created_at": datetime.utcnow().isoformat(),
            "status": "created",
        }

        # Write metadata
        import json
        (run_dir / "run.json").write_text(json.dumps(run_metadata, indent=2))

        # Write prompt
        (run_dir / "prompt.md").write_text(prompt)

        return run_metadata

    async def wait_for_run_completion(
        self,
        run_id: str,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        """
        Wait for a run to complete.

        Args:
            run_id: Run identifier
            timeout: Maximum wait time in seconds
            poll_interval: Check interval in seconds

        Returns:
            Final run status
        """
        if not self._initialized:
            raise RuntimeError("Environment not initialized")

        run_dir = self.runs_dir / run_id
        metadata_path = run_dir / "run.json"

        start_time = asyncio.get_event_loop().time()

        while True:
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")

            # Read metadata
            if not metadata_path.exists():
                await asyncio.sleep(poll_interval)
                continue

            import json
            metadata = json.loads(metadata_path.read_text())

            # Check if complete
            if metadata.get("status") in ["success", "failed", "cancelled"]:
                return metadata

            await asyncio.sleep(poll_interval)

    async def get_task_status(self, spec_slug: str, task_id: str) -> str:
        """
        Get the status of a task.

        Args:
            spec_slug: Spec identifier
            task_id: Task identifier

        Returns:
            Task status
        """
        if not self._initialized:
            raise RuntimeError("Environment not initialized")

        tasks_path = self.tasks_dir / f"{spec_slug}.json"
        if not tasks_path.exists():
            return "not_found"

        import json
        tasks_data = json.loads(tasks_path.read_text())

        for task in tasks_data.get("tasks", []):
            if task.get("id") == task_id:
                return task.get("status", "unknown")

        return "not_found"

    def get_environment_info(self) -> dict[str, Any]:
        """
        Get information about the test environment.

        Returns:
            Environment information dictionary
        """
        return {
            "name": self.name,
            "base_dir": str(self.base_dir),
            "state_dir": str(self.state_dir),
            "work_dir": str(self.work_dir),
            "isolated": self._isolated,
            "initialized": self._initialized,
        }


class E2ETestCase:
    """
    Base class for E2E tests.

    Provides common setup/teardown and helper methods
    for end-to-end testing.
    """

    @pytest.fixture
    async def e2e_env(self):
        """
        Fixture providing E2E test environment.

        Automatically manages environment lifecycle.
        """
        env_name = f"test_{self.__class__.__name__}"

        async with E2EEnvironment(name=env_name) as env:
            yield env

    @pytest.fixture
    async def sample_spec(self, e2e_env: E2EEnvironment):
        """
        Fixture providing a sample spec.

        Creates a basic spec for testing.
        """
        return await e2e_env.create_spec(
            slug="test-spec",
            title="Test Spec",
            summary="A spec for E2E testing",
            goals=["Test goal 1", "Test goal 2"],
            acceptance_criteria=["Criteria 1", "Criteria 2"]
        )

    async def wait_for_condition(
        self,
        condition: Callable[[], bool],
        timeout: float = 60.0,
        poll_interval: float = 0.5,
        error_message: str = "Condition not met",
    ) -> bool:
        """
        Wait for a condition to become true.

        Args:
            condition: Function that returns bool
            timeout: Maximum wait time
            poll_interval: Check interval
            error_message: Error message on timeout

        Returns:
            True if condition met

        Raises:
            TimeoutError: If condition not met within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            if condition():
                return True

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(f"{error_message} (waited {elapsed:.1f}s)")

            await asyncio.sleep(poll_interval)

    async def assert_file_exists(self, path: Path, timeout: float = 5.0) -> None:
        """
        Assert that a file exists, with timeout.

        Args:
            path: File path to check
            timeout: Maximum wait time

        Raises:
            AssertionError: If file doesn't exist within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            if path.exists():
                return

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                raise AssertionError(f"File does not exist: {path}")

            await asyncio.sleep(0.1)

    async def assert_json_file_contains(
        self,
        path: Path,
        key: str,
        value: Any,
        timeout: float = 5.0,
    ) -> None:
        """
        Assert that a JSON file contains a key-value pair.

        Args:
            path: JSON file path
            key: Key to check
            value: Expected value
            timeout: Maximum wait time

        Raises:
            AssertionError: If condition not met within timeout
        """
        await self.assert_file_exists(path, timeout)

        import json
        data = json.loads(path.read_text())

        if key not in data:
            raise AssertionError(f"Key '{key}' not found in {path}")

        if data[key] != value:
            raise AssertionError(
                f"Expected {key}={value}, got {data[key]} in {path}"
            )
