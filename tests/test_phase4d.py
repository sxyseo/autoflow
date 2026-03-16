"""
Unit Tests for Phase 4D CLI Functionality

Tests the autoflow CLI tool for spec management, reviewer workflows,
fix requests, task orchestration, and agent discovery.

These tests use temporary directories and mock git repositories to
avoid requiring actual project setups or external services.
"""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import importlib.util
import sys

import pytest

from autoflow.autoflow_cli import AgentSpec, AutoflowCLI
from autoflow.core.config import Config


def load_script_module(path: Path, name: str):
    """Helper to load a script module for testing scripts not yet migrated."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    temp_dir = tempfile.TemporaryDirectory()
    yield Path(temp_dir.name)
    temp_dir.cleanup()


@pytest.fixture
def test_repo(temp_workspace: Path):
    """Create a test git repository with required config files."""
    # Initialize git repo
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=temp_workspace,
        check=True,
        capture_output=True,
    )

    # Create config directory and system config
    (temp_workspace / "config").mkdir(parents=True, exist_ok=True)
    (temp_workspace / "config" / "system.example.json").write_text(
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

    # Create BMAD templates directory
    (temp_workspace / "templates" / "bmad").mkdir(parents=True, exist_ok=True)
    for role in [
        "spec-writer",
        "task-graph-manager",
        "implementation-runner",
        "reviewer",
        "maintainer",
    ]:
        (temp_workspace / "templates" / "bmad" / f"{role}.md").write_text(
            f"# {role}\n", encoding="utf-8"
        )

    return temp_workspace


@pytest.fixture
def autoflow_cli(test_repo: Path):
    """Create an AutoflowCLI instance for testing."""
    config = Config()
    cli = AutoflowCLI(config, root=test_repo)
    cli.ensure_state()

    # Write agents config
    cli.write_json(
        cli.agents_file,
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

    return cli


class Phase4DTests:
    """Tests for Phase 4D CLI functionality."""

    def create_spec(self, cli: AutoflowCLI, slug: str = "phase4d") -> None:
        """Helper to create a spec."""
        with redirect_stdout(io.StringIO()):
            cli.create_spec(slug, "Phase 4D", "Validation spec")

    def read_tasks(self, cli: AutoflowCLI, slug: str = "phase4d") -> dict:
        """Helper to read tasks."""
        return cli.load_tasks(slug)

    def capture_json_output(self, cli: AutoflowCLI, fn, args) -> dict:
        """Helper to capture JSON output from a function."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn(args)
        return json.loads(buf.getvalue())

    def test_reviewer_failure_creates_fix_request(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that reviewer failure creates a fix request."""
        self.create_spec(autoflow_cli)
        tasks = self.read_tasks(autoflow_cli)
        task = autoflow_cli.task_lookup(tasks, "T1")
        task["status"] = "in_review"
        autoflow_cli.save_tasks("phase4d", tasks, reason="task_status_updated")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
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
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(
                run=run_id,
                result="needs_changes",
                summary="Reviewer found two issues that require a retry.",
            ),
        )
        assert result["fix_request"].endswith("QA_FIX_REQUEST.md")
        fix_request = autoflow_cli.spec_files("phase4d")[
            "qa_fix_request"
        ].read_text(encoding="utf-8")
        assert "Reviewer found two issues" in fix_request

    def test_structured_findings_are_written_to_markdown_and_json(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that structured findings are written to both markdown and JSON."""
        self.create_spec(autoflow_cli, "findings-spec")
        tasks = autoflow_cli.load_tasks("findings-spec")
        autoflow_cli.task_lookup(tasks, "T1")["status"] = "in_review"
        autoflow_cli.save_tasks("findings-spec", tasks, reason="task_status_updated")
        out = io.StringIO()
        with redirect_stdout(out):
            autoflow_cli.create_run(
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
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(
                run=run_id,
                result="needs_changes",
                summary="Structured findings available.",
                findings_json=json.dumps(findings),
                findings_file="",
            ),
        )
        payload = autoflow_cli.load_fix_request_data("findings-spec")
        assert payload["finding_count"] == 1
        assert payload["findings"][0]["file"] == "tests/test_phase4d.py"
        assert payload["findings"][0]["severity"] == "high"
        markdown = autoflow_cli.load_fix_request("findings-spec")
        assert (
            "| F-1 | high | tests | tests/test_phase4d.py | 10 | Missing test coverage |"
            in markdown
        )

    def test_build_prompt_includes_structured_fix_request_and_respects_memory_scope(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that build prompt includes structured fix request and respects memory scope."""
        self.create_spec(autoflow_cli, "prompt-spec")
        autoflow_cli.append_memory("global", "global memory", title="Global")
        autoflow_cli.append_memory(
            "spec", "spec memory", spec_slug="prompt-spec", title="Spec"
        )
        autoflow_cli.write_fix_request(
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
        agent = AgentSpec(
            name="review-agent",
            command="claude",
            args=[],
            model="claude-sonnet-4-6",
            memory_scopes=["spec"],
        )
        prompt = autoflow_cli.build_prompt(
            "prompt-spec", "reviewer", "T1", agent, run_id="run-123"
        )
        assert '"file": "scripts/continuous_iteration.py"' in prompt
        assert '"suggested_fix": "Return the blocker in dispatch output."' in prompt
        assert "spec memory" in prompt
        assert "global memory" not in prompt
        assert ".autoflow/runs/run-123/agent_result.json" in prompt
        assert "## Completion contract" in prompt

    def test_complete_run_records_strategy_reflection_and_playbook(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that complete run records strategy reflection and playbook."""
        self.create_spec(autoflow_cli, "strategy-spec")
        out = io.StringIO()
        with redirect_stdout(out):
            autoflow_cli.create_run(
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
            autoflow_cli,
            autoflow_cli.complete_run,
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
        assert len(result["strategy_memory"]) == 2
        summary = autoflow_cli.strategy_summary("strategy-spec")
        assert summary["recent_reflections"][-1]["result"] == "needs_changes"
        assert any(item["category"] == "tests" for item in summary["playbook"])

    def test_show_and_update_spec_support_readme_compat_flags(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that show and update spec support readme compat flags."""
        self.create_spec(autoflow_cli, "compat-spec")
        result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.update_spec,
            SimpleNamespace(
                slug="compat-spec",
                title="Updated Title",
                summary="Updated summary text.",
                status="ready",
                append="Additional context for the spec.",
            ),
        )
        assert result["metadata"]["title"] == "Updated Title"
        shown = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.show_spec,
            SimpleNamespace(slug="compat-spec"),
        )
        assert shown["metadata"]["status"] == "ready"
        assert "Updated summary text." in shown["spec_markdown"]
        assert "Additional context for the spec." in shown["spec_markdown"]

    def test_init_tasks_update_task_and_reset_task(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test init tasks, update task, and reset task commands."""
        self.create_spec(autoflow_cli, "task-compat")
        init_result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.init_tasks_cmd,
            SimpleNamespace(spec="task-compat", force=False),
        )
        assert init_result["created"] is False
        updated = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.update_task_cmd,
            SimpleNamespace(
                spec="task-compat",
                task="T1",
                status="blocked",
                title="",
                owner_role="",
                append_criterion="",
                note="manual pause",
            ),
        )
        assert updated["status"] == "blocked"
        assert updated["notes"][-1]["note"] == "manual pause"
        reset = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.reset_task_cmd,
            SimpleNamespace(spec="task-compat", task="T1", note="retry from scratch"),
        )
        assert reset["status"] == "todo"
        assert reset["notes"][-1]["note"] == "retry from scratch"

    def test_capture_memory_validate_config_and_test_agent(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test capture memory, validate config, and test agent commands."""
        self.create_spec(autoflow_cli, "memory-spec")
        out = io.StringIO()
        with redirect_stdout(out):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="memory-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(out.getvalue().strip()).name
        self.capture_json_output(
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(run=run_id, result="success", summary="Spec writer completed."),
        )
        captured = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.capture_memory_cmd,
            SimpleNamespace(run=run_id, scopes=None),
        )
        assert captured["run"] == run_id
        memory_text = autoflow_cli.memory_file("spec", "memory-spec").read_text(
            encoding="utf-8"
        )
        assert "Spec writer completed." in memory_text
        validation = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.validate_config_cmd,
            SimpleNamespace(),
        )
        assert validation["valid"] is True
        agent_status = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.test_agent_cmd,
            SimpleNamespace(agent="dummy"),
        )
        assert agent_status["configured"] is True
        assert agent_status["ready"] is True

    def test_cleanup_runs_marks_created_runs_inactive(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that cleanup runs marks created runs inactive."""
        self.create_spec(autoflow_cli, "cleanup-spec")
        out = io.StringIO()
        with redirect_stdout(out):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="cleanup-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        state_before = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.workflow_state,
            SimpleNamespace(spec="cleanup-spec"),
        )
        assert len(state_before["active_runs"]) == 1
        cleanup = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.cleanup_runs_cmd,
            SimpleNamespace(
                spec="cleanup-spec",
                reason="manual_cleanup",
                target_status="abandoned",
                task_status="",
                include_status=["created", "running"],
            ),
        )
        assert len(cleanup["cleaned_runs"]) == 1
        assert cleanup["task_updates"][0]["status"] == "todo"
        state_after = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.workflow_state,
            SimpleNamespace(spec="cleanup-spec"),
        )
        assert state_after["active_runs"] == []
        tasks = autoflow_cli.load_tasks("cleanup-spec")
        assert autoflow_cli.task_lookup(tasks, "T1")["status"] == "todo"

    def test_add_planner_note_accepts_note_flag(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that add planner note accepts note flag."""
        self.create_spec(autoflow_cli, "note-spec")
        with redirect_stdout(io.StringIO()):
            autoflow_cli.add_planner_note_cmd(
                SimpleNamespace(
                    spec="note-spec",
                    title="",
                    content="",
                    note="Remember to validate the retry gate.",
                    category="strategy",
                    scope="spec",
                )
            )
        summary = autoflow_cli.strategy_summary("note-spec")
        assert summary["planner_notes"][-1]["content"] == "Remember to validate the retry gate."

    def test_resolve_root_path_remaps_foreign_autoflow_paths_into_current_root(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that resolve root path remaps foreign autoflow paths into current root."""
        foreign = Path("/tmp/other-repo/.autoflow/memory/specs/example.md")
        resolved = autoflow_cli.resolve_root_path(foreign)
        assert resolved == autoflow_cli.state_dir / "memory" / "specs" / "example.md"

    def test_taskmaster_export_import_round_trip(
        self, autoflow_cli: AutoflowCLI, test_repo: Path
    ) -> None:
        """Test taskmaster export import round trip."""
        self.create_spec(autoflow_cli, "taskmaster-spec")
        export_path = test_repo / "taskmaster.json"
        with redirect_stdout(io.StringIO()):
            autoflow_cli.export_taskmaster_cmd(
                SimpleNamespace(spec="taskmaster-spec", output=str(export_path))
            )
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        assert exported["tasks"][0]["id"] == "T1"
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
            autoflow_cli,
            autoflow_cli.import_taskmaster_cmd,
            SimpleNamespace(spec="taskmaster-spec", input=str(export_path)),
        )
        assert result["task_count"] == 1
        tasks = autoflow_cli.load_tasks("taskmaster-spec")
        assert tasks["tasks"][0]["id"] == "X1"
        assert tasks["tasks"][0]["owner_role"] == "maintainer"

    def test_resume_run_creates_new_attempt_with_resume_from(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that resume run creates new attempt with resume from."""
        self.create_spec(autoflow_cli, "resume-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
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
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(
                run=first_run, result="blocked", summary="First attempt blocked."
            ),
        )
        resumed = io.StringIO()
        with redirect_stdout(resumed):
            autoflow_cli.resume_run(SimpleNamespace(run=first_run))
        second_run = Path(resumed.getvalue().strip()).name
        metadata = autoflow_cli.read_json(
            autoflow_cli.runs_dir / second_run / "run.json"
        )
        assert metadata["resume_from"] == first_run
        assert metadata["attempt_count"] == 2

    def test_heartbeat_run_updates_session_and_status(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that heartbeat run updates session and status."""
        self.create_spec(autoflow_cli, "lease-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="lease-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.heartbeat_run_cmd,
            SimpleNamespace(
                run=run_id,
                status="running",
                session="autoflow-lease-test",
                exit_code=None,
            ),
        )
        metadata = autoflow_cli.load_run_metadata(run_id)
        assert result["status"] == "running"
        assert metadata["status"] == "running"
        assert metadata["tmux_session"] == "autoflow-lease-test"
        assert "heartbeat_at" in metadata

    def test_sweep_runs_marks_stale_and_requeues_task(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that sweep runs marks stale and requeues task."""
        self.create_spec(autoflow_cli, "stale-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="stale-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        metadata = autoflow_cli.load_run_metadata(run_id)
        metadata["status"] = "running"
        metadata["heartbeat_at"] = "20200101T000000Z"
        metadata["tmux_session"] = ""
        autoflow_cli.write_run_metadata(run_id, metadata)
        result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.sweep_runs_cmd,
            SimpleNamespace(
                spec="stale-spec",
                stale_after=60,
                target_status="stale",
                task_status="",
                include_status=["created", "running"],
                auto_recover=False,
                dispatch_recovery=False,
            ),
        )
        assert result["marked_stale"][0]["run"] == run_id
        metadata = autoflow_cli.load_run_metadata(run_id)
        assert metadata["status"] == "stale"
        tasks = autoflow_cli.load_tasks("stale-spec")
        task = autoflow_cli.task_lookup(tasks, "T1")
        assert task["status"] == "todo"

    def test_recover_run_creates_retry_and_marks_old_run(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that recover run creates retry and marks old run."""
        self.create_spec(autoflow_cli, "recover-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="recover-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        metadata = autoflow_cli.load_run_metadata(run_id)
        metadata["status"] = "stale"
        autoflow_cli.write_run_metadata(run_id, metadata)
        result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.recover_run_cmd,
            SimpleNamespace(run=run_id, reason="stale:heartbeat_expired", dispatch=False),
        )
        old_metadata = autoflow_cli.load_run_metadata(run_id)
        new_metadata = autoflow_cli.load_run_metadata(result["new_run"])
        assert old_metadata["status"] == "recovered"
        assert new_metadata["resume_from"] == run_id
        assert new_metadata["recovery_reason"] == "stale:heartbeat_expired"

    def test_finalize_run_uses_agent_result_artifact(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that finalize run uses agent result artifact."""
        self.create_spec(autoflow_cli, "finalize-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="finalize-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        result_file = autoflow_cli.runs_dir / run_id / "agent_result.json"
        result_file.write_text(
            json.dumps(
                {
                    "result": "success",
                    "summary": "Agent finished the slice and recorded the result.",
                    "findings": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.finalize_run_cmd,
            SimpleNamespace(run=run_id, exit_code=0, result_file=str(result_file)),
        )
        metadata = autoflow_cli.load_run_metadata(run_id)
        tasks = autoflow_cli.load_tasks("finalize-spec")
        task = autoflow_cli.task_lookup(tasks, "T1")
        assert result["result_source"] == "agent_result"
        assert metadata["status"] == "completed"
        assert metadata["result"] == "success"
        assert task["status"] == "in_review"

    def test_finalize_run_without_result_file_marks_failed(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that finalize run without result file marks failed."""
        self.create_spec(autoflow_cli, "finalize-fallback")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="finalize-fallback",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.finalize_run_cmd,
            SimpleNamespace(run=run_id, exit_code=0, result_file=""),
        )
        metadata = autoflow_cli.load_run_metadata(run_id)
        tasks = autoflow_cli.load_tasks("finalize-fallback")
        task = autoflow_cli.task_lookup(tasks, "T1")
        assert result["result_source"] == "fallback"
        assert metadata["status"] == "completed"
        assert metadata["result"] == "failed"
        assert task["status"] == "blocked"
        assert "did not write agent_result.json" in (
            autoflow_cli.runs_dir / run_id / "summary.md"
        ).read_text(encoding="utf-8")

    def test_bounded_qa_loop_progresses_from_fix_request_to_done(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that bounded QA loop progresses from fix request to done."""
        self.create_spec(autoflow_cli, "qa-loop-spec")
        tasks = autoflow_cli.load_tasks("qa-loop-spec")
        autoflow_cli.task_lookup(tasks, "T1")["status"] = "done"
        autoflow_cli.task_lookup(tasks, "T2")["status"] = "done"
        autoflow_cli.save_tasks("qa-loop-spec", tasks, reason="task_status_updated")
        self.capture_json_output(
            autoflow_cli,
            autoflow_cli.approve_spec,
            SimpleNamespace(spec="qa-loop-spec", approved_by="tester"),
        )

        impl_out = io.StringIO()
        with redirect_stdout(impl_out):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="qa-loop-spec",
                    role="implementation-runner",
                    agent="dummy",
                    task="T3",
                    branch="",
                    resume_from=None,
                )
            )
        impl_run = Path(impl_out.getvalue().strip()).name
        self.capture_json_output(
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(
                run=impl_run, result="success", summary="Initial implementation slice done."
            ),
        )
        state = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.workflow_state,
            SimpleNamespace(spec="qa-loop-spec"),
        )
        assert state["recommended_next_action"]["owner_role"] == "reviewer"
        assert state["recommended_next_action"]["id"] == "T3"

        review_out = io.StringIO()
        with redirect_stdout(review_out):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="qa-loop-spec",
                    role="reviewer",
                    agent="dummy",
                    task="T3",
                    branch="",
                    resume_from=None,
                )
            )
        review_run = Path(review_out.getvalue().strip()).name
        self.capture_json_output(
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(
                run=review_run,
                result="needs_changes",
                summary="Please tighten the implementation and add follow-up checks.",
            ),
        )
        state = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.workflow_state,
            SimpleNamespace(spec="qa-loop-spec"),
        )
        assert state["fix_request_present"] is True
        assert state["recommended_next_action"]["owner_role"] == "implementation-runner"
        assert state["recommended_next_action"]["id"] == "T3"

        retry_out = io.StringIO()
        with redirect_stdout(retry_out):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="qa-loop-spec",
                    role="implementation-runner",
                    agent="dummy",
                    task="T3",
                    branch="",
                    resume_from=None,
                )
            )
        retry_run = Path(retry_out.getvalue().strip()).name
        self.capture_json_output(
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(run=retry_run, result="success", summary="Applied reviewer fixes."),
        )
        state = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.workflow_state,
            SimpleNamespace(spec="qa-loop-spec"),
        )
        assert state["recommended_next_action"]["owner_role"] == "reviewer"

        final_review_out = io.StringIO()
        with redirect_stdout(final_review_out):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="qa-loop-spec",
                    role="reviewer",
                    agent="dummy",
                    task="T3",
                    branch="",
                    resume_from=None,
                )
            )
        final_review_run = Path(final_review_out.getvalue().strip()).name
        self.capture_json_output(
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(run=final_review_run, result="success", summary="Review passed."),
        )
        tasks = autoflow_cli.load_tasks("qa-loop-spec")
        task = autoflow_cli.task_lookup(tasks, "T3")
        assert task["status"] == "done"
        assert autoflow_cli.load_fix_request("qa-loop-spec") is False

    def test_workflow_state_blocks_implementation_when_review_invalid(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that workflow state blocks implementation when review invalid."""
        self.create_spec(autoflow_cli, "gate-spec")
        tasks = autoflow_cli.load_tasks("gate-spec")
        autoflow_cli.task_lookup(tasks, "T1")["status"] = "done"
        autoflow_cli.task_lookup(tasks, "T2")["status"] = "done"
        autoflow_cli.save_tasks("gate-spec", tasks, reason="task_status_updated")
        state = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.workflow_state,
            SimpleNamespace(spec="gate-spec"),
        )
        assert state["blocking_reason"] == "review_approval_required"
        assert state["recommended_next_action"] is None

    def test_cancel_run_updates_run_and_task_status(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that cancel run updates run and task status."""
        self.create_spec(autoflow_cli, "cancel-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="cancel-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.cancel_run,
            SimpleNamespace(run=run_id, reason=""),
        )
        assert result["run"] == run_id
        assert result["task_status"] == "todo"
        run_metadata = autoflow_cli.read_json(
            autoflow_cli.runs_dir / run_id / "run.json"
        )
        assert run_metadata["status"] == "cancelled"
        assert "cancelled_at" in run_metadata
        tasks = autoflow_cli.load_tasks("cancel-spec")
        task = autoflow_cli.task_lookup(tasks, "T1")
        assert task["status"] == "todo"

    def test_cancel_run_records_event_and_summary(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that cancel run records event and summary."""
        self.create_spec(autoflow_cli, "event-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="event-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        self.capture_json_output(
            autoflow_cli,
            autoflow_cli.cancel_run,
            SimpleNamespace(run=run_id, reason="Test cancellation"),
        )
        events = autoflow_cli.load_events("event-spec", limit=10)
        cancelled_event = next((e for e in events if e.get("type") == "run.cancelled"), None)
        assert cancelled_event is not None
        assert cancelled_event["payload"]["run"] == run_id
        assert cancelled_event["payload"]["task"] == "T1"
        summary_path = autoflow_cli.runs_dir / run_id / "summary.md"
        assert summary_path.exists()
        summary_content = summary_path.read_text(encoding="utf-8")
        assert "Test cancellation" in summary_content

    def test_cancel_run_with_reason(self, autoflow_cli: AutoflowCLI) -> None:
        """Test cancel run with reason."""
        self.create_spec(autoflow_cli, "reason-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="reason-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        reason = "Agent process crashed unexpectedly"
        result = self.capture_json_output(
            autoflow_cli,
            autoflow_cli.cancel_run,
            SimpleNamespace(run=run_id, reason=reason),
        )
        assert result["reason"] == reason
        tasks = autoflow_cli.load_tasks("reason-spec")
        task = autoflow_cli.task_lookup(tasks, "T1")
        assert len(task["notes"]) >= 1
        cancellation_note = next((n for n in task["notes"] if n["note"] == reason), None)
        assert cancellation_note is not None
        assert "at" in cancellation_note
        summary_path = autoflow_cli.runs_dir / run_id / "summary.md"
        summary_content = summary_path.read_text(encoding="utf-8")
        assert reason in summary_content

    def test_cancel_run_fails_on_completed_run(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that cancel run fails on completed run."""
        self.create_spec(autoflow_cli, "completed-spec")
        output = io.StringIO()
        with redirect_stdout(output):
            autoflow_cli.create_run(
                SimpleNamespace(
                    spec="completed-spec",
                    role="spec-writer",
                    agent="dummy",
                    task="T1",
                    branch="",
                    resume_from=None,
                )
            )
        run_id = Path(output.getvalue().strip()).name
        self.capture_json_output(
            autoflow_cli,
            autoflow_cli.complete_run,
            SimpleNamespace(run=run_id, result="success", summary="Work completed."),
        )
        with pytest.raises(SystemExit) as exc_info:
            autoflow_cli.cancel_run(SimpleNamespace(run=run_id, reason=""))
        assert "cannot cancel run with status completed" in str(exc_info.value)

    def test_cancel_run_fails_on_unknown_run(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that cancel run fails on unknown run."""
        self.create_spec(autoflow_cli, "unknown-spec")
        with pytest.raises(SystemExit) as exc_info:
            autoflow_cli.cancel_run(SimpleNamespace(run="nonexistent-run-id", reason=""))
        assert "unknown run: nonexistent-run-id" in str(exc_info.value)

    def test_discover_agents_includes_acp_registry(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that discover agents includes ACP registry."""
        config = autoflow_cli.system_config_default()
        config["registry"]["acp_agents"] = [
            {
                "name": "test-acp",
                "transport": {"type": "stdio", "command": "acp-agent", "args": []},
                "capabilities": {"resume": False},
            }
        ]
        autoflow_cli.write_json(autoflow_cli.system_config_file, config)
        with (
            patch.object(
                autoflow_cli.shutil,
                "which",
                side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd == "codex" else None,
            ),
            patch.object(
                autoflow_cli,
                "run_cmd",
                return_value=SimpleNamespace(
                    stdout="resume --model", stderr="", returncode=0
                ),
            ),
        ):
            payload = autoflow_cli.discover_agents_registry()
        names = [agent["name"] for agent in payload["agents"]]
        assert "codex" in names
        assert "test-acp" in names

    def test_load_agents_applies_model_and_tool_profiles(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that load agents applies model and tool profiles."""
        autoflow_cli.write_json(
            autoflow_cli.agents_file,
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
        agents = autoflow_cli.load_agents()
        profiled = agents["profiled-reviewer"]
        assert profiled.model == "claude-sonnet-4-6"
        assert profiled.tools == ["Read", "Bash(git:*)"]
        assert profiled.memory_scopes == ["spec"]

    def test_sync_discovered_agents_materializes_catalog(
        self, autoflow_cli: AutoflowCLI
    ) -> None:
        """Test that sync discovered agents materializes catalog."""
        config = autoflow_cli.system_config_default()
        config["registry"]["acp_agents"] = [
            {
                "name": "test-acp",
                "transport": {"type": "stdio", "command": "acp-agent", "args": []},
                "capabilities": {"resume": False},
            }
        ]
        autoflow_cli.write_json(autoflow_cli.system_config_file, config)
        with (
            patch.object(
                autoflow_cli.shutil,
                "which",
                side_effect=lambda cmd: (
                    f"/usr/bin/{cmd}" if cmd in {"codex", "claude"} else None
                ),
            ),
            patch.object(
                autoflow_cli,
                "run_cmd",
                side_effect=[
                    SimpleNamespace(stdout="resume --model", stderr="", returncode=0),
                    SimpleNamespace(
                        stdout="--continue --model", stderr="", returncode=0
                    ),
                ],
            ),
        ):
            result = autoflow_cli.sync_discovered_agents()
        catalog = autoflow_cli.read_json(autoflow_cli.agents_file)
        assert "codex" in catalog["agents"]
        assert "claude" in catalog["agents"]
        assert "test-acp" in catalog["agents"]
        assert catalog["agents"]["codex"]["resume"]["subcommand"] == "resume"
        assert result["total_agents"] == 4

    def test_dispatch_gate_stops_after_retry_limit(
        self, autoflow_cli: AutoflowCLI, test_repo: Path
    ) -> None:
        """Test that dispatch gate stops after retry limit."""
        continuous = load_script_module(
            test_repo / "scripts" / "continuous_iteration.py", "continuous_test"
        )
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
            {
                "id": "T3",
                "status": "needs_changes",
                "owner_role": "implementation-runner",
            },
        )
        assert gate["reason"] == "max_automatic_attempts_reached"

    def test_continuous_iteration_can_fallback_to_discovered_agent(
        self, autoflow_cli: AutoflowCLI, test_repo: Path
    ) -> None:
        """Test that continuous iteration can fallback to discovered agent."""
        continuous = load_script_module(
            test_repo / "scripts" / "continuous_iteration.py",
            "continuous_fallback_test",
        )
        catalog = {"codex": {"command": "codex"}, "claude": {"command": "claude"}}
        agent, source = continuous.select_agent_for_role(
            {"role_agents": {"reviewer": "claude-review"}},
            "reviewer",
            catalog,
        )
        assert agent == "claude"
        assert source == "fallback"
