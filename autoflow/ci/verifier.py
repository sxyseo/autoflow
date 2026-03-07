"""
Autoflow CI Verifier Module

Provides CI verification capabilities for running checks and gates
before code is committed. This ensures code quality in autonomous
development workflows.

Usage:
    from autoflow.ci.verifier import CIVerifier

    verifier = CIVerifier()
    result = await verifier.run_all_checks(workdir="/path/to/project")

    if result.passed:
        print("All CI checks passed!")
    else:
        print(f"CI failed: {result.failed_checks}")
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union


class CheckStatus(str, Enum):
    """Status of a CI check."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    TIMEOUT = "timeout"


class CheckType(str, Enum):
    """Types of CI checks."""

    TEST = "test"
    LINT = "lint"
    TYPE_CHECK = "type_check"
    SECURITY = "security"
    FORMAT = "format"
    BUILD = "build"
    CUSTOM = "custom"


@dataclass
class CheckResult:
    """
    Result of a single CI check.

    Attributes:
        check_id: Unique identifier for this check
        check_type: Type of check performed
        name: Human-readable name of the check
        status: Check status
        output: Standard output from the check
        error: Standard error from the check
        exit_code: Process exit code
        duration_seconds: Time taken to run the check
        started_at: When check started
        completed_at: When check completed
        metadata: Additional check metadata
    """

    check_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    check_type: CheckType = CheckType.CUSTOM
    name: str = ""
    status: CheckStatus = CheckStatus.PENDING
    output: str = ""
    error: str = ""
    exit_code: Optional[int] = None
    duration_seconds: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Check if this check passed."""
        return self.status == CheckStatus.PASSED

    @property
    def failed(self) -> bool:
        """Check if this check failed."""
        return self.status in (
            CheckStatus.FAILED,
            CheckStatus.ERROR,
            CheckStatus.TIMEOUT,
        )

    def mark_started(self) -> None:
        """Mark the check as started."""
        self.status = CheckStatus.RUNNING
        self.started_at = datetime.utcnow()

    def mark_complete(
        self,
        status: CheckStatus,
        output: str = "",
        error: str = "",
        exit_code: Optional[int] = None,
    ) -> None:
        """
        Mark the check as complete.

        Args:
            status: Final check status
            output: Standard output
            error: Standard error
            exit_code: Process exit code
        """
        self.status = status
        self.output = output
        self.error = error
        self.exit_code = exit_code
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "check_id": self.check_id,
            "check_type": self.check_type.value,
            "name": self.name,
            "status": self.status.value,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "output": self.output[:1000] if self.output else None,  # Truncated
            "error": self.error[:1000] if self.error else None,  # Truncated
            "metadata": self.metadata,
        }


@dataclass
class CheckDefinition:
    """
    Definition of a CI check to run.

    Attributes:
        name: Human-readable name
        check_type: Type of check
        command: Command to execute (list of args or string)
        cwd: Working directory for the command
        timeout_seconds: Timeout for the check
        env: Environment variables for the command
        expected_exit_codes: Exit codes that indicate success
        enabled: Whether this check is enabled
        required: Whether this check must pass for overall success
    """

    name: str
    check_type: CheckType
    command: Union[str, list[str]]
    cwd: Optional[Union[str, Path]] = None
    timeout_seconds: int = 300
    env: Optional[dict[str, str]] = None
    expected_exit_codes: list[int] = field(default_factory=lambda: [0])
    enabled: bool = True
    required: bool = True

    def __post_init__(self) -> None:
        """Normalize command to list format."""
        if isinstance(self.command, str):
            self.command = [self.command]


@dataclass
class VerificationResult:
    """
    Aggregated result from running multiple CI checks.

    Attributes:
        verification_id: Unique identifier for this verification
        status: Overall verification status
        check_results: Results from individual checks
        passed: Whether all required checks passed
        started_at: When verification started
        completed_at: When verification completed
        duration_seconds: Total verification time
        error: Error message if verification failed
        metadata: Additional metadata
    """

    verification_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: CheckStatus = CheckStatus.PENDING
    check_results: list[CheckResult] = field(default_factory=list)
    passed: bool = False
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_checks(self) -> int:
        """Get total number of checks."""
        return len(self.check_results)

    @property
    def passed_checks(self) -> list[CheckResult]:
        """Get list of passed checks."""
        return [c for c in self.check_results if c.passed]

    @property
    def failed_checks(self) -> list[CheckResult]:
        """Get list of failed checks."""
        return [c for c in self.check_results if c.failed]

    @property
    def skipped_checks(self) -> list[CheckResult]:
        """Get list of skipped checks."""
        return [c for c in self.check_results if c.status == CheckStatus.SKIPPED]

    @property
    def required_failures(self) -> list[CheckResult]:
        """Get failed required checks."""
        return [c for c in self.failed_checks if c.metadata.get("required", True)]

    def mark_complete(
        self,
        status: CheckStatus,
        passed: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """
        Mark verification as complete.

        Args:
            status: Final verification status
            passed: Whether verification passed
            error: Error message if any
        """
        self.status = status
        self.passed = passed
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "verification_id": self.verification_id,
            "status": self.status.value,
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_count": len(self.passed_checks),
            "failed_count": len(self.failed_checks),
            "skipped_count": len(self.skipped_checks),
            "required_failures": len(self.required_failures),
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "check_results": [c.to_dict() for c in self.check_results],
            "metadata": self.metadata,
        }


class CIVerifierError(Exception):
    """Exception raised for CI verifier errors."""

    def __init__(
        self,
        message: str,
        verification_id: Optional[str] = None,
        check_name: Optional[str] = None,
    ):
        self.verification_id = verification_id
        self.check_name = check_name
        super().__init__(message)


class CIVerifierStats:
    """Statistics about CI verification operations."""

    def __init__(self) -> None:
        self.total_verifications: int = 0
        self.passed_verifications: int = 0
        self.failed_verifications: int = 0
        self.total_checks_run: int = 0
        self.checks_passed: int = 0
        self.checks_failed: int = 0
        self.average_duration: float = 0.0
        self.last_verification_at: Optional[datetime] = None
        self.started_at: datetime = datetime.utcnow()

    def update(self, result: VerificationResult) -> None:
        """Update statistics with a verification result."""
        self.total_verifications += 1
        self.total_checks_run += result.total_checks
        self.checks_passed += len(result.passed_checks)
        self.checks_failed += len(result.failed_checks)
        self.last_verification_at = datetime.utcnow()

        if result.passed:
            self.passed_verifications += 1
        else:
            self.failed_verifications += 1

        # Update average duration
        if result.duration_seconds:
            total = self.total_verifications
            current_avg = self.average_duration
            self.average_duration = (
                (current_avg * (total - 1) + result.duration_seconds) / total
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total_verifications": self.total_verifications,
            "passed_verifications": self.passed_verifications,
            "failed_verifications": self.failed_verifications,
            "pass_rate": (
                self.passed_verifications / self.total_verifications
                if self.total_verifications > 0
                else 0.0
            ),
            "total_checks_run": self.total_checks_run,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "average_duration": self.average_duration,
            "last_verification_at": (
                self.last_verification_at.isoformat()
                if self.last_verification_at
                else None
            ),
            "started_at": self.started_at.isoformat(),
        }


# Default check definitions
DEFAULT_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        name="pytest",
        check_type=CheckType.TEST,
        command=["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
        timeout_seconds=300,
        required=True,
    ),
    CheckDefinition(
        name="ruff",
        check_type=CheckType.LINT,
        command=["python", "-m", "ruff", "check", "autoflow/"],
        timeout_seconds=60,
        required=False,
    ),
    CheckDefinition(
        name="mypy",
        check_type=CheckType.TYPE_CHECK,
        command=["python", "-m", "mypy", "autoflow/", "--ignore-missing-imports"],
        timeout_seconds=120,
        required=False,
    ),
    CheckDefinition(
        name="bandit",
        check_type=CheckType.SECURITY,
        command=["python", "-m", "bandit", "-r", "autoflow/", "-f", "json"],
        timeout_seconds=60,
        required=True,
    ),
]


class CIVerifier:
    """
    CI verification orchestrator.

    The CIVerifier runs CI checks and gates to verify code quality
    before commits. It supports running individual checks or all
    checks together, with configurable timeouts and parallelism.

    Key features:
    - Run predefined or custom CI checks
    - Parallel check execution
    - Timeout handling for individual checks
    - Aggregated results with pass/fail status
    - Statistics tracking for monitoring

    Example:
        >>> from autoflow.ci.verifier import CIVerifier
        >>>
        >>> verifier = CIVerifier()
        >>> verifier.register_check(
        ...     "pytest",
        ...     command=["python", "-m", "pytest", "tests/"],
        ...     check_type=CheckType.TEST
        ... )
        >>>
        >>> result = await verifier.run_all_checks(workdir="/path/to/project")
        >>>
        >>> if result.passed:
        ...     print("All checks passed!")
        ... else:
        ...     for check in result.failed_checks:
        ...         print(f"Failed: {check.name} - {check.error}")

    Attributes:
        checks: Dictionary of registered check definitions
        default_timeout: Default timeout for checks
        parallel: Whether to run checks in parallel
        stats: Verification statistics
    """

    DEFAULT_TIMEOUT = 300
    DEFAULT_PARALLEL = True

    def __init__(
        self,
        checks: Optional[list[CheckDefinition]] = None,
        default_timeout: Optional[int] = None,
        parallel: Optional[bool] = None,
    ):
        """
        Initialize the CI verifier.

        Args:
            checks: Optional list of check definitions
            default_timeout: Default timeout in seconds
            parallel: Whether to run checks in parallel by default
        """
        self._checks: dict[str, CheckDefinition] = {}
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT
        self._parallel = parallel if parallel is not None else self.DEFAULT_PARALLEL
        self._stats = CIVerifierStats()
        self._active_verifications: dict[str, VerificationResult] = {}

        # Register default or provided checks
        for check in checks or DEFAULT_CHECKS:
            self._checks[check.name] = check

    @property
    def stats(self) -> CIVerifierStats:
        """Get verification statistics."""
        return self._stats

    @property
    def default_timeout(self) -> int:
        """Get default timeout."""
        return self._default_timeout

    @property
    def check_names(self) -> list[str]:
        """Get list of registered check names."""
        return list(self._checks.keys())

    def register_check(
        self,
        name: str,
        command: Union[str, list[str]],
        check_type: CheckType = CheckType.CUSTOM,
        timeout_seconds: Optional[int] = None,
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[dict[str, str]] = None,
        expected_exit_codes: Optional[list[int]] = None,
        enabled: bool = True,
        required: bool = True,
    ) -> None:
        """
        Register a CI check.

        Args:
            name: Unique name for this check
            command: Command to execute
            check_type: Type of check
            timeout_seconds: Timeout override
            cwd: Working directory override
            env: Environment variables
            expected_exit_codes: Success exit codes
            enabled: Whether check is enabled
            required: Whether check must pass
        """
        check = CheckDefinition(
            name=name,
            check_type=check_type,
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds or self._default_timeout,
            env=env,
            expected_exit_codes=expected_exit_codes or [0],
            enabled=enabled,
            required=required,
        )
        self._checks[name] = check

    def unregister_check(self, name: str) -> bool:
        """
        Unregister a CI check.

        Args:
            name: Name of check to remove

        Returns:
            True if check was removed, False if not found
        """
        if name in self._checks:
            del self._checks[name]
            return True
        return False

    def get_check(self, name: str) -> Optional[CheckDefinition]:
        """
        Get a check definition by name.

        Args:
            name: Check name

        Returns:
            CheckDefinition if found, None otherwise
        """
        return self._checks.get(name)

    def enable_check(self, name: str) -> bool:
        """
        Enable a check.

        Args:
            name: Check name

        Returns:
            True if check was enabled, False if not found
        """
        check = self._checks.get(name)
        if check:
            check.enabled = True
            return True
        return False

    def disable_check(self, name: str) -> bool:
        """
        Disable a check.

        Args:
            name: Check name

        Returns:
            True if check was disabled, False if not found
        """
        check = self._checks.get(name)
        if check:
            check.enabled = False
            return True
        return False

    async def run_check(
        self,
        name: str,
        workdir: Optional[Union[str, Path]] = None,
        timeout_override: Optional[int] = None,
    ) -> CheckResult:
        """
        Run a single CI check.

        Args:
            name: Name of check to run
            workdir: Working directory override
            timeout_override: Timeout override in seconds

        Returns:
            CheckResult with check status and output

        Raises:
            CIVerifierError: If check is not found
        """
        check_def = self._checks.get(name)
        if check_def is None:
            raise CIVerifierError(f"Check not found: {name}", check_name=name)

        if not check_def.enabled:
            result = CheckResult(
                check_type=check_def.check_type,
                name=name,
                status=CheckStatus.SKIPPED,
                metadata={"required": check_def.required, "reason": "disabled"},
            )
            return result

        result = CheckResult(
            check_type=check_def.check_type,
            name=name,
            metadata={"required": check_def.required},
        )
        result.mark_started()

        try:
            # Determine working directory
            cwd = Path(workdir or check_def.cwd or Path.cwd())
            timeout = timeout_override or check_def.timeout_seconds

            # Build command
            command = check_def.command
            if isinstance(command, str):
                command = [command]

            # Run the check
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=check_def.env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                output = stdout.decode("utf-8", errors="replace")
                error = stderr.decode("utf-8", errors="replace")
                exit_code = process.returncode

                # Determine status based on exit code
                if exit_code in check_def.expected_exit_codes:
                    status = CheckStatus.PASSED
                else:
                    status = CheckStatus.FAILED

                result.mark_complete(
                    status=status,
                    output=output,
                    error=error,
                    exit_code=exit_code,
                )

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                result.mark_complete(
                    status=CheckStatus.TIMEOUT,
                    error=f"Check timed out after {timeout} seconds",
                )

        except FileNotFoundError as e:
            result.mark_complete(
                status=CheckStatus.ERROR,
                error=f"Command not found: {e}",
            )
        except Exception as e:
            result.mark_complete(
                status=CheckStatus.ERROR,
                error=f"Check failed with error: {str(e)}",
            )

        return result

    async def run_checks(
        self,
        names: list[str],
        workdir: Optional[Union[str, Path]] = None,
        parallel: Optional[bool] = None,
    ) -> list[CheckResult]:
        """
        Run multiple CI checks.

        Args:
            names: Names of checks to run
            workdir: Working directory for all checks
            parallel: Whether to run in parallel (overrides default)

        Returns:
            List of CheckResult objects
        """
        use_parallel = parallel if parallel is not None else self._parallel

        if use_parallel:
            tasks = [
                self.run_check(name, workdir=workdir)
                for name in names
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to error results
            final_results: list[CheckResult] = []
            for name, result in zip(names, results):
                if isinstance(result, Exception):
                    error_result = CheckResult(
                        name=name,
                        status=CheckStatus.ERROR,
                        error=str(result),
                    )
                    final_results.append(error_result)
                else:
                    final_results.append(result)
            return final_results
        else:
            results = []
            for name in names:
                result = await self.run_check(name, workdir=workdir)
                results.append(result)
            return results

    async def run_all_checks(
        self,
        workdir: Optional[Union[str, Path]] = None,
        parallel: Optional[bool] = None,
        include_disabled: bool = False,
        timeout_seconds: Optional[int] = None,
    ) -> VerificationResult:
        """
        Run all registered CI checks.

        This is the main entry point for running a full CI verification.
        It runs all enabled checks and aggregates the results.

        Args:
            workdir: Working directory for all checks
            parallel: Whether to run in parallel (overrides default)
            include_disabled: Whether to include disabled checks
            timeout_seconds: Overall timeout for all checks

        Returns:
            VerificationResult with aggregated results

        Example:
            >>> result = await verifier.run_all_checks(workdir="/project")
            >>> if result.passed:
            ...     print("All CI checks passed!")
            ... else:
            ...     print(f"Failed: {len(result.required_failures)} required checks")
        """
        # Create verification result
        verification = VerificationResult()
        verification.status = CheckStatus.RUNNING

        # Track active verification
        self._active_verifications[verification.verification_id] = verification

        try:
            # Get checks to run
            checks_to_run = [
                name
                for name, check in self._checks.items()
                if include_disabled or check.enabled
            ]

            if not checks_to_run:
                verification.mark_complete(
                    status=CheckStatus.SKIPPED,
                    passed=True,
                    error="No checks to run",
                )
                return verification

            # Run checks (possibly in parallel)
            use_parallel = parallel if parallel is not None else self._parallel

            if timeout_seconds:
                # Run with overall timeout
                try:
                    check_results = await asyncio.wait_for(
                        self.run_checks(checks_to_run, workdir=workdir, parallel=use_parallel),
                        timeout=timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    verification.mark_complete(
                        status=CheckStatus.TIMEOUT,
                        error=f"Verification timed out after {timeout_seconds} seconds",
                    )
                    return verification
            else:
                check_results = await self.run_checks(
                    checks_to_run,
                    workdir=workdir,
                    parallel=use_parallel,
                )

            verification.check_results = check_results

            # Determine overall pass/fail
            # Pass if no required checks failed
            required_failures = verification.required_failures
            passed = len(required_failures) == 0

            # Determine overall status
            if passed:
                status = CheckStatus.PASSED
            else:
                status = CheckStatus.FAILED

            verification.mark_complete(status=status, passed=passed)

        except Exception as e:
            verification.mark_complete(
                status=CheckStatus.ERROR,
                error=f"Verification failed: {str(e)}",
            )
        finally:
            # Remove from active verifications
            self._active_verifications.pop(verification.verification_id, None)
            # Update stats
            self._stats.update(verification)

        return verification

    def run_all_checks_sync(
        self,
        workdir: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> VerificationResult:
        """
        Synchronous wrapper for run_all_checks.

        Args:
            workdir: Working directory for all checks
            **kwargs: Additional arguments passed to run_all_checks

        Returns:
            VerificationResult with aggregated results
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.run_all_checks(workdir=workdir, **kwargs)
        )

    def get_active_verifications(self) -> list[VerificationResult]:
        """
        Get all currently active verifications.

        Returns:
            List of active VerificationResult objects
        """
        return list(self._active_verifications.values())

    def get_verification(self, verification_id: str) -> Optional[VerificationResult]:
        """
        Get a verification by ID.

        Args:
            verification_id: Verification ID to look up

        Returns:
            VerificationResult if found, None otherwise
        """
        return self._active_verifications.get(verification_id)

    async def cancel_verification(self, verification_id: str) -> bool:
        """
        Cancel an active verification.

        Args:
            verification_id: Verification ID to cancel

        Returns:
            True if verification was cancelled, False if not found
        """
        verification = self._active_verifications.get(verification_id)
        if verification is None:
            return False

        verification.mark_complete(
            status=CheckStatus.ERROR,
            error="Verification cancelled by user",
        )
        self._active_verifications.pop(verification_id, None)
        return True

    def __repr__(self) -> str:
        """Return string representation."""
        enabled = sum(1 for c in self._checks.values() if c.enabled)
        required = sum(1 for c in self._checks.values() if c.required)
        return (
            f"CIVerifier("
            f"checks={len(self._checks)}, "
            f"enabled={enabled}, "
            f"required={required})"
        )


def create_verifier(
    checks: Optional[list[CheckDefinition]] = None,
    add_defaults: bool = True,
    parallel: bool = True,
) -> CIVerifier:
    """
    Factory function to create a configured CI verifier.

    Args:
        checks: Optional list of check definitions
        add_defaults: Whether to add default checks
        parallel: Whether to run checks in parallel

    Returns:
        Configured CIVerifier instance

    Example:
        >>> verifier = create_verifier(parallel=True)
        >>> result = verifier.run_all_checks_sync(workdir="/project")
        >>> print(f"Passed: {result.passed}")
    """
    all_checks: list[CheckDefinition] = []

    if add_defaults:
        all_checks.extend(DEFAULT_CHECKS)

    if checks:
        all_checks.extend(checks)

    return CIVerifier(checks=all_checks, parallel=parallel)
