"""Health check runner with timeout and output capture for CI/CD workflows.

This module provides a convenient runner interface for executing health checks
in continuous integration environments, with built-in timeout handling and
output capture for logging and debugging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autoflow.rollback.health import HealthCheck, HealthStatus


class HealthCheckRunner:
    """Execute health checks with timeout and output capture for CI workflows.

    The HealthCheckRunner provides a simplified interface for running health
    checks in automated workflows, with sensible defaults for timeout and
    comprehensive output capture for debugging failures.

    Example:
        runner = HealthCheckRunner(root=Path("/path/to/project"))

        # Run a single check
        result = runner.run(
            command=["pytest", "-xvs"],
            severity=HealthStatus.CRITICAL,
            name="Unit tests"
        )

        # Run multiple checks
        results = runner.run_batch([
            {
                "command": ["pytest", "-x"],
                "severity": HealthStatus.CRITICAL,
                "name": "Unit tests"
            },
            {
                "command": ["flake8", "."],
                "severity": HealthStatus.WARNING,
                "name": "Linting"
            }
        ])
    """

    def __init__(self, root: Path | None = None, default_timeout: int = 120) -> None:
        """Initialize health check runner with project configuration.

        Args:
            root: Project root directory. Defaults to current working directory.
            default_timeout: Default timeout in seconds for all checks. Default: 120.
        """
        self.root = root or Path.cwd()
        self.default_timeout = default_timeout
        self._health_check = HealthCheck(root=self.root)

    def run(
        self,
        command: list[str] | str,
        severity: HealthStatus,
        name: str | None = None,
        timeout: int | None = None,
        cwd: Path | None = None,
    ) -> dict[str, Any]:
        """Run a single health check with timeout and output capture.

        Args:
            command: Command to execute as list or string.
            severity: Severity level for this check (CRITICAL, WARNING, SUCCESS).
            name: Optional name for this check. Defaults to command string.
            timeout: Maximum execution time in seconds. Defaults to default_timeout.
            cwd: Working directory for command execution. Defaults to root.

        Returns:
            Dictionary with:
                - command: Executed command string
                - status: HealthStatus (SUCCESS, WARNING, or CRITICAL)
                - returncode: Process exit code
                - stdout: Standard output captured
                - stderr: Standard error captured
                - timed_out: True if command timed out
                - name: Check name (if provided)
        """
        check_timeout = timeout or self.default_timeout

        result = self._health_check.run_command(
            command=command,
            severity=severity,
            timeout=check_timeout,
            cwd=cwd,
        )

        if name:
            result["name"] = name

        return result

    def run_batch(
        self,
        checks: list[dict[str, Any]],
        stop_on_first_failure: bool = False,
    ) -> dict[str, Any]:
        """Run multiple health checks and aggregate results.

        Args:
            checks: List of check dictionaries with keys:
                - command: Command to execute (list or string) [required]
                - severity: HealthStatus level for this check [required]
                - name: Optional name for the check
                - timeout: Optional timeout in seconds (overrides default)
                - cwd: Optional working directory (overrides root)
            stop_on_first_failure: Stop execution on first critical failure.

        Returns:
            Dictionary with:
                - overall_status: Worst status among all checks
                - results: List of individual check results
                - passed: Number of checks that passed
                - failed: Number of checks that failed
                - critical_failures: Number of critical failures
        """
        # Normalize checks with default timeout
        normalized_checks = []
        for check in checks:
            normalized_check = check.copy()
            if "timeout" not in normalized_check:
                normalized_check["timeout"] = self.default_timeout
            normalized_checks.append(normalized_check)

        return self._health_check.run_checks(
            checks=normalized_checks,
            timeout=self.default_timeout,
        )

    def run_with_fallback(
        self,
        command: list[str] | str,
        fallback_command: list[str] | str,
        severity: HealthStatus,
        name: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Run a health check with fallback command on failure.

        Args:
            command: Primary command to execute.
            fallback_command: Fallback command if primary fails.
            severity: Severity level for this check.
            name: Optional name for this check.
            timeout: Maximum execution time in seconds.

        Returns:
            Result dictionary from the successful command, or the primary
            command result if both fail.
        """
        primary_result = self.run(
            command=command,
            severity=severity,
            name=name,
            timeout=timeout,
        )

        # If primary succeeded, return it
        if primary_result["status"] == HealthStatus.SUCCESS:
            return primary_result

        # Try fallback
        fallback_name = f"{name} (fallback)" if name else None
        fallback_result = self.run(
            command=fallback_command,
            severity=severity,
            name=fallback_name,
            timeout=timeout,
        )

        # Return fallback if it succeeded, otherwise return primary
        if fallback_result["status"] == HealthStatus.SUCCESS:
            fallback_result["fallback_used"] = True
            return fallback_result

        primary_result["fallback_used"] = False
        primary_result["fallback_tried"] = True
        return primary_result

    def should_rollback(self, health_result: dict[str, Any]) -> bool:
        """Determine if rollback should be triggered based on health check results.

        Args:
            health_result: Result dictionary from run() or run_batch().

        Returns:
            True if rollback should be triggered (any critical failures).
        """
        # Handle single check result
        if "results" not in health_result:
            return health_result.get("status") == HealthStatus.CRITICAL

        # Handle batch result
        return self._health_check.should_rollback(health_result)

    def format_summary(self, health_result: dict[str, Any]) -> str:
        """Format health check results as a human-readable summary.

        Args:
            health_result: Result dictionary from run() or run_batch().

        Returns:
            Multi-line string summary of results.
        """
        # Handle single check result
        if "results" not in health_result:
            lines = [
                "Health Check Result",
                "=" * 50,
                f"Command: {health_result.get('name', health_result.get('command', 'Unknown'))}",
                f"Status: {health_result['status'].value.upper()}",
                f"Return Code: {health_result.get('returncode', 'N/A')}",
                "",
            ]

            if health_result.get("timed_out"):
                lines.append(f"⚠️  Timed out after {health_result.get('timeout', 'unknown')} seconds")

            if health_result.get("stderr"):
                lines.append(f"Stderr:\n{health_result['stderr']}")
            elif health_result.get("stdout"):
                lines.append(f"Stdout:\n{health_result['stdout']}")

            return "\n".join(lines)

        # Handle batch result
        return self._health_check.format_summary(health_result)
