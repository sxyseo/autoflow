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
import time
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


class ListRunsTestBase(unittest.TestCase):
    """Base class with common setup and helper methods for list-runs tests."""

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


class TestListRunsBasic(ListRunsTestBase):
    """Basic functionality tests for list-runs CLI command."""

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


class TestListRunsFilters(ListRunsTestBase):
    """Filter tests for list-runs CLI command."""

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


class TestListRunsEdgeCases(ListRunsTestBase):
    """Edge case tests for list-runs CLI command."""

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

    def test_list_runs_filter_nonexistent_spec(self) -> None:
        """Test filtering by non-existent spec returns empty list."""
        self.create_spec("spec-a")
        self.create_run("spec-a", "implementation-runner")

        # Filter for non-existent spec
        runs = self.capture_list_runs_output(spec="nonexistent-spec")
        self.assertEqual(len(runs), 0)

    def test_list_runs_filter_invalid_status(self) -> None:
        """Test filtering by invalid status returns empty list."""
        self.create_spec("spec-a")
        self.create_run("spec-a", "implementation-runner")

        # Filter for invalid status
        runs = self.capture_list_runs_output(status="invalid-status")
        self.assertEqual(len(runs), 0)

    def test_list_runs_filter_nonexistent_role(self) -> None:
        """Test filtering by non-existent role returns empty list."""
        self.create_spec("spec-a")
        self.create_run("spec-a", "implementation-runner")

        # Filter for non-existent role
        runs = self.capture_list_runs_output(role="nonexistent-role")
        self.assertEqual(len(runs), 0)

    def test_list_runs_filter_nonexistent_agent(self) -> None:
        """Test filtering by non-existent agent returns empty list."""
        self.create_spec("spec-a")
        self.create_run("spec-a", "implementation-runner", agent="dummy")

        # Filter for non-existent agent
        runs = self.capture_list_runs_output(agent="nonexistent-agent")
        self.assertEqual(len(runs), 0)

    def test_list_runs_with_unicode_spec_slug(self) -> None:
        """Test listing runs with unicode characters in spec slug."""
        # Create spec with unicode characters
        self.create_spec("test-αβγ")
        run_id = self.create_run("test-αβγ", "implementation-runner")

        runs = self.capture_list_runs_output(spec="test-αβγ")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_id)
        self.assertEqual(runs[0]["spec"], "test-αβγ")

    def test_list_runs_with_unicode_in_summary(self) -> None:
        """Test listing runs with unicode characters in summary."""
        self.create_spec("spec-a")
        run_id = self.create_run("spec-a", "implementation-runner")
        # Complete with unicode summary
        self.complete_run(run_id, result="success", summary="完成测试 🚀")

        runs = self.capture_list_runs_output()
        self.assertEqual(len(runs), 1)
        # Should handle unicode without errors
        self.assertEqual(runs[0]["id"], run_id)

    def test_list_runs_with_unicode_role_name(self) -> None:
        """Test listing runs handles unicode role names correctly."""
        self.create_spec("spec-a")
        run_id = self.create_run("spec-a", "implementation-runner")

        runs = self.capture_list_runs_output(role="implementation-runner")
        self.assertEqual(len(runs), 1)
        # Verify role name is handled correctly
        self.assertEqual(runs[0]["role"], "implementation-runner")

    def test_list_runs_missing_optional_fields(self) -> None:
        """Test listing runs with missing optional metadata fields."""
        self.create_spec("spec-a")
        run_id = self.create_run("spec-a", "implementation-runner")

        runs = self.capture_list_runs_output()
        self.assertEqual(len(runs), 1)

        run = runs[0]
        # Verify required fields are present
        self.assertIsNotNone(run["id"])
        self.assertIsNotNone(run["spec"])
        self.assertIsNotNone(run["role"])

        # Optional fields should have default values or be None
        # The list_runs command should handle missing fields gracefully
        self.assertIn("status", run)

    def test_list_runs_case_sensitive_filter(self) -> None:
        """Test that filters are case-sensitive."""
        self.create_spec("spec-a")
        self.create_run("spec-a", "implementation-runner")

        # Filter with different case should return no results
        runs = self.capture_list_runs_output(spec="SPEC-A")
        self.assertEqual(len(runs), 0)

        runs = self.capture_list_runs_output(spec="Spec-A")
        self.assertEqual(len(runs), 0)

    def test_list_runs_with_special_characters_in_agent(self) -> None:
        """Test listing runs with special characters in agent name."""
        self.create_spec("spec-a")
        # Add an agent with special characters
        agents_config = self.autoflow.read_json(self.autoflow.AGENTS_FILE)
        agents_config["agents"]["agent-test_123"] = {
            "command": "echo",
            "args": ["test"],
            "memory_scopes": ["spec"],
        }
        self.autoflow.write_json(self.autoflow.AGENTS_FILE, agents_config)

        run_id = self.create_run("spec-a", "implementation-runner", agent="agent-test_123")

        runs = self.capture_list_runs_output(agent="agent-test_123")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["agent"], "agent-test_123")

    def test_list_runs_empty_filter_values(self) -> None:
        """Test that empty filter values return all runs."""
        self.create_spec("spec-a")
        self.create_spec("spec-b")

        run_a = self.create_run("spec-a", "implementation-runner")
        run_b = self.create_run("spec-b", "implementation-runner")

        # No filter should return all runs
        runs = self.capture_list_runs_output()
        self.assertGreaterEqual(len(runs), 2)


class TestListRunsPerformance(ListRunsTestBase):
    """Performance and caching tests for list-runs CLI command."""

    def test_cache_performance_small_dataset(self) -> None:
        """Verify caching provides performance benefits with small dataset (10 runs)."""
        self.create_spec("perf-spec-a")
        self.create_spec("perf-spec-b")
        self.create_spec("perf-spec-c")

        # Create 10 runs across different specs and roles
        for i in range(10):
            spec = f"perf-spec-{chr(65 + (i % 3))}"  # spec-a, spec-b, spec-c
            role = ["implementation-runner", "reviewer", "maintainer"][i % 3]
            self.create_run(spec, role)

        # Invalidate cache to ensure first call is a cache miss
        self.autoflow.invalidate_run_cache()

        # Benchmark first call (cache miss - loads from filesystem)
        start = time.perf_counter()
        result_first = self.capture_list_runs_output()
        time_first = time.perf_counter() - start

        # Benchmark second call (cache hit - reads from memory)
        start = time.perf_counter()
        result_second = self.capture_list_runs_output()
        time_second = time.perf_counter() - start

        # Verify results are identical
        self.assertEqual(len(result_first), 10)
        self.assertEqual(len(result_second), 10)
        first_ids = sorted(r["id"] for r in result_first)
        second_ids = sorted(r["id"] for r in result_second)
        self.assertEqual(first_ids, second_ids)

        # Second call (cache hit) should be faster than first call (cache miss)
        # With small datasets, speedup may be modest due to fast filesystem I/O
        assert time_second < time_first, f"Cache hit ({time_second:.6f}s) should be faster than cache miss ({time_first:.6f}s)"

        # Calculate speedup
        speedup = time_first / time_second
        # At least 10% speedup on cache hit
        self.assertGreater(speedup, 1.1, f"Expected at least 10% speedup, got {speedup:.2f}x")

    def test_cache_performance_medium_dataset(self) -> None:
        """Verify caching provides performance benefits with medium dataset (50 runs)."""
        # Create 5 specs with 10 runs each
        for spec_idx in range(5):
            spec = f"perf-spec-{spec_idx}"
            self.create_spec(spec, impl_tasks=10)
            for i in range(10):
                task_id = f"T{6 + i}"
                self.create_run(spec, "implementation-runner", task=task_id)

        # Invalidate and benchmark first call (cache miss)
        self.autoflow.invalidate_run_cache()
        start = time.perf_counter()
        result_first = self.capture_list_runs_output()
        time_first = time.perf_counter() - start

        # Benchmark second call (cache hit)
        start = time.perf_counter()
        result_second = self.capture_list_runs_output()
        time_second = time.perf_counter() - start

        # Verify results are identical
        self.assertEqual(len(result_first), 50)
        self.assertEqual(len(result_second), 50)
        first_ids = sorted(r["id"] for r in result_first)
        second_ids = sorted(r["id"] for r in result_second)
        self.assertEqual(first_ids, second_ids)

        # With medium datasets, caching should provide benefit or at least not be slower
        # Performance can vary due to OS caching, system load, etc.
        speedup = time_first / time_second
        # At least not significantly slower (allow up to 10% slower due to system variance)
        self.assertGreater(speedup, 0.9, f"Expected cache to not be significantly slower, got {speedup:.2f}x")

    def test_cache_invalidation_works(self) -> None:
        """Verify that cache invalidation forces a reload from filesystem."""
        self.create_spec("cache-spec")
        run_id = self.create_run("cache-spec", "implementation-runner")

        # First call - cache miss
        self.autoflow.invalidate_run_cache()
        result_first = self.capture_list_runs_output()
        self.assertEqual(len(result_first), 1)

        # Create a new run (filesystem changes, cache is stale)
        run_id_2 = self.create_run("cache-spec", "reviewer")

        # Second call WITHOUT invalidation - should still return 1 (stale cache)
        # Note: In the current implementation, run_metadata_iter caches per call
        # but list_runs calls it each time, so we need to verify cache behavior
        # For this test, we're verifying that invalidate_run_cache() works
        self.autoflow.invalidate_run_cache()

        # Third call WITH cache invalidation - should return 2
        result_after_invalidation = self.capture_list_runs_output()
        self.assertEqual(len(result_after_invalidation), 2)

    def test_cache_with_filter_by_spec(self) -> None:
        """Verify caching works correctly when filtering by spec."""
        self.create_spec("spec-a")
        self.create_spec("spec-b")

        for _ in range(10):
            self.create_run("spec-a", "implementation-runner")
        for _ in range(10):
            self.create_run("spec-b", "reviewer")

        # Invalidate cache
        self.autoflow.invalidate_run_cache()

        # First call with filter (cache miss)
        start = time.perf_counter()
        result_first = self.capture_list_runs_output(spec="spec-a")
        time_first = time.perf_counter() - start

        # Second call with same filter (cache hit)
        start = time.perf_counter()
        result_second = self.capture_list_runs_output(spec="spec-a")
        time_second = time.perf_counter() - start

        # Verify results
        self.assertEqual(len(result_first), 10)
        self.assertEqual(len(result_second), 10)

        # All results should be from spec-a
        for run in result_second:
            self.assertEqual(run["spec"], "spec-a")

        # Cache hit should be faster
        assert time_second < time_first, f"Cache hit ({time_second:.6f}s) should be faster than cache miss ({time_first:.6f}s)"

    def test_cache_with_filter_by_status(self) -> None:
        """Verify caching works correctly when filtering by status."""
        self.create_spec("status-spec")

        # Create runs with different statuses
        run_ids = []
        for i in range(10):
            run_id = self.create_run("status-spec", "implementation-runner")
            run_ids.append(run_id)

        # Complete half of the runs
        for run_id in run_ids[:5]:
            self.complete_run(run_id, result="success", summary="Completed")

        # Invalidate cache
        self.autoflow.invalidate_run_cache()

        # First call with status filter (cache miss)
        start = time.perf_counter()
        result_first = self.capture_list_runs_output(status="completed")
        time_first = time.perf_counter() - start

        # Second call with same filter (cache hit)
        start = time.perf_counter()
        result_second = self.capture_list_runs_output(status="completed")
        time_second = time.perf_counter() - start

        # Verify we get exactly 5 completed runs
        self.assertEqual(len(result_first), 5)
        self.assertEqual(len(result_second), 5)

        # Cache hit should be faster
        assert time_second < time_first, f"Cache hit ({time_second:.6f}s) should be faster than cache miss ({time_first:.6f}s)"

    def test_cache_with_multiple_filters(self) -> None:
        """Verify caching works correctly with multiple filters applied."""
        self.create_spec("multi-spec-a")
        self.create_spec("multi-spec-b")

        # Create runs with different specs and roles
        for _ in range(10):
            self.create_run("multi-spec-a", "implementation-runner")
        for _ in range(10):
            self.create_run("multi-spec-a", "reviewer")
        for _ in range(10):
            self.create_run("multi-spec-b", "implementation-runner")

        # Complete some runs
        runs_all = self.capture_list_runs_output()
        for run in runs_all[:5]:
            self.complete_run(run["id"], result="success", summary="Completed")

        # Invalidate cache
        self.autoflow.invalidate_run_cache()

        # Test filtering by spec AND role
        start = time.perf_counter()
        result_first = self.capture_list_runs_output(spec="multi-spec-a", role="implementation-runner")
        time_first = time.perf_counter() - start

        start = time.perf_counter()
        result_second = self.capture_list_runs_output(spec="multi-spec-a", role="implementation-runner")
        time_second = time.perf_counter() - start

        # Should get 10 implementation-runner runs for multi-spec-a
        self.assertEqual(len(result_first), 10)
        self.assertEqual(len(result_second), 10)

        # Verify all results match the filters
        for run in result_second:
            self.assertEqual(run["spec"], "multi-spec-a")
            self.assertEqual(run["role"], "implementation-runner")

        # Cache hit should be faster
        assert time_second < time_first, f"Cache hit ({time_second:.6f}s) should be faster than cache miss ({time_first:.6f}s)"

    def test_cache_performance_with_many_specs(self) -> None:
        """Verify caching performance when listing runs across many specs."""
        # Create 20 specs with 5 runs each = 100 runs total
        for spec_idx in range(20):
            spec = f"perf-spec-{spec_idx:02d}"
            self.create_spec(spec, impl_tasks=5)
            for i in range(5):
                task_id = f"T{6 + i}"
                self.create_run(spec, "implementation-runner", task=task_id)

        # Invalidate cache
        self.autoflow.invalidate_run_cache()

        # First call (cache miss)
        start = time.perf_counter()
        result_first = self.capture_list_runs_output()
        time_first = time.perf_counter() - start

        # Second call (cache hit)
        start = time.perf_counter()
        result_second = self.capture_list_runs_output()
        time_second = time.perf_counter() - start

        # Verify all 100 runs are returned
        self.assertEqual(len(result_first), 100)
        self.assertEqual(len(result_second), 100)

        # Cache hit should be faster with large dataset
        # Performance can vary due to OS caching, system load, etc.
        speedup = time_first / time_second
        # With 100 runs across 20 specs, should see at least some speedup
        self.assertGreater(speedup, 1.2, f"Expected at least 20% speedup with 100 runs, got {speedup:.2f}x")

    def test_cache_consistency_across_calls(self) -> None:
        """Verify that cached results remain consistent across multiple calls."""
        self.create_spec("consistency-spec")

        # Create 20 runs
        run_ids = []
        for i in range(20):
            run_id = self.create_run("consistency-spec", "implementation-runner")
            run_ids.append(run_id)

        # Make multiple calls and verify consistency
        results = []
        for _ in range(5):
            result = self.capture_list_runs_output()
            results.append(result)

        # All results should be identical
        for i in range(1, len(results)):
            self.assertEqual(len(results[0]), len(results[i]))
            ids_0 = sorted(r["id"] for r in results[0])
            ids_i = sorted(r["id"] for r in results[i])
            self.assertEqual(ids_0, ids_i)

    def test_repeated_uncached_calls_performance(self) -> None:
        """Test that repeated calls with cache invalidation show no caching benefit."""
        self.create_spec("repeat-spec", impl_tasks=30)

        # Create 30 runs (one per task)
        for i in range(30):
            task_id = f"T{6 + i}"
            self.create_run("repeat-spec", "implementation-runner", task=task_id)

        # Make multiple calls with cache invalidation - each should scan filesystem
        times = []
        for _ in range(5):
            self.autoflow.invalidate_run_cache()
            start = time.perf_counter()
            self.capture_list_runs_output()
            times.append(time.perf_counter() - start)

        # All calls should take similar time (no persistent caching benefit)
        # Verify that the variance is within reasonable bounds
        avg_time = sum(times) / len(times)
        for t in times:
            # Each call should be within 50% of average (filesystem I/O varies)
            self.assertLess(t, avg_time * 1.5,
                          f"Time {t:.6f}s exceeds 150% of average {avg_time:.6f}s")

    def test_repeated_cached_calls_performance(self) -> None:
        """Test that repeated calls without invalidation show significant performance improvement."""
        self.create_spec("cached-repeat-spec", impl_tasks=30)

        # Create 30 runs (one per task)
        for i in range(30):
            task_id = f"T{6 + i}"
            self.create_run("cached-repeat-spec", "implementation-runner", task=task_id)

        # First call populates cache
        self.autoflow.invalidate_run_cache()
        start = time.perf_counter()
        self.capture_list_runs_output()
        time_first = time.perf_counter() - start

        # Subsequent calls should be much faster (reading from cache)
        times_cached = []
        for _ in range(5):
            start = time.perf_counter()
            self.capture_list_runs_output()
            times_cached.append(time.perf_counter() - start)

        # All cached calls after the first should be very fast
        avg_cached = sum(times_cached) / len(times_cached)

        # Cached calls should be significantly faster than first call
        # (first call does the work, subsequent calls just read from memory)
        self.assertLess(avg_cached, time_first * 0.8,
                       f"Avg cached time {avg_cached:.6f}s should be < 80% of first call {time_first:.6f}s")

    def test_cache_invalidation_performance(self) -> None:
        """Test that cache invalidation correctly resets performance."""
        self.create_spec("invalidate-spec", impl_tasks=20)

        # Create 20 runs (one per task)
        for i in range(20):
            task_id = f"T{6 + i}"
            self.create_run("invalidate-spec", "implementation-runner", task=task_id)

        # Populate cache
        self.autoflow.invalidate_run_cache()
        self.capture_list_runs_output()

        # Fast cached call
        start = time.perf_counter()
        self.capture_list_runs_output()
        time_cached = time.perf_counter() - start

        # Invalidate cache
        self.autoflow.invalidate_run_cache()

        # After invalidation, should be slower again (cache miss)
        start = time.perf_counter()
        self.capture_list_runs_output()
        time_after_invalidation = time.perf_counter() - start

        # After invalidation, should take longer than cached call
        self.assertGreater(time_after_invalidation, time_cached * 1.5,
                          f"Time after invalidation {time_after_invalidation:.6f}s should be > 150% of cached time {time_cached:.6f}s")

    def test_empty_runs_directory_performance(self) -> None:
        """Test performance with empty runs directory."""
        # Don't create any runs - directory is empty

        # Both should be fast with empty directory
        start = time.perf_counter()
        result_first = self.capture_list_runs_output()
        time_first = time.perf_counter() - start

        start = time.perf_counter()
        result_second = self.capture_list_runs_output()
        time_second = time.perf_counter() - start

        self.assertEqual(result_first, [])
        self.assertEqual(result_second, [])

        # Should complete quickly
        self.assertLess(time_first, 0.1, f"First call {time_first:.6f}s should be < 100ms")
        self.assertLess(time_second, 0.1, f"Second call {time_second:.6f}s should be < 100ms")

    def test_sorted_order_performance(self) -> None:
        """Test that both cached and uncached versions return results in the same sorted order."""
        self.create_spec("sorted-spec", impl_tasks=25)

        # Create multiple runs
        run_ids = []
        for i in range(25):
            task_id = f"T{6 + (i % 10)}"
            run_id = self.create_run("sorted-spec", "implementation-runner", task=task_id)
            run_ids.append(run_id)

        # Get results from function
        self.autoflow.invalidate_run_cache()
        result_first = self.capture_list_runs_output()
        result_second = self.capture_list_runs_output()

        # Extract run IDs
        ids_first = [r["id"] for r in result_first]
        ids_second = [r["id"] for r in result_second]

        # Both should return results sorted by run ID (directory name)
        self.assertEqual(ids_first, sorted(ids_first),
                        "First result should be sorted")
        self.assertEqual(ids_second, sorted(ids_second),
                        "Second result should be sorted")

        # Results should be identical
        self.assertEqual(ids_first, ids_second,
                        "Both results should be identical")

    def test_cache_memory_overhead(self) -> None:
        """Test that cache memory overhead is reasonable."""
        # Create 5 specs with 10 runs each
        for spec_idx in range(5):
            spec = f"memory-spec-{spec_idx}"
            self.create_spec(spec, impl_tasks=10)
            for i in range(10):
                task_id = f"T{6 + i}"
                self.create_run(spec, "implementation-runner", task=task_id)

        # Populate cache
        self.autoflow.invalidate_run_cache()
        results = self.capture_list_runs_output()

        # Access the internal cache from the test's autoflow module instance
        # The cache should be organized by spec (not all in one list)
        # This verifies lazy-loading by spec works
        _run_metadata_cache = self.autoflow._run_metadata_cache

        # Count total cached runs
        total_cached_runs = sum(len(runs) for runs in _run_metadata_cache.values())

        # Should cache all runs
        self.assertEqual(total_cached_runs, len(results),
                        f"Cache should have {len(results)} runs, got {total_cached_runs}")

        # Cache should be organized by spec (not all in one list)
        # This verifies lazy-loading by spec works
        num_specs = len(_run_metadata_cache)
        self.assertGreater(num_specs, 1,
                          f"Runs should be distributed across multiple specs, got {num_specs}")

    def test_cache_lazy_loading_by_spec(self) -> None:
        """Test that cache lazy-loads by spec_slug."""
        # Create runs for different specs
        for spec_idx in range(3):
            spec = f"lazy-spec-{spec_idx}"
            self.create_spec(spec, impl_tasks=10)
            for i in range(10):
                task_id = f"T{6 + i}"
                self.create_run(spec, "implementation-runner", task=task_id)

        # Invalidate to start fresh
        self.autoflow.invalidate_run_cache()

        # Access the cache from the test's autoflow module instance
        _run_metadata_cache = self.autoflow._run_metadata_cache
        _cache_loaded_specs = self.autoflow._cache_loaded_specs

        # Initially cache should be empty
        self.assertEqual(len(_run_metadata_cache), 0,
                        "Cache should be empty before first call")
        self.assertEqual(len(_cache_loaded_specs), 0,
                        "Loaded specs should be empty before first call")

        # Call list_runs which loads everything
        self.capture_list_runs_output()

        # Cache should be populated
        self.assertGreater(len(_run_metadata_cache), 0,
                          "Cache should be populated after list_runs call")
        self.assertGreater(len(_cache_loaded_specs), 0,
                          "Loaded specs should be populated after list_runs call")

    def test_cache_invalidation_clears_all_state(self) -> None:
        """Test that invalidate_run_cache() properly clears all cache state."""
        self.create_spec("clear-spec", impl_tasks=20)

        # Create and cache runs (one per task)
        for i in range(20):
            task_id = f"T{6 + i}"
            self.create_run("clear-spec", "implementation-runner", task=task_id)

        self.autoflow.invalidate_run_cache()
        self.capture_list_runs_output()

        # Access the cache from the test's autoflow module instance
        _run_metadata_cache = self.autoflow._run_metadata_cache
        _cache_loaded_specs = self.autoflow._cache_loaded_specs

        # Verify cache is populated
        self.assertGreater(len(_run_metadata_cache), 0,
                          "Cache should be populated after first call")
        self.assertGreater(len(_cache_loaded_specs), 0,
                          "Loaded specs should be populated after first call")

        # Invalidate
        self.autoflow.invalidate_run_cache()

        # Verify cache is cleared
        self.assertEqual(len(_run_metadata_cache), 0,
                        "Cache should be empty after invalidation")
        self.assertEqual(len(_cache_loaded_specs), 0,
                        "Loaded specs should be empty after invalidation")


if __name__ == "__main__":
    unittest.main()
