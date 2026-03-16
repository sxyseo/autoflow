"""Health check module with severity categorization for automatic rollback.

This module provides health check functionality that executes verification commands
and categorizes results by severity (critical, warning, success) to determine
whether rollback should be triggered.
"""

from __future__ import annotations

import subprocess
from enum import Enum
from pathlib import Path


class HealthStatus(Enum):
    """Health check status levels."""

    SUCCESS = "success"
    WARNING = "warning"
    CRITICAL = "critical"


class HealthCheck:
    """Execute and categorize health checks for automatic rollback decisions.

    Health checks run verification commands and categorize the results:
    - CRITICAL: Tests that MUST pass for the system to function (rollback triggered)
    - WARNING: Issues that should be logged but don't block continuation
    - SUCCESS: All checks passed (continue with workflow)

    Example:
        check = HealthCheck(root=Path("/path/to/project"))
        result = check.run_command(
            command=["pytest", "-x"],
            severity=HealthStatus.CRITICAL,
            timeout=60
        )
        if result["status"] == HealthStatus.CRITICAL:
            # Trigger rollback
            pass
    """

    def __init__(self, root: Path | None = None) -> None:
        """Initialize health check with project root directory.

        Args:
            root: Project root directory. Defaults to current working directory.
        """
        self.root = root or Path.cwd()

    def run_command(
        self,
        command: list[str] | str,
        severity: HealthStatus,
        timeout: int = 120,
        cwd: Path | None = None,
    ) -> dict[str, Any]:
        """Run a verification command and categorize the result.

        Args:
            command: Command to execute as list or string.
            severity: Severity level for this check (CRITICAL, WARNING, SUCCESS).
            timeout: Maximum execution time in seconds. Default: 120.
            cwd: Working directory for command execution. Defaults to root.

        Returns:
            Dictionary with:
                - command: Executed command string
                - status: HealthStatus (SUCCESS, WARNING, or CRITICAL)
                - returncode: Process exit code
                - stdout: Standard output captured
                - stderr: Standard error captured
                - timed_out: True if command timed out
        """
        working_dir = cwd or self.root

        # Convert list command to string for shell execution
        command_str = " ".join(command) if isinstance(command, list) else command

        try:
            proc = subprocess.run(
                command_str,
                cwd=working_dir,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            status = HealthStatus.SUCCESS if proc.returncode == 0 else severity

            return {
                "command": command_str,
                "status": status,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "timed_out": False,
            }

        except subprocess.TimeoutExpired:
            return {
                "command": command_str,
                "status": severity,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "timed_out": True,
            }

    def run_checks(
        self,
        checks: list[dict[str, Any]],
        timeout: int = 120,
    ) -> dict[str, Any]:
        """Run multiple health checks and aggregate results.

        Args:
            checks: List of check dictionaries with keys:
                - command: Command to execute (list or string)
                - severity: HealthStatus level for this check
                - name: Optional name for the check
            timeout: Default timeout for all checks. Can be overridden per check.

        Returns:
            Dictionary with:
                - overall_status: Worst status among all checks
                - results: List of individual check results
                - passed: Number of checks that passed
                - failed: Number of checks that failed
                - critical_failures: Number of critical failures
        """
        results = []
        critical_failures = 0
        failed = 0
        passed = 0
        worst_status = HealthStatus.SUCCESS

        for check in checks:
            command = check["command"]
            severity = HealthStatus(check["severity"])
            check_timeout = check.get("timeout", timeout)
            name = check.get("name", str(command))

            result = self.run_command(
                command=command,
                severity=severity,
                timeout=check_timeout,
            )
            result["name"] = name
            results.append(result)

            # Track statistics
            if result["status"] == HealthStatus.CRITICAL:
                critical_failures += 1
                failed += 1
                worst_status = HealthStatus.CRITICAL
            elif result["status"] == HealthStatus.WARNING:
                failed += 1
                if worst_status == HealthStatus.SUCCESS:
                    worst_status = HealthStatus.WARNING
            else:
                passed += 1

        return {
            "overall_status": worst_status,
            "results": results,
            "passed": passed,
            "failed": failed,
            "critical_failures": critical_failures,
        }

    def should_rollback(self, health_result: dict) -> bool:
        """Determine if rollback should be triggered based on health check results.

        Args:
            health_result: Result dictionary from run_checks().

        Returns:
            True if rollback should be triggered (any critical failures).
        """
        return health_result.get("critical_failures", 0) > 0

    def format_summary(self, health_result: dict) -> str:
        """Format health check results as a human-readable summary.

        Args:
            health_result: Result dictionary from run_checks().

        Returns:
            Multi-line string summary of results.
        """
        lines = [
            "Health Check Summary",
            "=" * 50,
            f"Overall Status: {health_result['overall_status'].value.upper()}",
            f"Passed: {health_result['passed']}",
            f"Failed: {health_result['failed']}",
            f"Critical Failures: {health_result['critical_failures']}",
            "",
        ]

        for i, result in enumerate(health_result["results"], 1):
            status_symbol = "✓" if result["status"] == HealthStatus.SUCCESS else "✗"
            lines.append(f"{i}. [{status_symbol}] {result['name']}")
            if result["status"] != HealthStatus.SUCCESS:
                lines.append(f"   Status: {result['status'].value}")
                if result["stderr"]:
                    lines.append(f"   Error: {result['stderr'][:200]}")
                elif result["stdout"]:
                    lines.append(f"   Output: {result['stdout'][:200]}")

        return "\n".join(lines)
