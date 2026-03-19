"""
Unit Tests for list-runs CLI Functionality

Tests the autoflow CLI tool for listing runs with optional filtering
by spec, status, role, and agent.

These tests use temporary directories and mock git repositories to
avoid requiring actual project setups or external services.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def configure_autoflow_module(module: ModuleType, root: Path) -> None:
    module.ROOT = root
    module.STATE_DIR = root / ".autoflow"
    module.SPECS_DIR = module.STATE_DIR / "specs"
    module.TASKS_DIR = module.STATE_DIR / "tasks"
    module.RUNS_DIR = module.STATE_DIR / "runs"
    module.LOGS_DIR = module.STATE_DIR / "logs"
    module.WORKTREES_DIR = module.STATE_DIR / "worktrees" / "tasks"
    module.MEMORY_DIR = module.STATE_DIR / "memory"
    module.STRATEGY_MEMORY_DIR = module.MEMORY_DIR / "strategy"
    module.DISCOVERY_FILE = module.STATE_DIR / "discovered_agents.json"
    module.SYSTEM_CONFIG_FILE = module.STATE_DIR / "system.json"
    module.SYSTEM_CONFIG_TEMPLATE = root / "config" / "system.example.json"
    module.AGENTS_FILE = module.STATE_DIR / "agents.json"
    module.BMAD_DIR = root / "templates" / "bmad"


class ListRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "config" / "system.example.json").write_text(
            json.dumps(
                {
                    "memory": {
                        "enabled": True,
                        "auto_capture_run_results": True,
                        "default_scopes": ["spec"],
                        "global_file": ".autoflow/memory/global.md",
                        "spec_dir": ".autoflow/memory/specs",
                    },
                    "models": {
                        "profiles": {
                            "implementation": "gpt-5-codex",
                            "review": "claude-sonnet-4-6",
                        }
                    },
                    "tools": {"profiles": {"claude-review": ["Read", "Bash(git:*)"]}},
                    "registry": {"acp_agents": []},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "templates" / "bmad").mkdir(parents=True, exist_ok=True)
        for role in [
            "spec-writer",
            "task-graph-manager",
            "implementation-runner",
            "reviewer",
            "maintainer",
        ]:
            (self.root / "templates" / "bmad" / f"{role}.md").write_text(
                f"# {role}\n", encoding="utf-8"
            )
        self.autoflow = load_module(
            self.repo_root / "scripts" / "autoflow.py", "autoflow_runs_test"
        )
        configure_autoflow_module(self.autoflow, self.root)
        self.autoflow.ensure_state()
        self.autoflow.write_json(
            self.autoflow.AGENTS_FILE,
            {
                "agents": {
                    "dummy": {
                        "command": "echo",
                        "args": ["agent"],
                        "memory_scopes": ["spec"],
                    },
                }
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_spec(self, slug: str = "test-spec", approve: bool = True, impl_tasks: int = 3) -> None:
        """Create a spec and optionally approve it for implementation.

        Args:
            slug: The spec slug
            approve: Whether to approve the spec (required for implementation runs)
            impl_tasks: Number of additional implementation tasks to add (default 3)
        """
        args = SimpleNamespace(slug=slug, title="Test Spec", summary="Test spec for list-runs")
        with redirect_stdout(io.StringIO()):
            self.autoflow.create_spec(args)

        # The base spec already creates T1-T5:
        # T1: spec-writer, T2: task-graph-manager, T3: implementation-runner,
        # T4: reviewer, T5: maintainer
        # Add more implementation tasks if requested
        if impl_tasks > 0:
            tasks = self.autoflow.load_tasks(slug)
            # Start from T6 (after the base tasks)
            for i in range(impl_tasks):
                tasks["tasks"].append({
                    "id": f"T{6 + i}",
                    "title": f"Implementation task {i + 1}",
                    "status": "todo",
                    "dependencies": [f"T{j}" for j in range(1, 3)],  # Depend on planning tasks
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": [f"Criterion {i + 1}"]
                })
            self.autoflow.save_tasks(slug, tasks, reason="test_setup")

        # Approve the spec if requested (needed for implementation-runner roles)
        if approve:
            tasks = self.autoflow.load_tasks(slug)
            # Mark planning tasks as done
            for task in tasks["tasks"]:
                if task.get("owner_role") in ["spec-writer", "task-graph-manager"]:
                    task["status"] = "done"
            self.autoflow.save_tasks(slug, tasks, reason="test_setup")

            with redirect_stdout(io.StringIO()):
                self.autoflow.approve_spec(
                    SimpleNamespace(spec=slug, approved_by="test-suite")
                )

    def create_run(
        self,
        spec: str,
        role: str,
        agent: str = "dummy",
        task: str | None = None,
    ) -> str:
        """Create a run and return the run ID.

        Args:
            spec: The spec slug
            role: The role for this run
            agent: The agent to use
            task: Optional task ID. If not provided, finds a task for the role.
        """
        # Find an appropriate task if not specified
        if task is None:
            tasks = self.autoflow.load_tasks(spec)

            # For reviewer, find an implementation task and mark it as in_review
            if role == "reviewer":
                for t in tasks["tasks"]:
                    if t.get("owner_role") == "implementation-runner":
                        t["status"] = "in_review"
                        self.autoflow.save_tasks(spec, tasks, reason="test_setup")
                        task = t["id"]
                        break
                # Fallback: use first available task and mark as in_review
                if task is None and len(tasks["tasks"]) > 0:
                    t = tasks["tasks"][0]
                    t["status"] = "in_review"
                    self.autoflow.save_tasks(spec, tasks, reason="test_setup")
                    task = t["id"]
            else:
                # For other roles, find a task owned by that role
                for t in tasks["tasks"]:
                    if t.get("owner_role") == role:
                        task = t["id"]
                        break

            # Last resort: use first available task
            if task is None and len(tasks["tasks"]) > 0:
                task = tasks["tasks"][0]["id"]

        output = io.StringIO()
        with redirect_stdout(output):
            self.autoflow.create_run(
                SimpleNamespace(
                    spec=spec,
                    role=role,
                    agent=agent,
                    task=task,
                    branch="",
                    resume_from=None,
                )
            )
        return Path(output.getvalue().strip()).name

    def complete_run(self, run_id: str, result: str = "success", summary: str = "Run completed") -> None:
        """Complete a run with the given result and summary."""
        with redirect_stdout(io.StringIO()):
            self.autoflow.complete_run(
                SimpleNamespace(
                    run=run_id,
                    result=result,
                    summary=summary,
                )
            )

    def capture_list_runs_output(self, **kwargs) -> list[dict]:
        """Capture the JSON output from list_runs command."""
        buf = io.StringIO()
        args = SimpleNamespace(**kwargs)
        with redirect_stdout(buf):
            self.autoflow.list_runs(args)
        return json.loads(buf.getvalue())

    def test_list_runs_empty(self) -> None:
        """Test listing runs when no runs exist."""
        runs = self.capture_list_runs_output()
        self.assertEqual(runs, [])

    def test_list_runs_single_run(self) -> None:
        """Test listing a single run."""
        self.create_spec("spec-a")
        run_id = self.create_run("spec-a", "implementation-runner")

        runs = self.capture_list_runs_output()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_id)
        self.assertEqual(runs[0]["spec"], "spec-a")
        self.assertEqual(runs[0]["role"], "implementation-runner")
        self.assertEqual(runs[0]["agent"], "dummy")

    def test_list_runs_multiple_specs(self) -> None:
        """Test listing runs across multiple specs."""
        self.create_spec("spec-a")
        self.create_spec("spec-b")

        run_a1 = self.create_run("spec-a", "implementation-runner")
        run_a2 = self.create_run("spec-a", "reviewer")
        run_b1 = self.create_run("spec-b", "implementation-runner")

        runs = self.capture_list_runs_output()
        self.assertEqual(len(runs), 3)

        # Verify all runs are present
        run_ids = {r["id"] for r in runs}
        self.assertEqual(run_ids, {run_a1, run_a2, run_b1})

    def test_list_runs_filter_by_spec(self) -> None:
        """Test filtering runs by spec."""
        self.create_spec("spec-a")
        self.create_spec("spec-b")

        run_a1 = self.create_run("spec-a", "implementation-runner")
        run_a2 = self.create_run("spec-a", "reviewer")
        run_b1 = self.create_run("spec-b", "implementation-runner")

        # Filter for spec-a
        runs = self.capture_list_runs_output(spec="spec-a")
        self.assertEqual(len(runs), 2)
        run_ids = {r["id"] for r in runs}
        self.assertEqual(run_ids, {run_a1, run_a2})
        for run in runs:
            self.assertEqual(run["spec"], "spec-a")

        # Filter for spec-b
        runs = self.capture_list_runs_output(spec="spec-b")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_b1)

    def test_list_runs_filter_by_status(self) -> None:
        """Test filtering runs by status."""
        self.create_spec("spec-a")
        self.create_spec("spec-b")

        run_created = self.create_run("spec-a", "implementation-runner")
        run_completed = self.create_run("spec-b", "implementation-runner")
        self.complete_run(run_completed, result="success", summary="Completed")

        # Filter for created status
        runs = self.capture_list_runs_output(status="created")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_created)

        # Filter for completed status
        runs = self.capture_list_runs_output(status="completed")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_completed)

    def test_list_runs_filter_by_role(self) -> None:
        """Test filtering runs by role."""
        self.create_spec("spec-a")

        run_impl = self.create_run("spec-a", "implementation-runner")
        run_review = self.create_run("spec-a", "reviewer")
        run_maint = self.create_run("spec-a", "maintainer")

        # Filter for implementation-runner role
        runs = self.capture_list_runs_output(role="implementation-runner")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_impl)

        # Filter for reviewer role
        runs = self.capture_list_runs_output(role="reviewer")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_review)

        # Filter for maintainer role
        runs = self.capture_list_runs_output(role="maintainer")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_maint)

    def test_list_runs_filter_by_agent(self) -> None:
        """Test filtering runs by agent name."""
        self.create_spec("spec-a")

        run_dummy = self.create_run("spec-a", "implementation-runner", agent="dummy")

        runs = self.capture_list_runs_output(agent="dummy")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_dummy)
        self.assertEqual(runs[0]["agent"], "dummy")

    def test_list_runs_filter_by_multiple_criteria(self) -> None:
        """Test filtering runs by multiple criteria."""
        self.create_spec("spec-a")
        self.create_spec("spec-b")

        # Create runs with different combinations
        run_a_impl = self.create_run("spec-a", "implementation-runner")
        run_a_review = self.create_run("spec-a", "reviewer")
        run_b_impl = self.create_run("spec-b", "implementation-runner")

        # Complete one run
        self.complete_run(run_a_impl, result="success", summary="Done")

        # Filter by spec AND role
        runs = self.capture_list_runs_output(spec="spec-a", role="reviewer")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_a_review)

        # Filter by spec AND status
        runs = self.capture_list_runs_output(spec="spec-a", status="completed")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_a_impl)

        # Filter by role AND agent (where agent is default "dummy")
        runs = self.capture_list_runs_output(role="implementation-runner", agent="dummy")
        self.assertEqual(len(runs), 2)
        run_ids = {r["id"] for r in runs}
        self.assertEqual(run_ids, {run_a_impl, run_b_impl})

    def test_list_runs_filter_no_matches(self) -> None:
        """Test filtering when no runs match the criteria."""
        self.create_spec("spec-a")
        self.create_run("spec-a", "implementation-runner")

        # Filter for non-existent spec
        runs = self.capture_list_runs_output(spec="nonexistent")
        self.assertEqual(len(runs), 0)

        # Filter for non-existent status
        runs = self.capture_list_runs_output(status="cancelled")
        self.assertEqual(len(runs), 0)

        # Filter for non-existent role
        runs = self.capture_list_runs_output(role="nonexistent-role")
        self.assertEqual(len(runs), 0)

    def test_list_runs_all_statuses(self) -> None:
        """Test listing runs with various statuses."""
        self.create_spec("spec-a")

        # Create runs with different statuses
        run_created = self.create_run("spec-a", "implementation-runner")

        run_completed = self.create_run("spec-a", "reviewer")
        self.complete_run(run_completed, result="success", summary="Approved")

        # Use T6 which is an additional implementation task (T3 is base impl task, T6 is first additional)
        run_blocked = self.create_run("spec-a", "implementation-runner", task="T6")
        self.complete_run(run_blocked, result="blocked", summary="Blocked")

        # Verify all runs are listed
        runs = self.capture_list_runs_output()
        self.assertEqual(len(runs), 3)

        # Verify statuses
        statuses = {r["id"]: r["status"] for r in runs}
        self.assertEqual(statuses[run_created], "created")
        self.assertEqual(statuses[run_completed], "completed")
        self.assertEqual(statuses[run_blocked], "completed")

    def test_list_runs_sorted_by_id(self) -> None:
        """Test that runs are sorted by ID."""
        # Use a unique spec name to avoid conflicts with other tests
        self.create_spec("spec-sorted", impl_tasks=10)

        # Create multiple runs for different implementation tasks
        # T1: spec-writer, T2: task-graph-manager, T3: base implementation task
        # T4: reviewer, T5: maintainer
        # T6-T15: additional implementation tasks (10 tasks)
        run_ids = []
        for i in range(5):
            task_id = f"T{6 + i}"  # T6, T7, T8, T9, T10 (all implementation-runner)
            run_id = self.create_run("spec-sorted", "implementation-runner", task=task_id)
            run_ids.append(run_id)

        runs = self.capture_list_runs_output()
        # Should have at least our 5 runs (might have more from setup)
        self.assertGreaterEqual(len(runs), 5)

        # Verify sorting (run IDs are timestamps, so should be in ascending order)
        returned_ids = [r["id"] for r in runs]
        self.assertEqual(returned_ids, sorted(returned_ids))

    def test_list_runs_includes_all_metadata_fields(self) -> None:
        """Test that list_runs includes all expected metadata fields."""
        self.create_spec("spec-a")
        run_id = self.create_run("spec-a", "implementation-runner")

        runs = self.capture_list_runs_output()
        self.assertEqual(len(runs), 1)

        run = runs[0]
        # Verify essential fields are present
        self.assertIn("id", run)
        self.assertIn("spec", run)
        self.assertIn("role", run)
        self.assertIn("agent", run)
        self.assertIn("status", run)
        self.assertIn("task", run)
        self.assertIn("created_at", run)


if __name__ == "__main__":
    unittest.main()
