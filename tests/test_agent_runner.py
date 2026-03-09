from __future__ import annotations

import importlib.util
import json
import os
import subprocess
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

    def test_tampered_prompt_md_raises_system_exit(self) -> None:
        """Test that tampered prompt.md file is detected and raises SystemExit."""
        # Import integrity module to compute hash
        from scripts.integrity import hash_file_content

        # Compute the original hash of the prompt file
        original_hash = hash_file_content(str(self.prompt_file))

        # Create run metadata with integrity hash
        run_file = Path(self.temp_dir.name) / "run.json"
        run_file.write_text(
            json.dumps(
                {
                    "resume_from": "run-1",
                    "agent_config": {"command": "claude", "args": []},
                    "integrity": {"prompt.md": original_hash},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Tamper with the prompt file
        self.prompt_file.write_text("MALICIOUS CONTENT", encoding="utf-8")

        # Verify that integrity check fails
        agents_file = Path(self.temp_dir.name) / "agents.json"
        agents_file.write_text(
            json.dumps({"agents": {"test-agent": {"command": "claude", "args": []}}}) + "\n",
            encoding="utf-8",
        )

        argv = [
            "agent_runner.py",
            str(agents_file),
            "test-agent",
            str(self.prompt_file),
            str(run_file),
        ]

        with patch.object(sys, "argv", argv):
            with self.assertRaises(SystemExit) as context:
                self.module.main()

            # Verify the error message mentions integrity check failure
            self.assertIn("integrity check failed", str(context.exception))
            self.assertIn("tampered with", str(context.exception))

    def test_tampered_run_sh_raises_error(self) -> None:
        """Test that tampered run.sh file is detected and raises an error."""
        # Import integrity module to compute hash
        from scripts.integrity import hash_file_content

        # Get the repo root
        repo_root = Path(__file__).resolve().parents[1]

        # Create .autoflow directory and agents.json if it doesn't exist
        autoflow_dir = repo_root / ".autoflow"
        autoflow_dir.mkdir(exist_ok=True)
        agents_file = autoflow_dir / "agents.json"

        # Save original agents.json if it exists
        original_agents = None
        if agents_file.exists():
            original_agents = agents_file.read_text(encoding="utf-8")

        try:
            # Create test agents.json
            agents_file.write_text(
                json.dumps({"agents": {"test-agent": {"command": "echo", "args": ["test"]}}}) + "\n",
                encoding="utf-8",
            )

            # Create a run directory structure
            run_dir = Path(self.temp_dir.name) / "run"
            run_dir.mkdir()

            # Create run.sh file
            run_script = run_dir / "run.sh"
            run_script.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo 'Original content'\n",
                encoding="utf-8",
            )
            run_script.chmod(0o755)

            # Create prompt.md file
            prompt_file = run_dir / "prompt.md"
            prompt_file.write_text("Implement the selected task.", encoding="utf-8")

            # Compute the original hash of run.sh
            original_hash = hash_file_content(str(run_script))

            # Create run metadata with integrity hash
            run_file = run_dir / "run.json"
            run_file.write_text(
                json.dumps(
                    {
                        "resume_from": "run-1",
                        "agent_config": {"command": "echo", "args": ["test"]},
                        "integrity": {"run.sh": original_hash},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            # Tamper with run.sh
            run_script.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo 'MALICIOUS CONTENT'\n",
                encoding="utf-8",
            )

            # Get the path to run-agent.sh
            run_agent_script = repo_root / "scripts" / "run-agent.sh"

            # Call run-agent.sh and verify it exits with error
            result = subprocess.run(
                [
                    str(run_agent_script),
                    "test-agent",
                    str(prompt_file),
                    str(run_file),
                ],
                capture_output=True,
                text=True,
            )

            # Verify the script failed
            self.assertNotEqual(result.returncode, 0)

            # Verify the error message mentions integrity check failure
            self.assertIn("integrity check failed", result.stderr)
            self.assertIn("tampered with", result.stderr)
        finally:
            # Restore original agents.json
            if original_agents is not None:
                agents_file.write_text(original_agents, encoding="utf-8")
            elif agents_file.exists():
                agents_file.unlink()


if __name__ == "__main__":
    unittest.main()
