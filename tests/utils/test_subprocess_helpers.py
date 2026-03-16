"""
Unit Tests for Subprocess Helpers

Tests for command execution utilities.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from autoflow.utils.subprocess_helpers import run_cmd


class SubprocessHelpersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_cmd_executes_simple_command(self) -> None:
        """run_cmd should execute simple commands and return output."""
        result = run_cmd(["echo", "test"])
        self.assertEqual(result.stdout.strip(), "test")
        self.assertEqual(result.returncode, 0)

    def test_run_cmd_captures_stdout(self) -> None:
        """run_cmd should capture stdout correctly."""
        result = run_cmd(["echo", "hello world"])
        self.assertIn("hello world", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_run_cmd_captures_stderr(self) -> None:
        """run_cmd should capture stderr correctly."""
        result = run_cmd(["sh", "-c", "echo error >&2"], check=False)
        self.assertIn("error", result.stderr)

    def test_run_cmd_returns_zero_exit_code(self) -> None:
        """run_cmd should return 0 for successful commands."""
        result = run_cmd(["true"])
        self.assertEqual(result.returncode, 0)

    def test_run_cmd_returns_nonzero_exit_code(self) -> None:
        """run_cmd should return non-zero exit code for failing commands."""
        result = run_cmd(["false"], check=False)
        self.assertEqual(result.returncode, 1)

    def test_run_cmd_raises_on_failure_when_check_true(self) -> None:
        """run_cmd should raise CalledProcessError when check=True and command fails."""
        with self.assertRaises(subprocess.CalledProcessError):
            run_cmd(["false"], check=True)

    def test_run_cmd_does_not_raise_when_check_false(self) -> None:
        """run_cmd should not raise when check=False even if command fails."""
        result = run_cmd(["false"], check=False)
        self.assertEqual(result.returncode, 1)

    def test_run_cmd_respects_cwd(self) -> None:
        """run_cmd should execute command in specified working directory."""
        # Create a file in temp directory
        test_file = self.root / "test.txt"
        test_file.write_text("content")

        # List files in temp directory
        result = run_cmd(["ls"], cwd=self.root)
        self.assertIn("test.txt", result.stdout)

    def test_run_cmd_cwd_defaults_to_current(self) -> None:
        """run_cmd should use current directory when cwd is not specified."""
        # This test just verifies it works without crashing
        result = run_cmd(["pwd"])
        self.assertIsNotNone(result.stdout)
        self.assertGreater(len(result.stdout), 0)

    def test_run_cmd_handles_multiple_arguments(self) -> None:
        """run_cmd should handle commands with multiple arguments."""
        result = run_cmd(["echo", "arg1", "arg2", "arg3"])
        self.assertIn("arg1", result.stdout)
        self.assertIn("arg2", result.stdout)
        self.assertIn("arg3", result.stdout)

    def test_run_cmd_handles_special_characters(self) -> None:
        """run_cmd should handle special characters in output."""
        result = run_cmd(["echo", "hello\nworld\t!@#$%"])
        self.assertIn("hello", result.stdout)
        self.assertIn("world", result.stdout)

    def test_run_cmd_raises_on_command_not_found(self) -> None:
        """run_cmd should raise FileNotFoundError for non-existent commands."""
        with self.assertRaises(FileNotFoundError):
            run_cmd(["nonexistent_command_xyz"])

    def test_run_cmd_with_pipe_output(self) -> None:
        """run_cmd should handle output from piped commands."""
        # Create a script that outputs to stdout
        script = self.root / "script.sh"
        script.write_text("#!/bin/sh\necho 'multiline\noutput'")
        script.chmod(0o755)

        result = run_cmd([str(script)])
        self.assertIn("multiline", result.stdout)
        self.assertIn("output", result.stdout)

    def test_run_cmd_empty_output(self) -> None:
        """run_cmd should handle commands with no output."""
        result = run_cmd(["true"])
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_run_cmd_preserves_exit_code(self) -> None:
        """run_cmd should preserve the actual exit code."""
        # Test different exit codes
        result = run_cmd(["sh", "-c", "exit 42"], check=False)
        self.assertEqual(result.returncode, 42)

    def test_run_cmd_text_mode_returns_strings(self) -> None:
        """run_cmd should return string output in text mode."""
        result = run_cmd(["echo", "test"])
        self.assertIsInstance(result.stdout, str)
        self.assertIsInstance(result.stderr, str)


if __name__ == "__main__":
    unittest.main()
