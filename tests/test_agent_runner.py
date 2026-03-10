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


if __name__ == "__main__":
    unittest.main()
