"""
Unit Tests for Autoflow Phase 4D Functionality

Tests Phase 4D workflow features including fix requests, structured findings,
strategy memory, and task master integration.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

import io
import json
import subprocess
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.autoflow_cli import AgentSpec, AutoflowCLI
from autoflow.core.config import Config


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_root(tmp_path: Path) -> Path:
    """Create a temporary root directory with git repo and config."""
    # Initialize git repo
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)

    # Create config directory
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)

    # Create system config template
    (tmp_path / "config" / "system.example.json").write_text(
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

    # Create BMAD templates directory
    (tmp_path / "templates" / "bmad").mkdir(parents=True, exist_ok=True)
    for role in [
        "spec-writer",
        "task-graph-manager",
        "implementation-runner",
        "reviewer",
        "maintainer",
    ]:
        (tmp_path / "templates" / "bmad" / f"{role}.md").write_text(f"# {role}\n", encoding="utf-8")

    return tmp_path


@pytest.fixture
def cli(temp_root: Path) -> AutoflowCLI:
    """Create an AutoflowCLI instance with temporary root."""
    config = Config()
    state_dir = temp_root / ".autoflow"
    cli_instance = AutoflowCLI(config, root=temp_root, state_dir=state_dir)
    cli_instance.ensure_state()

    # Write default agents config
    cli_instance.write_json(
        cli_instance.agents_file,
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

    return cli_instance


@pytest.fixture
def create_spec_helper(cli: AutoflowCLI):
    """Helper fixture to create a spec."""

    def _create(slug: str = "phase4d", title: str = "Phase 4D", summary: str = "Validation spec"):
        with redirect_stdout(io.StringIO()):
            cli.create_spec(slug, title, summary)

    return _create


@pytest.fixture
def capture_json_output():
    """Helper fixture to capture JSON output from CLI commands."""

    def _capture(fn, args) -> dict[str, Any]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn(args)
        return json.loads(buf.getvalue())

    return _capture


# ============================================================================
# Tests
# ============================================================================


class TestPhase4DFixRequests:
    """Tests for Phase 4D fix request functionality."""

    def test_reviewer_failure_creates_fix_request(
        self, cli: AutoflowCLI, create_spec_helper, capture_json_output
    ) -> None:
        """Test that reviewer failure creates a fix request."""
        create_spec_helper()
        tasks = cli.load_tasks("phase4d")
        task = cli.task_lookup(tasks, "T1")
        task["status"] = "in_review"
        cli.save_tasks("phase4d", tasks, reason="task_status_updated")

        output = io.StringIO()
        with redirect_stdout(output):
            cli.create_run(
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

        result = capture_json_output(
            cli.complete_run,
            SimpleNamespace(
                run=run_id,
                result="needs_changes",
                summary="Reviewer found two issues that require a retry.",
            ),
        )

        assert result["fix_request"].endswith("QA_FIX_REQUEST.md")
        fix_request = cli.spec_files("phase4d")["qa_fix_request"].read_text(encoding="utf-8")
        assert "Reviewer found two issues" in fix_request

    def test_structured_findings_are_written_to_markdown_and_json(
        self, cli: AutoflowCLI, create_spec_helper, capture_json_output
    ) -> None:
        """Test that structured findings are written to both markdown and JSON."""
        create_spec_helper("findings-spec")
        tasks = cli.load_tasks("findings-spec")
        cli.task_lookup(tasks, "T1")["status"] = "in_review"
        cli.save_tasks("findings-spec", tasks, reason="task_status_updated")

        out = io.StringIO()
        with redirect_stdout(out):
            cli.create_run(
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

        capture_json_output(
            cli.complete_run,
            SimpleNamespace(
                run=run_id,
                result="needs_changes",
                summary="Structured findings available.",
                findings_json=json.dumps(findings),
                findings_file="",
            ),
        )

        payload = cli.load_fix_request_data("findings-spec")
        assert payload["finding_count"] == 1
        assert payload["findings"][0]["file"] == "tests/test_phase4d.py"
        assert payload["findings"][0]["severity"] == "high"

        markdown = cli.load_fix_request("findings-spec")
        assert "| F-1 | high | tests | tests/test_phase4d.py | 10 | Missing test coverage |" in markdown


class TestPhase4DPrompts:
    """Tests for Phase 4D prompt building."""

    def test_build_prompt_includes_structured_fix_request_and_respects_memory_scope(
        self, cli: AutoflowCLI, create_spec_helper
    ) -> None:
        """Test that build_prompt includes fix request and respects memory scope."""
        create_spec_helper("prompt-spec")
        cli.append_memory("global", "global memory", title="Global")
        cli.append_memory("spec", "spec memory", spec_slug="prompt-spec", title="Spec")

        cli.write_fix_request(
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
        prompt = cli.build_prompt("prompt-spec", "reviewer", "T1", agent)

        assert '"file": "scripts/continuous_iteration.py"' in prompt
        assert '"suggested_fix": "Return the blocker in dispatch output."' in prompt
        assert "spec memory" in prompt
        assert "global memory" not in prompt


class TestPhase4DStrategyMemory:
    """Tests for Phase 4D strategy memory functionality."""

    def test_complete_run_records_strategy_reflection_and_playbook(
        self, cli: AutoflowCLI, create_spec_helper, capture_json_output
    ) -> None:
        """Test that completing a run records strategy reflection and playbook."""
        create_spec_helper("strategy-spec")

        out = io.StringIO()
        with redirect_stdout(out):
            cli.create_run(
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

        result = capture_json_output(
            cli.complete_run,
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
        summary = cli.strategy_summary("strategy-spec")
        assert summary["recent_reflections"][-1]["result"] == "needs_changes"
        assert any(item["category"] == "tests" for item in summary["playbook"])


class TestPhase4DTaskmaster:
    """Tests for Phase 4D task master integration."""

    def test_taskmaster_export_import_round_trip(
        self, cli: AutoflowCLI, temp_root: Path, create_spec_helper, capture_json_output
    ) -> None:
        """Test task master export and import round trip."""
        create_spec_helper("taskmaster-spec")
        export_path = temp_root / "taskmaster.json"

        with redirect_stdout(io.StringIO()):
            cli.export_taskmaster_cmd(
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

        result = capture_json_output(
            cli.import_taskmaster_cmd,
            SimpleNamespace(spec="taskmaster-spec", input=str(export_path)),
        )

        assert result["task_count"] == 1
        tasks = cli.load_tasks("taskmaster-spec")
        assert tasks["tasks"][0]["id"] == "X1"
        assert tasks["tasks"][0]["owner_role"] == "maintainer"


class TestPhase4DRunResume:
    """Tests for Phase 4D run resume functionality."""

    def test_resume_run_creates_new_attempt_with_resume_from(
        self, cli: AutoflowCLI, create_spec_helper, capture_json_output
    ) -> None:
        """Test that resuming a run creates a new attempt with resume_from."""
        create_spec_helper("resume-spec")

        output = io.StringIO()
        with redirect_stdout(output):
            cli.create_run(
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

        capture_json_output(
            cli.complete_run,
            SimpleNamespace(run=first_run, result="blocked", summary="First attempt blocked."),
        )

        resumed = io.StringIO()
        with redirect_stdout(resumed):
            cli.resume_run(SimpleNamespace(run=first_run))

        second_run = Path(resumed.getvalue().strip()).name
        metadata = cli.read_json(cli.runs_dir / second_run / "run.json")
        assert metadata["resume_from"] == first_run
        assert metadata["attempt_count"] == 2


class TestPhase4DWorkflowState:
    """Tests for Phase 4D workflow state functionality."""

    def test_workflow_state_blocks_implementation_when_review_invalid(
        self, cli: AutoflowCLI, create_spec_helper, capture_json_output
    ) -> None:
        """Test that workflow state blocks implementation when review is invalid."""
        create_spec_helper("gate-spec")
        tasks = cli.load_tasks("gate-spec")
        cli.task_lookup(tasks, "T1")["status"] = "done"
        cli.task_lookup(tasks, "T2")["status"] = "done"
        cli.save_tasks("gate-spec", tasks, reason="task_status_updated")

        state = capture_json_output(cli.workflow_state, SimpleNamespace(spec="gate-spec"))
        assert state["blocking_reason"] == "review_approval_required"
        assert state["recommended_next_action"] is None


class TestPhase4DAgentDiscovery:
    """Tests for Phase 4D agent discovery functionality."""

    def test_discover_agents_includes_acp_registry(
        self, cli: AutoflowCLI, temp_root: Path
    ) -> None:
        """Test that agent discovery includes ACP registry."""
        config = cli.system_config_default()
        config["registry"]["acp_agents"] = [
            {
                "name": "test-acp",
                "transport": {"type": "stdio", "command": "acp-agent", "args": []},
                "capabilities": {"resume": False},
            }
        ]
        cli.write_json(cli.system_config_file, config)

        with (
            patch.object(cli.shutil, "which", side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd == "codex" else None),
            patch.object(cli, "run_cmd", return_value=SimpleNamespace(stdout="resume --model", stderr="", returncode=0)),
        ):
            payload = cli.discover_agents_registry()

        names = [agent["name"] for agent in payload["agents"]]
        assert "codex" in names
        assert "test-acp" in names

    def test_load_agents_applies_model_and_tool_profiles(self, cli: AutoflowCLI) -> None:
        """Test that loading agents applies model and tool profiles."""
        cli.write_json(
            cli.agents_file,
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

        agents = cli.load_agents()
        profiled = agents["profiled-reviewer"]
        assert profiled.model == "claude-sonnet-4-6"
        assert profiled.tools == ["Read", "Bash(git:*)"]
        assert profiled.memory_scopes == ["spec"]

    def test_sync_discovered_agents_materializes_catalog(
        self, cli: AutoflowCLI, temp_root: Path
    ) -> None:
        """Test that syncing discovered agents materializes the catalog."""
        config = cli.system_config_default()
        config["registry"]["acp_agents"] = [
            {
                "name": "test-acp",
                "transport": {"type": "stdio", "command": "acp-agent", "args": []},
                "capabilities": {"resume": False},
            }
        ]
        cli.write_json(cli.system_config_file, config)

        with (
            patch.object(
                cli.shutil,
                "which",
                side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd in {"codex", "claude"} else None,
            ),
            patch.object(
                cli,
                "run_cmd",
                side_effect=[
                    SimpleNamespace(stdout="resume --model", stderr="", returncode=0),
                    SimpleNamespace(stdout="--continue --model", stderr="", returncode=0),
                ],
            ),
        ):
            result = cli.sync_discovered_agents()

        catalog = cli.read_json(cli.agents_file)
        assert "codex" in catalog["agents"]
        assert "claude" in catalog["agents"]
        assert "test-acp" in catalog["agents"]
        assert catalog["agents"]["codex"]["resume"]["subcommand"] == "resume"
        assert result["total_agents"] == 4
