"""
Tests for search-tasks CLI command.

Tests the search and filtering functionality for tasks across all specs.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from click.testing import CliRunner


class SearchTasksCommandTests(unittest.TestCase):
    """Test cases for the search-tasks CLI command."""

    def setUp(self) -> None:
        """Set up test environment with temporary directory and test data."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # Initialize git repo
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

        # Create state directory structure
        self.state_dir = self.root / ".autoflow"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir = self.state_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        # Create test spec task files
        self._create_test_tasks(self.tasks_dir)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def _create_test_tasks(self, tasks_dir: Path) -> None:
        """Create test task files for different specs."""
        # Spec 1: api-spec
        spec1_tasks = {
            "tasks": [
                {
                    "id": "T1",
                    "title": "Implement REST API endpoints",
                    "status": "todo",
                    "owner_role": "implementation-runner",
                    "dependencies": [],
                    "acceptanceCriteria": ["All endpoints implemented"],
                    "notes": ["Need to add authentication", "Use FastAPI framework"],
                },
                {
                    "id": "T2",
                    "title": "Add API documentation",
                    "status": "in_progress",
                    "owner_role": "spec-writer",
                    "dependencies": ["T1"],
                    "acceptanceCriteria": ["OpenAPI spec complete"],
                    "notes": [{"content": "Use Swagger UI", "priority": "high"}],
                },
                {
                    "id": "T3",
                    "title": "Review API security",
                    "status": "done",
                    "owner_role": "reviewer",
                    "dependencies": ["T1"],
                    "acceptanceCriteria": ["Security audit passed"],
                    "notes": [],
                },
            ]
        }

        # Spec 2: frontend-spec
        spec2_tasks = {
            "tasks": [
                {
                    "id": "F1",
                    "title": "Build React components",
                    "status": "todo",
                    "owner_role": "implementation-runner",
                    "dependencies": [],
                    "acceptanceCriteria": ["Components tested"],
                    "notes": ["Use TypeScript", "Follow design system"],
                },
                {
                    "id": "F2",
                    "title": "Implement state management",
                    "status": "blocked",
                    "owner_role": "implementation-runner",
                    "dependencies": ["F1"],
                    "acceptanceCriteria": ["Redux setup complete"],
                    "notes": ["Waiting for API endpoint specs"],
                },
            ]
        }

        # Spec 3: database-spec
        spec3_tasks = {
            "tasks": [
                {
                    "id": "D1",
                    "title": "Design database schema",
                    "status": "done",
                    "owner_role": "maintainer",
                    "dependencies": [],
                    "acceptanceCriteria": ["Schema approved"],
                    "notes": ["Use PostgreSQL", "Include migration scripts"],
                },
            ]
        }

        # Write task files
        (tasks_dir / "api-spec.json").write_text(json.dumps(spec1_tasks, indent=2) + "\n")
        (tasks_dir / "frontend-spec.json").write_text(json.dumps(spec2_tasks, indent=2) + "\n")
        (tasks_dir / "database-spec.json").write_text(json.dumps(spec3_tasks, indent=2) + "\n")

    def _run_search_tasks(
        self,
        status_filter: str | None = None,
        owner_role: str | None = None,
        text: str | None = None,
        limit: int = 20,
        output_json: bool = False,
    ) -> tuple[int, str]:
        """Run the search-tasks command and return exit code and output."""
        # Import CLI module
        from autoflow.cli import main

        # Build command arguments (json flag comes before subcommand)
        args = []
        if output_json:
            args.append("--json")
        args.append("search-tasks")
        if status_filter:
            args.extend(["--status", status_filter])
        if owner_role:
            args.extend(["--owner-role", owner_role])
        if text:
            args.extend(["--text", text])
        args.extend(["--limit", str(limit)])

        # Set state directory via environment
        env = {"AUTOFLOW_STATE_DIR": str(self.state_dir)}

        # Run command
        result = self.runner.invoke(main, args, env=env, catch_exceptions=False)

        return result.exit_code, result.output

    def test_search_all_tasks(self) -> None:
        """Test searching without filters returns all tasks."""
        exit_code, output = self._run_search_tasks()

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find all 6 tasks
        self.assertIn("Found 6 matching task(s)", output)

        # Should contain tasks from all specs
        self.assertIn("[T1] Implement REST API endpoints", output)
        self.assertIn("[F1] Build React components", output)
        self.assertIn("[D1] Design database schema", output)

    def test_filter_by_status_todo(self) -> None:
        """Test filtering tasks by status='todo'."""
        exit_code, output = self._run_search_tasks(status_filter="todo")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 2 todo tasks
        self.assertIn("Found 2 matching task(s)", output)

        # Should contain todo tasks
        self.assertIn("[T1] Implement REST API endpoints", output)
        self.assertIn("[F1] Build React components", output)

        # Should not contain non-todo tasks
        self.assertNotIn("[T2] Add API documentation", output)  # in_progress
        self.assertNotIn("[T3] Review API security", output)  # done

    def test_filter_by_status_in_progress(self) -> None:
        """Test filtering tasks by status='in_progress'."""
        exit_code, output = self._run_search_tasks(status_filter="in_progress")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 1 in_progress task
        self.assertIn("Found 1 matching task(s)", output)

        # Should contain in_progress task
        self.assertIn("[T2] Add API documentation", output)
        self.assertIn("Status: in_progress", output)

    def test_filter_by_status_done(self) -> None:
        """Test filtering tasks by status='done'."""
        exit_code, output = self._run_search_tasks(status_filter="done")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 2 done tasks
        self.assertIn("Found 2 matching task(s)", output)

        # Should contain done tasks
        self.assertIn("[T3] Review API security", output)
        self.assertIn("[D1] Design database schema", output)

    def test_filter_by_status_blocked(self) -> None:
        """Test filtering tasks by status='blocked'."""
        exit_code, output = self._run_search_tasks(status_filter="blocked")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 1 blocked task
        self.assertIn("Found 1 matching task(s)", output)

        # Should contain blocked task
        self.assertIn("[F2] Implement state management", output)
        self.assertIn("Status: blocked", output)

    def test_filter_by_owner_role_implementation_runner(self) -> None:
        """Test filtering tasks by owner_role='implementation-runner'."""
        exit_code, output = self._run_search_tasks(owner_role="implementation-runner")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 3 tasks
        self.assertIn("Found 3 matching task(s)", output)

        # Should contain implementation-runner tasks
        self.assertIn("[T1] Implement REST API endpoints", output)
        self.assertIn("[F1] Build React components", output)
        self.assertIn("[F2] Implement state management", output)

        # Should not contain other roles
        self.assertNotIn("[T2] Add API documentation", output)  # spec-writer
        self.assertNotIn("[T3] Review API security", output)  # reviewer

    def test_filter_by_owner_role_reviewer(self) -> None:
        """Test filtering tasks by owner_role='reviewer'."""
        exit_code, output = self._run_search_tasks(owner_role="reviewer")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 1 task
        self.assertIn("Found 1 matching task(s)", output)

        # Should contain reviewer task
        self.assertIn("[T3] Review API security", output)
        self.assertIn("Owner: reviewer", output)

    def test_filter_by_text_api(self) -> None:
        """Test text search for 'api' (case-insensitive)."""
        exit_code, output = self._run_search_tasks(text="api")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find tasks with 'api' in title or notes
        # T1, T2, T3 have 'api' in title, F2 has 'API' in notes
        self.assertIn("Found 4 matching task(s)", output)

        # Should contain tasks with 'api' in title
        self.assertIn("[T1] Implement REST API endpoints", output)
        self.assertIn("[T2] Add API documentation", output)
        self.assertIn("[T3] Review API security", output)

        # Should contain task with 'API' in notes
        self.assertIn("[F2] Implement state management", output)

        # Should not contain tasks without 'api'
        self.assertNotIn("[F1] Build React components", output)
        self.assertNotIn("[D1] Design database schema", output)

    def test_filter_by_text_authentication(self) -> None:
        """Test text search for 'authentication' in notes."""
        exit_code, output = self._run_search_tasks(text="authentication")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find tasks with 'authentication' in notes
        self.assertIn("Found 1 matching task(s)", output)

        # Should contain task with authentication in notes
        self.assertIn("[T1] Implement REST API endpoints", output)

    def test_filter_by_text_fastapi(self) -> None:
        """Test text search for 'fastapi' (case-insensitive)."""
        exit_code, output = self._run_search_tasks(text="fastapi")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find tasks with 'fastapi' in notes
        self.assertIn("Found 1 matching task(s)", output)

        # Should contain task with FastAPI in notes
        self.assertIn("[T1] Implement REST API endpoints", output)

    def test_filter_by_text_react(self) -> None:
        """Test text search for 'react'."""
        exit_code, output = self._run_search_tasks(text="react")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find tasks with 'react' in title or notes
        self.assertIn("Found 1 matching task(s)", output)

        # Should contain tasks with 'react'
        self.assertIn("[F1] Build React components", output)

    def test_combined_filters_status_and_owner(self) -> None:
        """Test combining status and owner_role filters (AND logic)."""
        exit_code, output = self._run_search_tasks(
            status_filter="todo", owner_role="implementation-runner"
        )

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 2 tasks matching both filters
        self.assertIn("Found 2 matching task(s)", output)

        # Should contain only tasks that are both todo AND implementation-runner
        self.assertIn("[T1] Implement REST API endpoints", output)
        self.assertIn("[F1] Build React components", output)

        # Should not contain tasks that only match one filter
        self.assertNotIn("[F2] Implement state management", output)  # blocked, not todo
        self.assertNotIn("[T2] Add API documentation", output)  # in_progress, not todo

    def test_combined_filters_status_and_text(self) -> None:
        """Test combining status and text filters (AND logic)."""
        exit_code, output = self._run_search_tasks(status_filter="done", text="api")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 1 task matching both filters
        self.assertIn("Found 1 matching task(s)", output)

        # Should contain only tasks that are both done AND contain 'api'
        self.assertIn("[T3] Review API security", output)

        # Should not contain tasks that only match one filter
        self.assertNotIn("[T1] Implement REST API endpoints", output)  # todo, not done
        self.assertNotIn("[D1] Design database schema", output)  # done but no 'api'

    def test_combined_filters_all_three(self) -> None:
        """Test combining all three filters (AND logic)."""
        exit_code, output = self._run_search_tasks(
            status_filter="todo", owner_role="implementation-runner", text="components"
        )

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 1 task matching all filters
        self.assertIn("Found 1 matching task(s)", output)

        # Should contain only the task that matches all filters
        self.assertIn("[F1] Build React components", output)

    def test_limit_filter(self) -> None:
        """Test limiting the number of results."""
        exit_code, output = self._run_search_tasks(limit=2)

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should show only 2 tasks
        self.assertIn("Showing 2", output)

        # Should indicate total found
        self.assertIn("Found 6 matching task(s)", output)

    def test_limit_with_filters(self) -> None:
        """Test limiting results when filters are applied."""
        exit_code, output = self._run_search_tasks(status_filter="todo", limit=1)

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should show only 1 task
        self.assertIn("Showing 1", output)

        # Should indicate total matching
        self.assertIn("Found 2 matching task(s)", output)

    def test_no_results(self) -> None:
        """Test search with filters that match no tasks."""
        exit_code, output = self._run_search_tasks(
            status_filter="in_progress", owner_role="maintainer"
        )

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find 0 tasks
        self.assertIn("Found 0 matching task(s)", output)

        # Should show no tasks message
        self.assertIn("No tasks found matching the criteria", output)

    def test_json_output_all_tasks(self) -> None:
        """Test JSON output format for all tasks."""
        exit_code, output = self._run_search_tasks(output_json=True)

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Parse JSON output
        result = json.loads(output)

        # Should have correct structure
        self.assertIn("tasks", result)
        self.assertIn("count", result)
        self.assertIn("total_matching", result)
        self.assertIn("filters", result)

        # Should have all 6 tasks
        self.assertEqual(result["count"], 6)
        self.assertEqual(result["total_matching"], 6)

        # Should have spec field added to each task
        for task in result["tasks"]:
            self.assertIn("spec", task)

        # Should contain tasks from all specs
        specs = {task["spec"] for task in result["tasks"]}
        self.assertEqual(specs, {"api-spec", "frontend-spec", "database-spec"})

    def test_json_output_with_filters(self) -> None:
        """Test JSON output with filters applied."""
        exit_code, output = self._run_search_tasks(status_filter="todo", output_json=True)

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Parse JSON output
        result = json.loads(output)

        # Should have 2 todo tasks
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total_matching"], 2)

        # Should have filter info
        self.assertEqual(result["filters"]["status"], "todo")
        self.assertEqual(result["filters"]["owner_role"], None)
        self.assertEqual(result["filters"]["text"], None)

        # All returned tasks should be todo
        for task in result["tasks"]:
            self.assertEqual(task["status"], "todo")

    def test_json_output_with_limit(self) -> None:
        """Test JSON output with limit applied."""
        exit_code, output = self._run_search_tasks(limit=2, output_json=True)

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Parse JSON output
        result = json.loads(output)

        # Should return 2 tasks but indicate 6 total
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total_matching"], 6)

    def test_json_output_no_results(self) -> None:
        """Test JSON output when no tasks match."""
        exit_code, output = self._run_search_tasks(
            status_filter="in_progress", owner_role="maintainer", output_json=True
        )

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Parse JSON output
        result = json.loads(output)

        # Should have 0 tasks
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["total_matching"], 0)
        self.assertEqual(len(result["tasks"]), 0)

    def test_text_search_case_insensitive(self) -> None:
        """Test that text search is case-insensitive."""
        # Search with different cases
        _, output1 = self._run_search_tasks(text="API")
        _, output2 = self._run_search_tasks(text="api")
        _, output3 = self._run_search_tasks(text="Api")

        # All should return the same results (4 tasks with 'api' in title/notes)
        self.assertIn("Found 4 matching task(s)", output1)
        self.assertIn("Found 4 matching task(s)", output2)
        self.assertIn("Found 4 matching task(s)", output3)

    def test_text_search_in_notes_as_strings(self) -> None:
        """Test text search in string notes."""
        exit_code, output = self._run_search_tasks(text="typescript")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find task with "TypeScript" in notes
        self.assertIn("Found 1 matching task(s)", output)
        self.assertIn("[F1] Build React components", output)

    def test_text_search_in_notes_as_dicts(self) -> None:
        """Test text search in dict notes."""
        exit_code, output = self._run_search_tasks(text="swagger")

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Should find task with "Swagger" in dict notes
        self.assertIn("Found 1 matching task(s)", output)
        self.assertIn("[T2] Add API documentation", output)

    def test_tasks_sorted_by_spec_and_id(self) -> None:
        """Test that tasks are sorted by spec and then by task ID."""
        exit_code, output = self._run_search_tasks(output_json=True)

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Parse JSON output
        result = json.loads(output)

        # Extract (spec, id) pairs
        task_ids = [(task["spec"], task["id"]) for task in result["tasks"]]

        # Should be sorted
        self.assertEqual(
            task_ids,
            [
                ("api-spec", "T1"),
                ("api-spec", "T2"),
                ("api-spec", "T3"),
                ("database-spec", "D1"),
                ("frontend-spec", "F1"),
                ("frontend-spec", "F2"),
            ],
        )

    def test_spec_field_added_to_tasks(self) -> None:
        """Test that spec field is correctly added to all tasks."""
        exit_code, output = self._run_search_tasks(output_json=True)

        # Should succeed
        self.assertEqual(exit_code, 0)

        # Parse JSON output
        result = json.loads(output)

        # All tasks should have spec field
        for task in result["tasks"]:
            self.assertIn("spec", task)
            self.assertIn(task["spec"], ["api-spec", "frontend-spec", "database-spec"])

        # Tasks should be in correct specs
        api_tasks = [t for t in result["tasks"] if t["spec"] == "api-spec"]
        self.assertEqual(len(api_tasks), 3)

        frontend_tasks = [t for t in result["tasks"] if t["spec"] == "frontend-spec"]
        self.assertEqual(len(frontend_tasks), 2)

        db_tasks = [t for t in result["tasks"] if t["spec"] == "database-spec"]
        self.assertEqual(len(db_tasks), 1)


if __name__ == "__main__":
    unittest.main()
