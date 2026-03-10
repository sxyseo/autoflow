"""
Unit Tests for Phase 4D CLI Functionality

Tests the autoflow CLI tool for spec management, reviewer workflows,
fix requests, task orchestration, and agent discovery.

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


class Phase4DTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
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
                    "models": {"profiles": {"implementation": "gpt-5-codex", "review": "claude-sonnet-4-6"}},
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
        self.autoflow = load_module(self.repo_root / "scripts" / "autoflow.py", "autoflow_test")
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

    def test_structured_findings_are_written_to_markdown_and_json(self) -> None:
        self.create_spec("findings-spec")
        tasks = self.autoflow.load_tasks("findings-spec")
        self.autoflow.task_lookup(tasks, "T1")["status"] = "in_review"
        self.autoflow.save_tasks("findings-spec", tasks, reason="task_status_updated")
        out = io.StringIO()
        with redirect_stdout(out):
            self.autoflow.create_run(
                SimpleNamespace(
                    spec="findings-spec",
                    role="reviewer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(out.getvalue().strip()).name
        findings = [
            {
                "id": "F-1",
                "title": "Missing test coverage",
                "body": "Add a regression test for the retry gate.",
                "file": "tests/test_phase4d.py",
                "line": 10,
                "severity": "high",
                "category": "tests",
            }
        ]
        self.capture_json_output(
            self.autoflow.complete_run,
            SimpleNamespace(
                run=run_id,
                result="needs_changes",
                summary="Structured findings available.",
                findings_json=json.dumps(findings),
                findings_file="",
            ),
        )
        payload = self.autoflow.load_fix_request_data("findings-spec")
        self.assertEqual(payload["finding_count"], 1)
        self.assertEqual(payload["findings"][0]["file"], "tests/test_phase4d.py")
        self.assertEqual(payload["findings"][0]["severity"], "high")
        markdown = self.autoflow.load_fix_request("findings-spec")
        self.assertIn("| F-1 | high | tests | tests/test_phase4d.py | 10 | Missing test coverage |", markdown)

    def test_build_prompt_includes_structured_fix_request_and_respects_memory_scope(self) -> None:
        self.create_spec("prompt-spec")
        self.autoflow.append_memory("global", "global memory", title="Global")
        self.autoflow.append_memory("spec", "spec memory", spec_slug="prompt-spec", title="Spec")
        self.autoflow.write_fix_request(
            "prompt-spec",
            "T1",
            "Reviewer requested changes.",
            "needs_changes",
            findings=[
                {
                    "id": "F-2",
                    "title": "Broken retry flow",
                    "body": "Retry gate does not surface the blocker clearly.",
                    "file": "scripts/continuous_iteration.py",
                    "line": 42,
                    "severity": "medium",
                    "category": "workflow",
                    "suggested_fix": "Return the blocker in dispatch output.",
                }
            ],
        )
        agent = self.autoflow.AgentSpec(
            name="review-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec"],
        )
        prompt = self.autoflow.build_prompt("prompt-spec", "reviewer", "T1", agent)
        self.assertIn('"file": "scripts/continuous_iteration.py"', prompt)
        self.assertIn('"suggested_fix": "Return the blocker in dispatch output."', prompt)
        self.assertIn("spec memory", prompt)
        self.assertNotIn("global memory", prompt)

    def test_complete_run_records_strategy_reflection_and_playbook(self) -> None:
        self.create_spec("strategy-spec")
        out = io.StringIO()
        with redirect_stdout(out):
            self.autoflow.create_run(
                SimpleNamespace(
                    spec="strategy-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(out.getvalue().strip()).name
        result = self.capture_json_output(
            self.autoflow.complete_run,
            SimpleNamespace(
                run=run_id,
                result="needs_changes",
                summary="Planner needs better tests.",
                findings_json=json.dumps(
                    [
                        {
                            "title": "Missing tests",
                            "body": "Add test coverage before retrying.",
                            "category": "tests",
                            "severity": "high",
                            "file": "tests/test_phase4d.py",
                            "line": 1,
                        }
                    ]
                ),
                findings_file="",
            ),
        )
        self.assertEqual(len(result["strategy_memory"]), 2)
        summary = self.autoflow.strategy_summary("strategy-spec")
        self.assertEqual(summary["recent_reflections"][-1]["result"], "needs_changes")
        self.assertTrue(any(item["category"] == "tests" for item in summary["playbook"]))

    def test_taskmaster_export_import_round_trip(self) -> None:
        self.create_spec("taskmaster-spec")
        export_path = self.root / "taskmaster.json"
        with redirect_stdout(io.StringIO()):
            self.autoflow.export_taskmaster_cmd(
                SimpleNamespace(spec="taskmaster-spec", output=str(export_path))
            )
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(exported["tasks"][0]["id"], "T1")
        imported = {
            "tasks": [
                {
                    "id": "X1",
                    "title": "Imported task",
                    "status": "todo",
                    "dependencies": [],
                    "role": "maintainer",
                    "acceptanceCriteria": ["Imported criteria"],
                }
            ]
        }
        export_path.write_text(json.dumps(imported) + "\n", encoding="utf-8")
        result = self.capture_json_output(
            self.autoflow.import_taskmaster_cmd,
            SimpleNamespace(spec="taskmaster-spec", input=str(export_path)),
        )
        self.assertEqual(result["task_count"], 1)
        tasks = self.autoflow.load_tasks("taskmaster-spec")
        self.assertEqual(tasks["tasks"][0]["id"], "X1")
        self.assertEqual(tasks["tasks"][0]["owner_role"], "maintainer")

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

    def test_continuous_iteration_can_fallback_to_discovered_agent(self) -> None:
        continuous = load_module(self.repo_root / "scripts" / "continuous_iteration.py", "continuous_fallback_test")
        catalog = {"codex": {"command": "codex"}, "claude": {"command": "claude"}}
        agent, source = continuous.select_agent_for_role(
            {"role_agents": {"reviewer": "claude-review"}},
            "reviewer",
            catalog,
        )
        self.assertEqual(agent, "claude")
        self.assertEqual(source, "fallback")

    def test_discover_agents_includes_acp_registry(self) -> None:
        config = self.autoflow.system_config_default()
        config["registry"]["acp_agents"] = [
            {
                "name": "test-acp",
                "transport": {"type": "stdio", "command": "acp-agent", "args": []},
                "capabilities": {"resume": False},
            }
        ]
        self.autoflow.write_json(self.autoflow.SYSTEM_CONFIG_FILE, config)
        with (
            patch.object(self.autoflow.shutil, "which", side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd == "codex" else None),
            patch.object(self.autoflow, "run_cmd", return_value=SimpleNamespace(stdout="resume --model", stderr="", returncode=0)),
        ):
            payload = self.autoflow.discover_agents_registry()
        names = [agent["name"] for agent in payload["agents"]]
        self.assertIn("codex", names)
        self.assertIn("test-acp", names)

    def test_load_agents_applies_model_and_tool_profiles(self) -> None:
        self.autoflow.write_json(
            self.autoflow.AGENTS_FILE,
            {
                "agents": {
                    "profiled-reviewer": {
                        "command": "claude",
                        "args": [],
                        "model_profile": "review",
                        "tool_profile": "claude-review",
                    }
                }
            },
        )
        agents = self.autoflow.load_agents()
        profiled = agents["profiled-reviewer"]
        self.assertEqual(profiled.model, "claude-sonnet-4-6")
        self.assertEqual(profiled.tools, ["Read", "Bash(git:*)"])
        self.assertEqual(profiled.memory_scopes, ["spec"])

    def test_sync_discovered_agents_materializes_catalog(self) -> None:
        config = self.autoflow.system_config_default()
        config["registry"]["acp_agents"] = [
            {
                "name": "test-acp",
                "transport": {"type": "stdio", "command": "acp-agent", "args": []},
                "capabilities": {"resume": False},
            }
        ]
        self.autoflow.write_json(self.autoflow.SYSTEM_CONFIG_FILE, config)
        with (
            patch.object(self.autoflow.shutil, "which", side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd in {"codex", "claude"} else None),
            patch.object(
                self.autoflow,
                "run_cmd",
                side_effect=[
                    SimpleNamespace(stdout="resume --model", stderr="", returncode=0),
                    SimpleNamespace(stdout="--continue --model", stderr="", returncode=0),
                ],
            ),
        ):
            result = self.autoflow.sync_discovered_agents()
        catalog = self.autoflow.read_json(self.autoflow.AGENTS_FILE)
        self.assertIn("codex", catalog["agents"])
        self.assertIn("claude", catalog["agents"])
        self.assertIn("test-acp", catalog["agents"])
        self.assertEqual(catalog["agents"]["codex"]["resume"]["subcommand"], "resume")
        self.assertEqual(result["total_agents"], 4)


if __name__ == "__main__":
    unittest.main()
