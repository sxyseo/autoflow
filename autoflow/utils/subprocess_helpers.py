"""
Subprocess Helpers - Command Execution Utilities

Provides utilities for running subprocess commands with consistent
error handling and output capture.
"""

import subprocess
from pathlib import Path


def run_cmd(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Run a command and capture its output.

    Args:
        args: Command arguments as a list of strings
        cwd: Working directory for the command (defaults to current directory)
        check: Whether to raise an exception if the command returns non-zero exit code

    Returns:
        CompletedProcess object containing stdout, stderr, and returncode

    Raises:
        subprocess.CalledProcessError: If check=True and command returns non-zero exit code
        FileNotFoundError: If the command executable is not found
    """
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


__all__ = ["run_cmd"]
