"""
Unit Tests for Agent Runner

Tests the agent runner command building functionality from autoflow.agents.runner.
These tests verify that agent specifications are correctly converted into
executable commands with proper arguments, tools, and resume configuration.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autoflow.agents.runner import build_command


class TestAgentRunner(unittest.TestCase):
    """Test cases for agent runner command building."""

    def setUp(self) -> None:
        """Set up test fixtures with temporary directory and prompt file."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prompt_file = Path(self.temp_dir.name) / "prompt.md"
        self.prompt_file.write_text("Implement the selected task.", encoding="utf-8")

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_regular_command_uses_prompt_text(self) -> None:
        """Test that a regular command includes the prompt text."""
        command = build_command(
            {"command": "echo", "args": ["agent"]},
            str(self.prompt_file),
            run_metadata=None,
        )
        self.assertEqual(command, ["echo", "agent", "Implement the selected task."])

    def test_codex_resume_uses_subcommand(self) -> None:
        """Test that codex resume uses subcommand mode."""
        command = build_command(
            {
                "command": "codex",
                "args": ["--full-auto"],
                "resume": {
                    "mode": "subcommand",
                    "subcommand": "resume",
                    "args": ["--last"],
                },
            },
            str(self.prompt_file),
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

    def test_claude_resume_uses_continue_flag(self) -> None:
        """Test that claude resume uses args mode for --continue flag."""
        command = build_command(
            {
                "command": "claude",
                "args": [],
                "resume": {"mode": "args", "args": ["--continue"]},
            },
            str(self.prompt_file),
            run_metadata={"resume_from": "run-2"},
        )
        self.assertEqual(
            command, ["claude", "--continue", "Implement the selected task."]
        )

    def test_model_and_tools_are_applied(self) -> None:
        """Test that model and tools configuration is applied to claude commands."""
        command = build_command(
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
        """Test that ACP stdio agents use the transport command."""
        command = build_command(
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
        self.assertEqual(
            command, ["acp-agent", "--serve", "Implement the selected task."]
        )

    def test_agent_config_from_run_metadata_is_applied(self) -> None:
        """Test that agent config from run metadata is properly applied."""
        # Simulate resolved agent config with overrides from run metadata
        command = build_command(
            {
                "command": "claude",
                "args": [],
                "model": "claude-sonnet-4-6",
                "tools": ["Read"],
                "resume": {"mode": "args", "args": ["--continue"]},
            },
            str(self.prompt_file),
            run_metadata={"resume_from": "run-9"},
        )
        self.assertEqual(
            command,
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
