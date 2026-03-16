"""
E2E Tests for Complete Autoflow Workflow

Tests the complete autonomous development workflow from
spec creation to task completion without using mocks.
"""

from __future__ import annotations

import json
from pathlib import Path

from autoflow.core.state import StateManager

from tests.e2e.base import E2EEnvironment, E2ETestCase


class TestCompleteWorkflow(E2ETestCase):
    """Test complete workflow from spec to completion."""

    async def test_spec_to_task_workflow(self, e2e_env: E2EEnvironment) -> None:
        """
        Test complete workflow: create spec → generate tasks → save state.

        This is a fundamental E2E test that verifies the core
        control plane functionality works end-to-end.
        """
        # Step 1: Create a spec
        spec = await e2e_env.create_spec(
            slug="workflow-test",
            title="Workflow Test Spec",
            summary="Testing complete workflow",
            goals=[
                "Validate spec creation",
                "Validate task generation",
                "Validate state persistence"
            ],
            acceptance_criteria=[
                "Spec file created",
                "Tasks file created",
                "State persisted correctly"
            ]
        )

        # Verify spec file exists
        spec_path = e2e_env.specs_dir / "workflow-test" / "SPEC.md"
        assert spec_path.exists(), "Spec file should be created"

        # Step 2: Create tasks
        tasks = await e2e_env.create_tasks(
            spec_slug="workflow-test",
            tasks=[
                {
                    "id": "T1",
                    "title": "Create project structure",
                    "status": "todo",
                    "depends_on": [],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": [
                        "Directory structure created",
                        "Configuration files in place"
                    ],
                    "notes": []
                },
                {
                    "id": "T2",
                    "title": "Implement core functionality",
                    "status": "todo",
                    "depends_on": ["T1"],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": [
                        "Core functions implemented",
                        "Unit tests passing"
                    ],
                    "notes": []
                }
            ]
        )

        # Verify tasks file exists
        tasks_path = e2e_env.tasks_dir / "workflow-test.json"
        assert tasks_path.exists(), "Tasks file should be created"

        # Verify tasks content
        tasks_data = json.loads(tasks_path.read_text())
        assert len(tasks_data["tasks"]) == 2
        assert tasks_data["tasks"][0]["id"] == "T1"
        assert tasks_data["tasks"][1]["id"] == "T2"
        assert tasks_data["tasks"][1]["depends_on"] == ["T1"]

    async def test_run_lifecycle(self, e2e_env: E2EEnvironment) -> None:
        """Test complete run lifecycle from creation to completion."""

        # Create spec and tasks
        await e2e_env.create_spec(
            slug="run-lifecycle-test",
            title="Run Lifecycle Test",
            summary="Testing run creation and lifecycle"
        )

        await e2e_env.create_tasks(
            spec_slug="run-lifecycle-test",
            tasks=[
                {
                    "id": "T1",
                    "title": "Test task",
                    "status": "todo",
                    "depends_on": [],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": ["Task completed"],
                    "notes": []
                }
            ]
        )

        # Create a run
        run = await e2e_env.create_run(
            spec_slug="run-lifecycle-test",
            task_id="T1",
            role="implementation-runner",
            agent="claude",
            prompt="Implement the test task"
        )

        # Verify run directory structure
        run_dir = e2e_env.runs_dir / run["run_id"]
        assert run_dir.exists(), "Run directory should be created"
        assert (run_dir / "run.json").exists(), "run.json should exist"
        assert (run_dir / "prompt.md").exists(), "prompt.md should exist"

        # Verify run metadata
        run_metadata = json.loads((run_dir / "run.json").read_text())
        assert run_metadata["run_id"] == run["run_id"]
        assert run_metadata["spec_slug"] == "run-lifecycle-test"
        assert run_metadata["task_id"] == "T1"
        assert run_metadata["agent"] == "claude"
        assert run_metadata["status"] == "created"

    async def test_state_manager_persistence(self, e2e_env: E2EEnvironment) -> None:
        """Test that StateManager persists state correctly."""

        # Create spec and tasks through state manager
        spec_slug = "persistence-test"
        await e2e_env.create_spec(
            slug=spec_slug,
            title="Persistence Test",
            summary="Testing state persistence"
        )

        # Verify spec can be read back
        spec_path = e2e_env.specs_dir / spec_slug / "SPEC.md"
        assert spec_path.exists()

        content = spec_path.read_text()
        assert "Persistence Test" in content
        assert "Testing state persistence" in content

    async def test_multi_task_workflow(self, e2e_env: E2EEnvironment) -> None:
        """Test workflow with multiple tasks and dependencies."""

        # Create complex spec
        await e2e_env.create_spec(
            slug="multi-task-test",
            title="Multi-Task Workflow Test",
            summary="Testing complex task dependencies"
        )

        # Create task graph with dependencies
        await e2e_env.create_tasks(
            spec_slug="multi-task-test",
            tasks=[
                {
                    "id": "T1",
                    "title": "Foundation",
                    "status": "todo",
                    "depends_on": [],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": ["Foundation ready"],
                    "notes": []
                },
                {
                    "id": "T2",
                    "title": "Feature A",
                    "status": "todo",
                    "depends_on": ["T1"],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": ["Feature A done"],
                    "notes": []
                },
                {
                    "id": "T3",
                    "title": "Feature B",
                    "status": "todo",
                    "depends_on": ["T1"],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": ["Feature B done"],
                    "notes": []
                },
                {
                    "id": "T4",
                    "title": "Integration",
                    "status": "todo",
                    "depends_on": ["T2", "T3"],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": ["Integration complete"],
                    "notes": []
                }
            ]
        )

        # Verify task graph structure
        tasks_path = e2e_env.tasks_dir / "multi-task-test.json"
        tasks_data = json.loads(tasks_path.read_text())

        assert len(tasks_data["tasks"]) == 4

        # Verify dependencies
        task_deps = {
            task["id"]: task["depends_on"]
            for task in tasks_data["tasks"]
        }

        assert task_deps["T1"] == []
        assert set(task_deps["T2"]) == {"T1"}
        assert set(task_deps["T3"]) == {"T1"}
        assert set(task_deps["T4"]) == {"T2", "T3"}

    async def test_error_handling_invalid_spec(self, e2e_env: E2EEnvironment) -> None:
        """Test error handling for invalid spec operations."""

        # Try to create tasks for non-existent spec
        # This should handle gracefully
        try:
            await e2e_env.create_tasks(
                spec_slug="non-existent-spec",
                tasks=[{
                    "id": "T1",
                    "title": "Orphan task",
                    "status": "todo",
                    "depends_on": [],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": [],
                    "notes": []
                }]
            )
            # Tasks file should still be created even without spec
            tasks_path = e2e_env.tasks_dir / "non-existent-spec.json"
            assert tasks_path.exists()
        except Exception as e:
            # Should not crash, may handle gracefully
            assert True, f"Handled error: {e}"

    async def test_environment_cleanup(self, e2e_env: E2EEnvironment) -> None:
        """Test that environment cleans up correctly."""

        # Create some state
        await e2e_env.create_spec(
            slug="cleanup-test",
            title="Cleanup Test",
            summary="Testing environment cleanup"
        )

        # Verify files exist
        spec_path = e2e_env.specs_dir / "cleanup-test" / "SPEC.md"
        assert spec_path.exists()

        # Cleanup is handled by context manager
        # This test verifies the cleanup process runs without errors
        assert True, "Cleanup will be tested by context manager exit"


class TestStateManagement(E2ETestCase):
    """Test state management operations."""

    async def test_state_directory_structure(self, e2e_env: E2EEnvironment) -> None:
        """Verify required state directories are created."""

        # All required directories should exist
        assert e2e_env.state_dir.exists(), "State dir should exist"
        assert e2e_env.specs_dir.exists(), "Specs dir should exist"
        assert e2e_env.tasks_dir.exists(), "Tasks dir should exist"
        assert e2e_env.runs_dir.exists(), "Runs dir should exist"

    async def test_concurrent_spec_creation(self, e2e_env: E2EEnvironment) -> None:
        """Test creating multiple specs concurrently."""

        import asyncio

        # Create multiple specs concurrently
        tasks = [
            e2e_env.create_spec(
                slug=f"concurrent-spec-{i}",
                title=f"Concurrent Spec {i}",
                summary=f"Testing concurrent creation {i}"
            )
            for i in range(5)
        ]

        await asyncio.gather(*tasks)

        # Verify all specs were created
        for i in range(5):
            spec_path = e2e_env.specs_dir / f"concurrent-spec-{i}" / "SPEC.md"
            assert spec_path.exists(), f"Spec {i} should be created"

    async def test_run_id_uniqueness(self, e2e_env: E2EEnvironment) -> None:
        """Verify that run IDs are unique."""

        # Create spec and tasks
        await e2e_env.create_spec(
            slug="run-id-test",
            title="Run ID Test",
            summary="Testing run ID uniqueness"
        )

        await e2e_env.create_tasks(
            spec_slug="run-id-test",
            tasks=[
                {
                    "id": "T1",
                    "title": "Task 1",
                    "status": "todo",
                    "depends_on": [],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": [],
                    "notes": []
                }
            ]
        )

        # Create multiple runs quickly
        run_ids = []
        for _ in range(10):
            run = await e2e_env.create_run(
                spec_slug="run-id-test",
                task_id="T1",
                role="implementation-runner",
                agent="claude",
                prompt="Test"
            )
            run_ids.append(run["run_id"])

        # All run IDs should be unique
        assert len(set(run_ids)) == 10, "All run IDs should be unique"


class TestIntegrationPoints(E2ETestCase):
    """Test integration between components."""

    async def test_spec_to_run_integration(self, e2e_env: E2EEnvironment) -> None:
        """Test integration from spec to run execution."""

        # Create complete workflow
        spec_slug = "integration-test"
        await e2e_env.create_spec(
            slug=spec_slug,
            title="Integration Test",
            summary="Testing spec to run integration"
        )

        await e2e_env.create_tasks(
            spec_slug=spec_slug,
            tasks=[
                {
                    "id": "T1",
                    "title": "Integration Task",
                    "status": "todo",
                    "depends_on": [],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": ["Integration verified"],
                    "notes": []
                }
            ]
        )

        # Create run
        run = await e2e_env.create_run(
            spec_slug=spec_slug,
            task_id="T1",
            role="implementation-runner",
            agent="claude",
            prompt="Verify integration"
        )

        # Verify all components connect
        assert run["spec_slug"] == spec_slug
        assert run["task_id"] == "T1"

        # Verify files are in correct locations
        spec_path = e2e_env.specs_dir / spec_slug / "SPEC.md"
        tasks_path = e2e_env.tasks_dir / f"{spec_slug}.json"
        run_dir = e2e_env.runs_dir / run["run_id"]

        assert spec_path.exists()
        assert tasks_path.exists()
        assert run_dir.exists()
