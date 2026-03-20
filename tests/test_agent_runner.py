"""
Unit Tests for Agent Runner

Tests the agent_runner module for building commands and executing
different AI agents (Claude, Codex, ACP, etc.) with various configurations.

These tests use dynamic module loading to test the agent_runner script
in isolation, mocking file system and subprocess execution.
"""

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
            {"command": "claude", "args": ["--print"]},
            str(self.prompt_file),
            run_metadata=None,
        )
        self.assertEqual(command, ["claude", "--print", "Implement the selected task."])

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

    def test_claude_resume_uses_resume_flag(self) -> None:
        command = self.module.build_command(
            {
                "command": "claude",
                "args": [],
                "resume": {"mode": "args", "args": ["--resume"]},
            },
            str(self.prompt_file),
            run_metadata={"resume_from": "run-2"},
        )
        self.assertEqual(command, ["claude", "--resume", "Implement the selected task."])

    def test_model_and_tools_are_applied(self) -> None:
        command = self.module.build_command(
            {
                "command": "claude",
                "args": [],
                "model": "claude-sonnet-4-6",
                "tools": ["Read", "Bash", "Write"],
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
                "Read,Bash,Write",
                "Implement the selected task.",
            ],
        )

    def test_acp_stdio_agent_uses_transport_command(self) -> None:
        command = self.module.build_command(
            {
                "command": "claude",
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
        # Create test files in current directory to pass path validation
        import os
        import uuid

        # Use unique names to avoid conflicts
        unique_id = str(uuid.uuid4())[:8]
        agents_file = Path(f"test_agents_{unique_id}.json")
        run_file = Path(f"test_run_{unique_id}.json")
        prompt_file = Path(f"test_prompt_{unique_id}.md")

        try:
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
                            "resume": {"mode": "args", "args": ["--resume"]},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            prompt_file.write_text("Implement the selected task.", encoding="utf-8")
            argv = [
                "agent_runner.py",
                str(agents_file),
                "claude-review",
                str(prompt_file),
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
                    "--resume",
                    "Implement the selected task.",
                ],
            )
        finally:
            # Clean up test files
            if agents_file.exists():
                agents_file.unlink()
            if run_file.exists():
                run_file.unlink()
            if prompt_file.exists():
                prompt_file.unlink()

    def test_malicious_command_rejected(self) -> None:
        """Test that commands not in the allowlist are rejected."""
        with self.assertRaises(SystemExit) as cm:
            self.module.build_command(
                {"command": "rm", "args": ["-rf", "/"]},
                str(self.prompt_file),
                run_metadata=None,
            )
        self.assertIn("Invalid agent specification", str(cm.exception))

    def test_shell_metacharacters_rejected(self) -> None:
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

    def test_acp_transport_validation(self) -> None:
        """Test comprehensive ACP transport validation."""
        # Test valid ACP transport configurations
        valid_transports = [
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "acp-agent",
                    "args": ["--serve"],
                    "prompt_mode": "argv"
                },
            },
            {
                "command": "codex",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "acp-agent",
                    "args": ["--port", "8080", "--verbose"],
                    "prompt_mode": "argv"
                },
            },
        ]
        for spec in valid_transports:
            with self.subTest(transport=spec["transport"]):
                command = self.module.build_command(
                    spec,
                    str(self.prompt_file),
                    run_metadata=None,
                )
                # Should not raise and should return a valid command list
                self.assertIsInstance(command, list)
                self.assertGreater(len(command), 0)

        # Test invalid ACP transport commands
        invalid_transport_commands = [
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "rm -rf /",
                    "args": [],
                    "prompt_mode": "argv"
                },
            },
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "malware",
                    "args": [],
                    "prompt_mode": "argv"
                },
            },
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "evil && pwn",
                    "args": [],
                    "prompt_mode": "argv"
                },
            },
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "",
                    "args": [],
                    "prompt_mode": "argv"
                },
            },
        ]
        for spec in invalid_transport_commands:
            with self.subTest(transport_command=spec["transport"]["command"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

        # Test invalid ACP transport arguments
        invalid_transport_args = [
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "acp-agent",
                    "args": ["--exec", "evil()"],
                    "prompt_mode": "argv"
                },
            },
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "acp-agent",
                    "args": ["|", "rm", "-rf"],
                    "prompt_mode": "argv"
                },
            },
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "acp-agent",
                    "args": ["&&", "malware"],
                    "prompt_mode": "argv"
                },
            },
            {
                "command": "claude",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "acp-agent",
                    "args": [";evil"],
                    "prompt_mode": "argv"
                },
            },
        ]
        for spec in invalid_transport_args:
            with self.subTest(transport_args=spec["transport"]["args"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_path_traversal_prevented(self) -> None:
        """Test that path traversal attacks are prevented."""
        from scripts.agent_validation import validate_path, ValidationError
        import tempfile

        # Test various path traversal attempts (all should be rejected)
        path_traversal_attempts = [
            ("../../../etc/passwd", "/workspace"),
            ("../../sensitive_file.txt", "/workspace"),
            ("../../../../../../../../etc/passwd", "/workspace"),
            ("./../../etc/passwd", "/workspace"),
            ("../sibling_dir/file.txt", "/workspace/allowed"),
            ("/etc/passwd", "/workspace"),  # Absolute path
            ("/tmp/test", "/workspace"),  # Another absolute path
            ("~/../../etc/passwd", "/workspace"),  # With home expansion
            ("./file/../../../etc/passwd", "/workspace"),  # Mixed
            ("/workspace/../etc/passwd", "/workspace"),  # Starts in base but escapes
        ]

        for path, base_dir in path_traversal_attempts:
            with self.subTest(path=path, base_dir=base_dir):
                with self.assertRaises(ValidationError) as cm:
                    validate_path(path, base_dir=base_dir, allow_absolute=False)
                # Verify the error message indicates the security issue
                self.assertTrue(
                    "outside base directory" in str(cm.exception) or
                    "Absolute paths are not allowed" in str(cm.exception) or
                    "directory traversal" in str(cm.exception).lower()
                )

        # Test that valid paths within a temporary directory are accepted
        with tempfile.TemporaryDirectory() as temp_base:
            # Create actual files for testing
            test_file = Path(temp_base) / "file.txt"
            test_file.write_text("test content")

            subdir = Path(temp_base) / "subdir"
            subdir.mkdir()
            test_subdir_file = subdir / "file.txt"
            test_subdir_file.write_text("test content")

            # Test valid paths using actual file paths
            valid_paths = [
                str(test_file),
                str(test_subdir_file),
            ]

            for path in valid_paths:
                with self.subTest(path=path):
                    try:
                        result = validate_path(path, base_dir=temp_base, allow_absolute=True)
                        # Verify the resolved path is within base directory
                        base_path = Path(temp_base).resolve()
                        self.assertTrue(
                            str(result).startswith(str(base_path)),
                            f"Resolved path {result} should start with base {base_path}"
                        )
                    except ValidationError:
                        self.fail(f"Valid path {path} should not raise ValidationError")

    def test_command_chaining_rejected(self) -> None:
        """Test that command chaining attempts are comprehensively rejected."""
        # Test command chaining in command field
        command_chaining_commands = [
            {"command": "claude; rm -rf /", "args": []},
            {"command": "claude && malware", "args": []},
            {"command": "claude||evil", "args": []},
            {"command": "claude|cat /etc/passwd", "args": []},
            {"command": "claude\nmalicious", "args": []},
        ]
        for spec in command_chaining_commands:
            with self.subTest(command=spec["command"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

        # Test command chaining in arguments
        command_chaining_args = [
            {"command": "claude", "args": ["arg1", ";", "rm", "-rf", "/"]},
            {"command": "claude", "args": ["arg1", "&&", "malware"]},
            {"command": "claude", "args": ["arg1", "||", "evil"]},
            {"command": "claude", "args": ["arg1", "|", "cat", "/etc/passwd"]},
            {"command": "claude", "args": ["arg1\n", "malicious"]},
            {"command": "claude", "args": ["arg1\r", "malware"]},
        ]
        for spec in command_chaining_args:
            with self.subTest(args=spec["args"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

        # Test command chaining in model field
        command_chaining_models = [
            {"command": "claude", "args": [], "model": "claude; rm -rf /"},
            {"command": "claude", "args": [], "model": "claude && malware"},
            {"command": "claude", "args": [], "model": "claude||evil"},
            {"command": "claude", "args": [], "model": "claude|pwn"},
        ]
        for spec in command_chaining_models:
            with self.subTest(model=spec["model"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

        # Test command chaining in tools field
        command_chaining_tools = [
            {"command": "claude", "args": [], "tools": ["Read; rm -rf /"]},
            {"command": "claude", "args": [], "tools": ["Read&&malware"]},
            {"command": "claude", "args": [], "tools": ["Read||evil"]},
            {"command": "claude", "args": [], "tools": ["Read|pwn"]},
        ]
        for spec in command_chaining_tools:
            with self.subTest(tools=spec["tools"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

        # Test command chaining in runtime_args
        command_chaining_runtime = [
            {"command": "claude", "args": [], "runtime_args": [";", "rm", "-rf"]},
            {"command": "claude", "args": [], "runtime_args": ["&&", "malware"]},
            {"command": "claude", "args": [], "runtime_args": ["||", "evil"]},
            {"command": "claude", "args": [], "runtime_args": ["|", "pwn"]},
        ]
        for spec in command_chaining_runtime:
            with self.subTest(runtime_args=spec["runtime_args"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

        # Test command chaining in resume args
        command_chaining_resume = [
            {"command": "claude", "args": [], "resume": {"mode": "args", "args": [";", "rm"]}},
            {"command": "claude", "args": [], "resume": {"mode": "args", "args": ["&&malware"]}},
            {"command": "claude", "args": [], "resume": {"mode": "args", "args": ["||evil"]}},
            {"command": "claude", "args": [], "resume": {"mode": "args", "args": ["|pwn"]}},
        ]
        for spec in command_chaining_resume:
            with self.subTest(resume=spec["resume"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

        # Test command chaining in ACP transport command
        command_chaining_transport = [
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {"type": "stdio", "command": "agent; rm -rf /", "args": [], "prompt_mode": "argv"}
            },
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {"type": "stdio", "command": "agent && malware", "args": [], "prompt_mode": "argv"}
            },
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {"type": "stdio", "command": "agent||evil", "args": [], "prompt_mode": "argv"}
            },
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {"type": "stdio", "command": "agent|pwn", "args": [], "prompt_mode": "argv"}
            },
        ]
        for spec in command_chaining_transport:
            with self.subTest(transport=spec["transport"]["command"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

        # Test command chaining in ACP transport args
        command_chaining_transport_args = [
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {"type": "stdio", "command": "agent", "args": [";", "rm"], "prompt_mode": "argv"}
            },
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {"type": "stdio", "command": "agent", "args": ["&&malware"], "prompt_mode": "argv"}
            },
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {"type": "stdio", "command": "agent", "args": ["||evil"], "prompt_mode": "argv"}
            },
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {"type": "stdio", "command": "agent", "args": ["|pwn"], "prompt_mode": "argv"}
            },
        ]
        for spec in command_chaining_transport_args:
            with self.subTest(transport_args=spec["transport"]["args"]):
                with self.assertRaises(SystemExit) as cm:
                    self.module.build_command(
                        spec,
                        str(self.prompt_file),
                        run_metadata=None,
                    )
                self.assertIn("Invalid agent specification", str(cm.exception))

    def test_command_line_path_validation(self) -> None:
        """Test that command-line file paths are validated to prevent arbitrary file reads."""
        from unittest.mock import patch
        import tempfile
        import os

        # Create temporary valid files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid agents directory structure
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            valid_agents_json = agents_dir / "test.json"
            valid_agents_json.write_text('{"agents": {"test": {"command": "claude", "args": []}}}')

            # Create valid prompts directory structure
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            valid_prompt = prompts_dir / "test.md"
            valid_prompt.write_text("test prompt")

            # Create valid runs directory structure
            runs_dir = Path(tmpdir) / "runs"
            runs_dir.mkdir()
            valid_run_json = runs_dir / "run.json"
            valid_run_json.write_text('{}')

            # Test helper function to run main with custom argv
            def main_with_argv(argv):
                old_argv = sys.argv
                sys.argv = argv
                try:
                    self.module.main()
                except SystemExit as e:
                    sys.argv = old_argv
                    raise e
                except OSError:
                    # Expected: execvp will fail since command doesn't exist
                    sys.argv = old_argv
                finally:
                    sys.argv = old_argv

            # Test 1: Path traversal attempt should fail
            with self.assertRaises(SystemExit) as cm:
                main_with_argv([
                    "agent_runner.py",
                    "../../../etc/passwd",
                    "test",
                    str(valid_prompt)
                ])
            self.assertIn("Invalid", str(cm.exception))

            # Test 2: Absolute path should fail
            with self.assertRaises(SystemExit) as cm:
                main_with_argv([
                    "agent_runner.py",
                    "/etc/passwd",
                    "test",
                    str(valid_prompt)
                ])
            self.assertIn("Invalid", str(cm.exception))

            # Test 3: Invalid agent_name format should fail
            with self.assertRaises(SystemExit) as cm:
                main_with_argv([
                    "agent_runner.py",
                    str(valid_agents_json),
                    "../../malicious",
                    str(valid_prompt)
                ])
            self.assertIn("Invalid", str(cm.exception))

            # Test 4: Invalid prompt_file path should fail
            with self.assertRaises(SystemExit) as cm:
                main_with_argv([
                    "agent_runner.py",
                    str(valid_agents_json),
                    "test",
                    "../../../etc/passwd"
                ])
            self.assertIn("Invalid", str(cm.exception))

    def test_command_line_run_json_validation(self) -> None:
        """Test that run_json command-line argument is validated."""
        from unittest.mock import patch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid directory structure
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            valid_agents_json = agents_dir / "test.json"
            valid_agents_json.write_text('{"agents": {"test": {"command": "claude", "args": []}}}')

            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            valid_prompt = prompts_dir / "test.md"
            valid_prompt.write_text("test prompt")

            runs_dir = Path(tmpdir) / "runs"
            runs_dir.mkdir()
            valid_run_json = runs_dir / "run.json"
            valid_run_json.write_text('{}')

            # Test helper function to run main with custom argv
            def main_with_argv(argv):
                old_argv = sys.argv
                sys.argv = argv
                try:
                    self.module.main()
                except SystemExit as e:
                    sys.argv = old_argv
                    raise e
                except OSError:
                    # Expected: execvp will fail since command doesn't exist
                    sys.argv = old_argv
                finally:
                    sys.argv = old_argv

            # Test 1: Invalid run_json path should fail
            with self.assertRaises(SystemExit) as cm:
                main_with_argv([
                    "agent_runner.py",
                    str(valid_agents_json),
                    "test",
                    str(valid_prompt),
                    "../../../etc/passwd"
                ])
            self.assertIn("Invalid", str(cm.exception))

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
                    "integrity": {"prompt_md_hash": original_hash, "hash_algorithm": "sha256"},
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

    def test_tampered_run_sh_integrity(self) -> None:
        """Test that tampered run.sh file is detected and raises an error."""
        # Import integrity module to compute hash
        from scripts.integrity import hash_file_content

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

        # Compute the original hash of run.sh
        original_hash = hash_file_content(str(run_script))

        # Create run metadata with integrity hash
        run_file = run_dir / "run.json"
        run_metadata = {
            "resume_from": "run-1",
            "agent_config": {"command": "echo", "args": ["test"]},
            "integrity": {"run_sh_hash": original_hash, "hash_algorithm": "sha256"},
        }
        run_file.write_text(json.dumps(run_metadata) + "\n", encoding="utf-8")

        # Load metadata from file to simulate real usage
        run_metadata = json.loads(run_file.read_text(encoding="utf-8"))

        # Tamper with run.sh
        run_script.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "echo 'MALICIOUS CONTENT'\n",
            encoding="utf-8",
        )

        # Verify that integrity check fails
        from agent_runner import verify_run_script_integrity

        with self.assertRaises(SystemExit) as context:
            verify_run_script_integrity(str(run_script), run_metadata)

        # Verify the error message mentions integrity check failure
        error_message = str(context.exception).lower()
        self.assertIn("integrity", error_message)
        self.assertIn("tampered", error_message)

    def test_missing_integrity_hash_allows_execution(self) -> None:
        """Test that missing integrity hash in run metadata allows execution to proceed."""
        # Create run metadata WITHOUT integrity field
        run_file = Path(self.temp_dir.name) / "run.json"
        run_file.write_text(
            json.dumps(
                {
                    "resume_from": "run-1",
                    "agent_config": {"command": "claude", "args": []},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Verify that execution proceeds without error
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
            with patch.object(self.module.os, "execvp") as execvp:
                self.module.main()

        # Verify execvp was called (meaning execution proceeded)
        execvp.assert_called_once_with(
            "claude",
            ["claude", "Implement the selected task."],
        )

    def test_hash_generation_in_create_run_record(self) -> None:
        """Test that create_run_record generates integrity hashes for prompt.md and run.sh."""
        import tempfile
        import shutil
        import uuid

        # Load the autoflow module
        autoflow_module = load_module(
            self.repo_root / "scripts" / "autoflow.py",
            "autoflow_test"
        )

        # Create a temporary directory structure for the test
        temp_base = tempfile.mkdtemp()
        try:
            # Create .autoflow directory structure
            autoflow_dir = Path(temp_base) / ".autoflow"
            autoflow_dir.mkdir()
            specs_dir = autoflow_dir / "specs"
            specs_dir.mkdir()
            tasks_dir = autoflow_dir / "tasks"
            tasks_dir.mkdir()
            runs_dir = autoflow_dir / "runs"
            runs_dir.mkdir()

            # Create a minimal spec directory
            spec_dir = specs_dir / "test-spec"
            spec_dir.mkdir()
            spec_file = spec_dir / "SPEC.md"
            spec_file.write_text("# Test Spec\n\nTest specification.\n", encoding="utf-8")

            # Create a minimal tasks file
            tasks_file = tasks_dir / "test-spec.json"
            tasks_file.write_text(
                json.dumps({
                    "tasks": [
                        {
                            "id": "T1",
                            "title": "Test Task",
                            "description": "Test task",
                            "status": "todo",
                            "owner_role": "implementation-runner",
                            "depends_on": [],
                            "acceptance_criteria": []
                        }
                    ]
                }),
                encoding="utf-8"
            )

            # Create a minimal agents.json
            agents_file = autoflow_dir / "agents.json"
            agents_file.write_text(
                json.dumps({
                    "agents": {
                        "test-agent": {
                            "command": "echo",
                            "args": ["test"]
                        }
                    }
                }),
                encoding="utf-8"
            )

            # Create a minimal system.json
            system_file = autoflow_dir / "system.json"
            system_file.write_text(
                json.dumps({
                    "model_profiles": {},
                    "tool_profiles": {}
                }),
                encoding="utf-8"
            )

            # Patch ROOT to point to our temp directory
            original_root = autoflow_module.ROOT
            autoflow_module.ROOT = Path(temp_base)

            # Patch the RUNS_DIR and other constants
            autoflow_module.RUNS_DIR = runs_dir
            autoflow_module.SPECS_DIR = specs_dir
            autoflow_module.TASKS_DIR = tasks_dir
            autoflow_module.STATE_DIR = autoflow_dir
            autoflow_module.AGENTS_FILE = agents_file
            autoflow_module.SYSTEM_CONFIG_FILE = autoflow_dir / "system.json"

            # Create a test run record
            run_dir = autoflow_module.create_run_record(
                spec_slug="test-spec",
                role="implementation-runner",
                agent_name="test-agent",
                task_id="T1"
            )

            # Verify run directory was created
            self.assertTrue(run_dir.exists())

            # Verify run.json was created with integrity hashes
            run_json_path = run_dir / "run.json"
            self.assertTrue(run_json_path.exists())

            run_data = json.loads(run_json_path.read_text(encoding="utf-8"))

            # Verify integrity field exists
            self.assertIn("integrity", run_data)
            integrity = run_data["integrity"]

            # Verify prompt_md_hash exists and is valid
            self.assertIn("prompt_md_hash", integrity)
            prompt_hash = integrity["prompt_md_hash"]
            self.assertEqual(len(prompt_hash), 64)  # SHA-256 hash is 64 hex chars
            self.assertTrue(all(c in "0123456789abcdef" for c in prompt_hash))

            # Verify run_sh_hash exists and is valid
            self.assertIn("run_sh_hash", integrity)
            script_hash = integrity["run_sh_hash"]
            self.assertEqual(len(script_hash), 64)  # SHA-256 hash is 64 hex chars
            self.assertTrue(all(c in "0123456789abcdef" for c in script_hash))

            # Verify hash_algorithm is sha256
            self.assertIn("hash_algorithm", integrity)
            self.assertEqual(integrity["hash_algorithm"], "sha256")

            # Verify the hashes match the actual file contents
            from scripts.integrity import hash_file_content
            prompt_path = run_dir / "prompt.md"
            run_script_path = run_dir / "run.sh"

            actual_prompt_hash = hash_file_content(str(prompt_path))
            actual_script_hash = hash_file_content(str(run_script_path))

            self.assertEqual(prompt_hash, actual_prompt_hash)
            self.assertEqual(script_hash, actual_script_hash)

        finally:
            # Restore original ROOT
            autoflow_module.ROOT = original_root
            # Clean up temp directory
            shutil.rmtree(temp_base, ignore_errors=True)

    def test_malicious_configs_rejected(self) -> None:
        """Integration test: malicious agent configs should be rejected at execution time."""
        import uuid

        def main_with_argv(argv: list[str]) -> None:
            old_argv = sys.argv
            sys.argv = argv
            try:
                self.module.main()
            except SystemExit:
                raise
            except OSError:
                # Expected when execvp reaches a non-existent command in tests.
                pass
            finally:
                sys.argv = old_argv

        unique_id = str(uuid.uuid4())[:8]
        prompt_file = Path(self.temp_dir.name) / f"malicious_prompt_{unique_id}.md"
        prompt_file.write_text("Execute malicious task", encoding="utf-8")

        scenarios = [
            (
                "malicious-agent",
                {"command": "rm", "args": ["-rf", "/"]},
                "Invalid agent specification",
                str(prompt_file),
            ),
            (
                "shell-agent",
                {"command": "claude", "args": ["|", "rm", "-rf", "/"]},
                "Invalid agent specification",
                str(prompt_file),
            ),
            (
                "exec-agent",
                {"command": "python", "args": ["-c", "import os; os.system('rm -rf /')"]},
                "Invalid agent specification",
                str(prompt_file),
            ),
            (
                "chain-agent",
                {"command": "claude", "args": [], "model": "claude; rm -rf /"},
                "Invalid agent specification",
                str(prompt_file),
            ),
            (
                "valid-agent",
                {"command": "claude", "args": []},
                "Invalid",
                "../../../etc/passwd",
            ),
            (
                "acp-malicious",
                {
                    "command": "placeholder",
                    "protocol": "acp",
                    "transport": {
                        "type": "stdio",
                        "command": "rm -rf /",
                        "args": [],
                        "prompt_mode": "argv",
                    },
                },
                "Invalid agent specification",
                str(prompt_file),
            ),
        ]

        for index, (agent_name, spec, expected_error, prompt_arg) in enumerate(scenarios):
            agents_file = Path(self.temp_dir.name) / f"malicious_agents_{unique_id}_{index}.json"
            agents_file.write_text(
                json.dumps({"agents": {agent_name: spec}}) + "\n",
                encoding="utf-8",
            )

            with self.subTest(agent=agent_name):
                with self.assertRaises(SystemExit) as context:
                    main_with_argv(
                        [
                            "agent_runner.py",
                            str(agents_file),
                            agent_name,
                            prompt_arg,
                        ]
                    )
                self.assertIn(expected_error, str(context.exception))


class AutoflowAgentRunnerValidationTests(unittest.TestCase):
    """Tests validation and sanitization in autoflow.agents.runner."""

    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prompt_file = Path(self.temp_dir.name) / "prompt.md"
        self.prompt_file.write_text("Implement the selected task.", encoding="utf-8")

        scripts_dir = str(self.repo_root / "scripts")
        while scripts_dir in sys.path:
            sys.path.remove(scripts_dir)
        if str(self.repo_root) not in sys.path:
            sys.path.insert(0, str(self.repo_root))

        existing_autoflow = sys.modules.get("autoflow")
        if existing_autoflow is not None and getattr(existing_autoflow, "__file__", "").endswith(
            "/scripts/autoflow.py"
        ):
            del sys.modules["autoflow"]

        from autoflow.agents.runner import AgentRunner, AgentValidationError
        from autoflow.core.config import load_config

        self.AgentValidationError = AgentValidationError
        self.runner = AgentRunner(load_config())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_malicious_command_rejected(self) -> None:
        with self.assertRaises(self.AgentValidationError):
            self.runner.build_command(
                {"command": "rm", "args": ["-rf", "/"]},
                str(self.prompt_file),
                run_metadata=None,
            )

    def test_shell_metacharacters_rejected(self) -> None:
        for args in [
            ["evil", "|", "rm", "-rf", "/"],
            ["evil", "&&", "malware"],
            ["evil", ";", "cat", "/etc/passwd"],
            ["evil", "$HOME"],
            ["evil", "`whoami`"],
        ]:
            with self.subTest(args=args):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(
                        {"command": "claude", "args": args},
                        str(self.prompt_file),
                        run_metadata=None,
                    )

    def test_dangerous_flags_rejected(self) -> None:
        for args in [
            ["--exec", "evil()"],
            ["--execute", "malware"],
            ["--eval", "malicious()"],
            ["-e", "evil()"],
            ["-c", "malware"],
        ]:
            with self.subTest(args=args):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(
                        {"command": "claude", "args": args},
                        str(self.prompt_file),
                        run_metadata=None,
                    )

    def test_invalid_command_format_rejected(self) -> None:
        for spec in [
            {"command": "claude; rm -rf /", "args": []},
            {"command": "claude && malware", "args": []},
            {"command": "claude|evil", "args": []},
            {"command": "", "args": []},
            {"command": "   ", "args": []},
            {"command": "claude evil", "args": []},
        ]:
            with self.subTest(command=spec["command"]):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(spec, str(self.prompt_file), run_metadata=None)

    def test_invalid_model_identifier_rejected(self) -> None:
        for spec in [
            {"command": "claude", "args": [], "model": "claude; rm -rf /"},
            {"command": "claude", "args": [], "model": "claude && malware"},
            {"command": "claude", "args": [], "model": "claude|evil"},
            {"command": "claude", "args": [], "model": "claude model"},
        ]:
            with self.subTest(model=spec["model"]):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(spec, str(self.prompt_file), run_metadata=None)

    def test_invalid_tool_names_rejected(self) -> None:
        for spec in [
            {"command": "claude", "args": [], "tools": ["Read; rm -rf /"]},
            {"command": "claude", "args": [], "tools": ["Read&&malware"]},
            {"command": "claude", "args": [], "tools": ["Read|evil"]},
            {"command": "claude", "args": [], "tools": ["Read Write"]},
            {"command": "claude", "args": [], "tools": ["Read,Bash(evil)"]},
        ]:
            with self.subTest(tools=spec["tools"]):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(spec, str(self.prompt_file), run_metadata=None)

    def test_malicious_runtime_args_rejected(self) -> None:
        for runtime_args in [
            ["--exec", "evil()"],
            ["|", "rm", "-rf"],
            ["&&", "malware"],
            [";evil"],
        ]:
            with self.subTest(runtime_args=runtime_args):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(
                        {"command": "claude", "args": [], "runtime_args": runtime_args},
                        str(self.prompt_file),
                        run_metadata=None,
                    )

    def test_malicious_resume_args_rejected(self) -> None:
        for resume in [
            {"mode": "args", "args": ["--exec", "evil()"]},
            {"mode": "args", "args": ["|", "rm", "-rf"]},
            {"mode": "args", "args": ["&&malware"]},
        ]:
            with self.subTest(resume=resume):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(
                        {"command": "claude", "args": [], "resume": resume},
                        str(self.prompt_file),
                        run_metadata=None,
                    )

    def test_malicious_acp_transport_command_rejected(self) -> None:
        for spec in [
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "rm -rf /",
                    "args": [],
                    "prompt_mode": "argv",
                },
            },
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "malware",
                    "args": [],
                    "prompt_mode": "argv",
                },
            },
            {
                "command": "placeholder",
                "protocol": "acp",
                "transport": {
                    "type": "stdio",
                    "command": "evil && pwn",
                    "args": [],
                    "prompt_mode": "argv",
                },
            },
        ]:
            with self.subTest(transport_command=spec["transport"]["command"]):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(spec, str(self.prompt_file), run_metadata=None)

    def test_malicious_acp_transport_args_rejected(self) -> None:
        malicious_transport = {
            "command": "placeholder",
            "protocol": "acp",
            "transport": {
                "type": "stdio",
                "command": "acp-agent",
                "args": ["--exec", "evil()"],
                "prompt_mode": "argv",
            },
        }
        with self.assertRaises(self.AgentValidationError):
            self.runner.build_command(
                malicious_transport,
                str(self.prompt_file),
                run_metadata=None,
            )

    def test_path_traversal_prevented(self) -> None:
        for path in [
            "../../../etc/passwd",
            "../../sensitive_file.txt",
            "../../../../../../../../etc/passwd",
            "./../../etc/passwd",
            "../sibling_dir/file.txt",
        ]:
            with self.subTest(path=path):
                with self.assertRaises(self.AgentValidationError):
                    self.runner.build_command(
                        {"command": "claude", "args": []},
                        path,
                        run_metadata=None,
                    )

    def test_valid_agent_spec_accepted(self) -> None:
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        test_prompt = Path(f"test_valid_spec_prompt_{unique_id}.md")
        test_prompt.write_text("Valid prompt content", encoding="utf-8")

        try:
            valid_specs = [
                {"command": "claude", "args": ["--print"]},
                {"command": "codex", "args": ["--full-auto"]},
                {
                    "command": "claude",
                    "args": [],
                    "model": "claude-sonnet-4-6",
                    "tools": ["Read", "Bash", "Write"],
                },
                {
                    "command": "claude",
                    "protocol": "acp",
                    "transport": {
                        "type": "stdio",
                        "command": "acp-agent",
                        "args": ["--serve"],
                        "prompt_mode": "argv",
                    },
                },
            ]
            for spec in valid_specs:
                with self.subTest(spec=spec):
                    command = self.runner.build_command(
                        spec,
                        str(test_prompt),
                        run_metadata=None,
                    )
                    self.assertIsInstance(command, list)
                    self.assertGreater(len(command), 0)
        finally:
            if test_prompt.exists():
                test_prompt.unlink()

    def test_valid_path_accepted(self) -> None:
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        valid_prompt = Path(f"test_valid_prompt_{unique_id}.md")
        valid_prompt.write_text("Valid prompt content", encoding="utf-8")

        try:
            command = self.runner.build_command(
                {"command": "claude", "args": []},
                str(valid_prompt),
                run_metadata=None,
            )
            self.assertIsInstance(command, list)
            self.assertGreater(len(command), 0)
        finally:
            if valid_prompt.exists():
                valid_prompt.unlink()

    def test_read_json_valid_file(self) -> None:
        test_file = Path(self.temp_dir.name) / "test.json"
        test_data = {"key": "value", "number": 42}
        test_file.write_text(json.dumps(test_data), encoding="utf-8")

        result = self.runner.read_json(test_file)
        self.assertEqual(result, test_data)

    def test_read_json_invalid_json_raises_error(self) -> None:
        test_file = Path(self.temp_dir.name) / "invalid.json"
        test_file.write_text("{ invalid json }", encoding="utf-8")

        with self.assertRaises(json.JSONDecodeError):
            self.runner.read_json(test_file)

    def test_read_json_missing_file_raises_error(self) -> None:
        missing_file = Path(self.temp_dir.name) / "missing.json"
        with self.assertRaises(FileNotFoundError):
            self.runner.read_json(missing_file)

    def test_load_prompt_valid_file(self) -> None:
        test_prompt = Path(self.temp_dir.name) / "test_prompt.md"
        test_content = "Test prompt content\nLine 2\nLine 3"
        test_prompt.write_text(test_content, encoding="utf-8")

        result = self.runner.load_prompt(test_prompt)
        self.assertEqual(result, test_content)

    def test_load_prompt_missing_file_raises_error(self) -> None:
        missing_prompt = Path(self.temp_dir.name) / "missing.md"
        with self.assertRaises(FileNotFoundError):
            self.runner.load_prompt(missing_prompt)

    def test_apply_runtime_config_model_and_tools(self) -> None:
        base_command = ["claude", "--print"]
        agent_spec = {
            "command": "claude",
            "model": "claude-sonnet-4-6",
            "tools": ["Read", "Bash", "Write"],
        }

        result = self.runner.apply_runtime_config(base_command, agent_spec)
        self.assertEqual(
            result,
            [
                "claude",
                "--print",
                "--model",
                "claude-sonnet-4-6",
                "--allowedTools",
                "Read,Bash,Write",
            ],
        )

    def test_apply_runtime_config_runtime_args(self) -> None:
        base_command = ["claude"]
        agent_spec = {
            "command": "claude",
            "runtime_args": ["--verbose", "--timeout", "60"],
        }

        result = self.runner.apply_runtime_config(base_command, agent_spec)
        self.assertEqual(result, ["claude", "--verbose", "--timeout", "60"])

    def test_apply_runtime_config_no_runtime_config(self) -> None:
        base_command = ["claude", "--print"]
        result = self.runner.apply_runtime_config(base_command, {"command": "claude"})
        self.assertEqual(result, base_command)

    def test_build_command_with_resume_subcommand(self) -> None:
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        test_prompt = Path(f"test_resume_prompt_{unique_id}.md")
        test_prompt.write_text("Implement the selected task.", encoding="utf-8")

        try:
            spec = {
                "command": "codex",
                "args": ["--full-auto"],
                "resume": {"mode": "subcommand", "subcommand": "resume", "args": ["--last"]},
            }
            command = self.runner.build_command(
                spec,
                str(test_prompt),
                run_metadata={"resume_from": "run-1"},
            )
            self.assertEqual(
                command,
                [
                    "codex",
                    "--full-auto",
                    "resume",
                    "--last",
                    "Implement the selected task.",
                ],
            )
        finally:
            if test_prompt.exists():
                test_prompt.unlink()

    def test_build_command_with_resume_args(self) -> None:
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        test_prompt = Path(f"test_resume_args_prompt_{unique_id}.md")
        test_prompt.write_text("Implement the selected task.", encoding="utf-8")

        try:
            spec = {
                "command": "claude",
                "args": [],
                "resume": {"mode": "args", "args": ["--resume"]},
            }
            command = self.runner.build_command(
                spec,
                str(test_prompt),
                run_metadata={"resume_from": "run-2"},
            )
            self.assertEqual(command, ["claude", "--resume", "Implement the selected task."])
        finally:
            if test_prompt.exists():
                test_prompt.unlink()

    def test_complete_integrity_workflow(self) -> None:
        """Test the complete integrity verification workflow for run artifacts."""
        import shutil
        import tempfile
        from scripts.integrity import hash_file_content, verify_file_integrity

        # Load autoflow module
        autoflow_module = load_module(
            self.repo_root / "scripts" / "autoflow.py",
            "autoflow_test"
        )

        # Create a temporary directory structure
        temp_base = tempfile.mkdtemp()
        autoflow_dir = Path(temp_base) / ".autoflow"
        runs_dir = autoflow_dir / "runs"
        specs_dir = autoflow_dir / "specs"
        tasks_dir = autoflow_dir / "tasks"

        try:
            # Create directories
            runs_dir.mkdir(parents=True, exist_ok=True)
            specs_dir.mkdir(parents=True, exist_ok=True)
            tasks_dir.mkdir(parents=True, exist_ok=True)

            # Create a minimal spec directory with SPEC.md
            spec_dir = specs_dir / "test-spec"
            spec_dir.mkdir(parents=True, exist_ok=True)
            spec_file = spec_dir / "SPEC.md"
            spec_file.write_text("# Test Spec\n\nTest specification.\n", encoding="utf-8")

            # Create a minimal tasks file (in root tasks directory)
            tasks_file = tasks_dir / "test-spec.json"
            tasks_file.write_text(
                json.dumps({
                    "tasks": [
                        {
                            "id": "T1",
                            "title": "Test Task",
                            "status": "in_progress",
                            "owner_role": "implementation-runner",
                            "description": "A test task",
                            "depends_on": [],
                            "acceptance_criteria": []
                        }
                    ]
                }),
                encoding="utf-8"
            )

            # Create a minimal agents.json
            agents_file = autoflow_dir / "agents.json"
            agents_file.write_text(
                json.dumps({
                    "agents": {
                        "test-agent": {
                            "command": "echo",
                            "args": ["test"]
                        }
                    }
                }),
                encoding="utf-8"
            )

            # Create a minimal system.json
            system_file = autoflow_dir / "system.json"
            system_file.write_text(
                json.dumps({
                    "model_profiles": {},
                    "tool_profiles": {}
                }),
                encoding="utf-8"
            )

            # Patch ROOT to point to our temp directory
            original_root = autoflow_module.ROOT
            autoflow_module.ROOT = Path(temp_base)

            # Patch the RUNS_DIR and other constants
            autoflow_module.RUNS_DIR = runs_dir
            autoflow_module.SPECS_DIR = specs_dir
            autoflow_module.TASKS_DIR = tasks_dir
            autoflow_module.STATE_DIR = autoflow_dir
            autoflow_module.AGENTS_FILE = agents_file
            autoflow_module.SYSTEM_CONFIG_FILE = autoflow_dir / "system.json"

            # Create a test run record
            run_dir = autoflow_module.create_run_record(
                spec_slug="test-spec",
                role="implementation-runner",
                agent_name="test-agent",
                task_id="T1"
            )

            # Verify run directory was created
            self.assertTrue(run_dir.exists())

            # Load run.json to get integrity hashes
            run_json_path = run_dir / "run.json"
            run_data = json.loads(run_json_path.read_text(encoding="utf-8"))
            integrity = run_data["integrity"]

            # Test 1: Verify original integrity of prompt.md
            prompt_path = run_dir / "prompt.md"
            self.assertTrue(verify_file_integrity(prompt_path, integrity["prompt_md_hash"]))

            # Test 2: Verify original integrity of run.sh
            run_script_path = run_dir / "run.sh"
            self.assertTrue(verify_file_integrity(run_script_path, integrity["run_sh_hash"]))

            # Test 3: Verify hashes match actual file contents
            actual_prompt_hash = hash_file_content(prompt_path)
            actual_script_hash = hash_file_content(run_script_path)
            self.assertEqual(integrity["prompt_md_hash"], actual_prompt_hash)
            self.assertEqual(integrity["run_sh_hash"], actual_script_hash)

            # Test 4: Simulate tampering with prompt.md
            original_prompt_content = prompt_path.read_text(encoding="utf-8")
            prompt_path.write_text("Tampered content", encoding="utf-8")

            # Verify tampering is detected
            self.assertFalse(verify_file_integrity(prompt_path, integrity["prompt_md_hash"]))

            # Test 5: Restore original content and verify integrity is restored
            prompt_path.write_text(original_prompt_content, encoding="utf-8")
            self.assertTrue(verify_file_integrity(prompt_path, integrity["prompt_md_hash"]))

            # Test 6: Simulate tampering with run.sh
            original_script_content = run_script_path.read_text(encoding="utf-8")
            run_script_path.write_text("# Tampered script\n", encoding="utf-8")

            # Verify tampering is detected
            self.assertFalse(verify_file_integrity(run_script_path, integrity["run_sh_hash"]))

            # Test 7: Restore original content and verify integrity is restored
            run_script_path.write_text(original_script_content, encoding="utf-8")
            self.assertTrue(verify_file_integrity(run_script_path, integrity["run_sh_hash"]))

            # Test 8: Verify both files simultaneously
            self.assertTrue(verify_file_integrity(prompt_path, integrity["prompt_md_hash"]))
            self.assertTrue(verify_file_integrity(run_script_path, integrity["run_sh_hash"]))

        finally:
            # Restore original ROOT
            autoflow_module.ROOT = original_root
            # Clean up temp directory
            shutil.rmtree(temp_base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
