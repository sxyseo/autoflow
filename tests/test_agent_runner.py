from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AgentRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.module = load_module(self.repo_root / "scripts" / "agent_runner.py", "agent_runner_test")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prompt_file = Path(self.temp_dir.name) / "prompt.md"
        self.prompt_file.write_text("Implement the selected task.", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_regular_command_uses_prompt_text(self) -> None:
        command = self.module.build_command(
            {"command": "echo", "args": ["agent"]},
            str(self.prompt_file),
            run_metadata=None,
        )
        self.assertEqual(command, ["echo", "agent", "Implement the selected task."])

    def test_codex_resume_uses_subcommand(self) -> None:
        command = self.module.build_command(
            {
                "command": "codex",
                "args": ["--full-auto"],
                "resume": {"mode": "subcommand", "subcommand": "resume", "args": ["--last"]},
            },
            str(self.prompt_file),
            run_metadata={"resume_from": "run-1"},
        )
        self.assertEqual(
            command,
            ["codex", "--full-auto", "resume", "--last", "Implement the selected task."],
        )

    def test_claude_resume_uses_continue_flag(self) -> None:
        command = self.module.build_command(
            {
                "command": "claude",
                "args": [],
                "resume": {"mode": "args", "args": ["--continue"]},
            },
            str(self.prompt_file),
            run_metadata={"resume_from": "run-2"},
        )
        self.assertEqual(command, ["claude", "--continue", "Implement the selected task."])

    def test_model_and_tools_are_applied(self) -> None:
        command = self.module.build_command(
            {
                "command": "claude",
                "args": [],
                "model": "claude-sonnet-4-6",
                "tools": ["Read", "Bash(git:*)"],
            },
            str(self.prompt_file),
            run_metadata=None,
        )
        self.assertEqual(
            command,
            [
                "claude",
                "--model",
                "claude-sonnet-4-6",
                "--allowedTools",
                "Read,Bash(git:*)",
                "Implement the selected task.",
            ],
        )

    def test_acp_stdio_agent_uses_transport_command(self) -> None:
        command = self.module.build_command(
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "acp-agent",
                    "args": ["--serve"],
                    "prompt_mode": "argv",
                },
            },
            str(self.prompt_file),
            run_metadata=None,
        )
        self.assertEqual(command, ["acp-agent", "--serve", "Implement the selected task."])

    def test_main_uses_resolved_agent_config_from_run_metadata(self) -> None:
        agents_file = Path(self.temp_dir.name) / "agents.json"
        run_file = Path(self.temp_dir.name) / "run.json"
        agents_file.write_text(
            json.dumps({"agents": {"claude-review": {"command": "claude", "args": []}}}) + "\n",
            encoding="utf-8",
        )
        run_file.write_text(
            json.dumps(
                {
                    "resume_from": "run-9",
                    "agent_config": {
                        "command": "claude",
                        "args": [],
                        "model": "claude-sonnet-4-6",
                        "tools": ["Read"],
                        "resume": {"mode": "args", "args": ["--continue"]},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        argv = [
            "agent_runner.py",
            str(agents_file),
            "claude-review",
            str(self.prompt_file),
            str(run_file),
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(self.module.os, "execvp") as execvp,
        ):
            self.module.main()
        execvp.assert_called_once_with(
            "claude",
            [
                "claude",
                "--model",
                "claude-sonnet-4-6",
                "--allowedTools",
                "Read",
                "--continue",
                "Implement the selected task.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
