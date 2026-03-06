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
    module.AGENTS_FILE = module.STATE_DIR / "agents.json"
    module.BMAD_DIR = root / "templates" / "bmad"


class Phase4DTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
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
        self.autoflow = load_module(self.repo_root / "scripts" / "autoflow.py", "autoflow_test")
        configure_autoflow_module(self.autoflow, self.root)
        self.autoflow.ensure_state()
        self.autoflow.write_json(
            self.autoflow.AGENTS_FILE,
            {
                "agents": {
                    "dummy": {"command": "echo", "args": ["agent"]},
                }
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_spec(self, slug: str = "phase4d") -> None:
        args = SimpleNamespace(slug=slug, title="Phase 4D", summary="Validation spec")
        with redirect_stdout(io.StringIO()):
            self.autoflow.create_spec(args)

    def read_tasks(self, slug: str = "phase4d") -> dict:
        return self.autoflow.load_tasks(slug)

    def capture_json_output(self, fn, args) -> dict:
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn(args)
        return json.loads(buf.getvalue())

    def test_reviewer_failure_creates_fix_request(self) -> None:
        self.create_spec()
        tasks = self.read_tasks()
        task = self.autoflow.task_lookup(tasks, "T1")
        task["status"] = "in_review"
        self.autoflow.save_tasks("phase4d", tasks, reason="task_status_updated")
        output = io.StringIO()
        with redirect_stdout(output):
            self.autoflow.create_run(
                SimpleNamespace(
                    spec="phase4d",
                    role="reviewer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_path = Path(output.getvalue().strip())
        run_id = run_path.name
        result = self.capture_json_output(
            self.autoflow.complete_run,
            SimpleNamespace(
                run=run_id,
                result="needs_changes",
                summary="Reviewer found two issues that require a retry.",
            ),
        )
        self.assertTrue(result["fix_request"].endswith("QA_FIX_REQUEST.md"))
        fix_request = self.autoflow.spec_files("phase4d")["qa_fix_request"].read_text(encoding="utf-8")
        self.assertIn("Reviewer found two issues", fix_request)

    def test_resume_run_creates_new_attempt_with_resume_from(self) -> None:
        self.create_spec("resume-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            self.autoflow.create_run(
                SimpleNamespace(
                    spec="resume-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        first_run = Path(output.getvalue().strip()).name
        self.capture_json_output(
            self.autoflow.complete_run,
            SimpleNamespace(run=first_run, result="blocked", summary="First attempt blocked."),
        )
        resumed = io.StringIO()
        with redirect_stdout(resumed):
            self.autoflow.resume_run(SimpleNamespace(run=first_run))
        second_run = Path(resumed.getvalue().strip()).name
        metadata = self.autoflow.read_json(self.autoflow.RUNS_DIR / second_run / "run.json")
        self.assertEqual(metadata["resume_from"], first_run)
        self.assertEqual(metadata["attempt_count"], 2)

    def test_workflow_state_blocks_implementation_when_review_invalid(self) -> None:
        self.create_spec("gate-spec")
        tasks = self.autoflow.load_tasks("gate-spec")
        self.autoflow.task_lookup(tasks, "T1")["status"] = "done"
        self.autoflow.task_lookup(tasks, "T2")["status"] = "done"
        self.autoflow.save_tasks("gate-spec", tasks, reason="task_status_updated")
        state = self.capture_json_output(self.autoflow.workflow_state, SimpleNamespace(spec="gate-spec"))
        self.assertEqual(state["blocking_reason"], "review_approval_required")
        self.assertIsNone(state["recommended_next_action"])

    def test_dispatch_gate_stops_after_retry_limit(self) -> None:
        continuous = load_module(self.repo_root / "scripts" / "continuous_iteration.py", "continuous_test")
        continuous.task_history = lambda spec, task: [
            {"result": "needs_changes"},
            {"result": "blocked"},
            {"result": "failed"},
        ]
        gate = continuous.dispatch_gate(
            {
                "retry_policy": {
                    "max_automatic_attempts": 3,
                    "require_fix_request_for_retry": True,
                }
            },
            {
                "spec": "gate-spec",
                "active_runs": [],
                "blocking_reason": "",
                "fix_request_present": True,
            },
            {"id": "T3", "status": "needs_changes", "owner_role": "implementation-runner"},
        )
        self.assertEqual(gate["reason"], "max_automatic_attempts_reached")


if __name__ == "__main__":
    unittest.main()
