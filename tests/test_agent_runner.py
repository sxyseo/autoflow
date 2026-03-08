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

    def test_malicious_command_rejected(self) -> None:
        """Test that commands not in the allowlist are rejected."""
        with self.assertRaises(SystemExit) as cm:
            self.module.build_command(
                {"command": "rm", "args": ["-rf", "/"]},
                str(self.prompt_file),
                run_metadata=None,
            )
        self.assertIn("Invalid agent specification", str(cm.exception))

    def test_shell_metacharacters_in_args_rejected(self) -> None:
        """Test that shell metacharacters in arguments are rejected."""
        malicious_args = [
            ["evil", "|", "rm", "-rf", "/"],
            ["evil", "&&", "malware"],
            ["evil", ";", "cat", "/etc/passwd"],
            ["evil", "$HOME"],
            ["evil", "`whoami`"],
            ["evil\n", "malicious"],
            ["evil\r", "malicious"],
            ["evil", "(", "malicious", ")"],
            ["evil", "<", "/etc/passwd"],
            ["evil", ">", "/tmp/pwned"],
            ["evil", "\\x", "malicious"],
        ]
        for args in malicious_args:
            with self.subTest(args=args):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        {"command": "claude", "args": args},
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_dangerous_flags_rejected(self) -> None:
        """Test that dangerous command execution flags are rejected."""
        dangerous_args = [
            ["--exec", "evil()"],
            ["--execute", "malware"],
            ["--eval", "malicious()"],
            ["--evaluate", "pwn()"],
            ["-e", "evil()"],
            ["-c", "malware"],
            ["-x", "pwn()"],
        ]
        for args in dangerous_args:
            with self.subTest(args=args):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        {"command": "claude", "args": args},
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_invalid_command_format_rejected(self) -> None:
        """Test that commands with invalid format are rejected."""
        invalid_commands = [
            {"command": "claude; rm -rf /", "args": []},
            {"command": "claude && malware", "args": []},
            {"command": "claude|evil", "args": []},
            {"command": "", "args": []},
            {"command": "   ", "args": []},
            {"command": "claude evil", "args": []},  # Space in command
        ]
        for spec in invalid_commands:
            with self.subTest(command=spec["command"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_invalid_model_identifier_rejected(self) -> None:
        """Test that model identifiers with invalid characters are rejected."""
        invalid_models = [
            {"command": "claude", "args": [], "model": "claude; rm -rf /"},
            {"command": "claude", "args": [], "model": "claude && malware"},
            {"command": "claude", "args": [], "model": "claude|evil"},
            {"command": "claude", "args": [], "model": "claude model"},  # Space
        ]
        for spec in invalid_models:
            with self.subTest(model=spec["model"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_invalid_tool_names_rejected(self) -> None:
        """Test that tool names with invalid characters are rejected."""
        invalid_tools = [
            {"command": "claude", "args": [], "tools": ["Read; rm -rf /"]},
            {"command": "claude", "args": [], "tools": ["Read&&malware"]},
            {"command": "claude", "args": [], "tools": ["Read|evil"]},
            {"command": "claude", "args": [], "tools": ["Read Write"]},  # Space
            {"command": "claude", "args": [], "tools": ["Read,Bash(evil)"]},  # Comma
        ]
        for spec in invalid_tools:
            with self.subTest(tools=spec["tools"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_malicious_runtime_args_rejected(self) -> None:
        """Test that malicious runtime arguments are rejected."""
        malicious_runtime_args = [
            ["--exec", "evil()"],
            ["|", "rm", "-rf"],
            ["&&", "malware"],
            [";evil"],
        ]
        for runtime_args in malicious_runtime_args:
            with self.subTest(runtime_args=runtime_args):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        {"command": "claude", "args": [], "runtime_args": runtime_args},
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_malicious_resume_args_rejected(self) -> None:
        """Test that malicious resume arguments are rejected."""
        malicious_resume_args = [
            {"mode": "args", "args": ["--exec", "evil()"]},
            {"mode": "args", "args": ["|", "rm", "-rf"]},
            {"mode": "args", "args": ["&&malware"]},
        ]
        for resume in malicious_resume_args:
            with self.subTest(resume=resume):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        {"command": "claude", "args": [], "resume": resume},
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_malicious_acp_transport_command_rejected(self) -> None:
        """Test that malicious ACP transport commands are rejected."""
        malicious_transports = [
            {"command": "placeholder", "protocol": "acp", "transport": {"type": "stdio", "command": "rm -rf /", "args": [], "prompt_mode": "argv"}},
            {"command": "placeholder", "protocol": "acp", "transport": {"type": "stdio", "command": "malware", "args": [], "prompt_mode": "argv"}},
            {"command": "placeholder", "protocol": "acp", "transport": {"type": "stdio", "command": "evil && pwn", "args": [], "prompt_mode": "argv"}},
        ]
        for spec in malicious_transports:
            with self.subTest(transport_command=spec["transport"]["command"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_malicious_acp_transport_args_rejected(self) -> None:
        """Test that malicious ACP transport arguments are rejected."""
        malicious_transport = {
            "command": "placeholder",
            "protocol": "acp",
            "transport": {
                "type": "stdio",
                "command": "acp-agent",
                "args": ["--exec", "evil()"],
                "prompt_mode": "argv"
            },
        }
        with self.assertRaises(SystemExit) as cm:
            self.module.build_command(
                malicious_transport,
                str(self.prompt_file),
                run_metadata=None,
            )
        self.assertIn("Invalid agent specification", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
