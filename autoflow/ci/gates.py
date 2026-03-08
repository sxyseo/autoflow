"""
Autoflow CI Gate Definitions

Provides specialized gate classes for different types of CI checks.
Each gate encapsulates the configuration and execution logic for
a specific category of checks (tests, linting, security).

These gates integrate with CIVerifier and provide higher-level
abstractions for common CI workflows.

Usage:
    from autoflow.ci.gates import TestGate, LintGate, SecurityGate, SymphonyCheckpointGate

    # Create individual gates
    test_gate = TestGate()
    lint_gate = LintGate()
    security_gate = SecurityGate()

    # Run a single gate
    result = await test_gate.run(workdir="/path/to/project")

    # Wrap a gate with Symphony checkpoint integration
    checkpoint_gate = SymphonyCheckpointGate(
        wrapped_gate=test_gate,
        checkpoint_name="code-review",
        require_approval=True
    )

    # Run all gates
    from autoflow.ci.gates import GateRunner
    runner = GateRunner()
    result = await runner.run_all(workdir="/path/to/project")
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from autoflow.ci.verifier import (
    CheckDefinition,
    CheckResult,
    CheckStatus,
    CheckType,
    CIVerifier,
    VerificationResult,
)

# Optional Symphony integration
try:
    from autoflow.skills.symphony_bridge import SymphonyBridge
    SYMPHONY_AVAILABLE = True
except ImportError:
    SYMPHONY_AVAILABLE = False
    SymphonyBridge = None  # type: ignore


class GateStatus(str, Enum):
    """Status of a CI gate."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    WARNING = "warning"  # Passed but with warnings


class GateSeverity(str, Enum):
    """Severity level for gate configuration."""

    REQUIRED = "required"  # Must pass for overall success
    OPTIONAL = "optional"  # Nice to have, won't block
    WARNING = "warning"  # Will warn but not fail


@dataclass
class GateConfig:
    """
    Configuration for a CI gate.

    Attributes:
        enabled: Whether the gate is enabled
        severity: Gate severity level
        timeout_seconds: Timeout for gate execution
        fail_fast: Stop on first failure
        parallel: Run checks in parallel
        continue_on_error: Continue even if gate fails
    """

    enabled: bool = True
    severity: GateSeverity = GateSeverity.REQUIRED
    timeout_seconds: int = 300
    fail_fast: bool = False
    parallel: bool = True
    continue_on_error: bool = False


@dataclass
class GateResult:
    """
    Result from running a CI gate.

    Attributes:
        gate_name: Name of the gate
        gate_type: Type of gate (test, lint, security)
        status: Gate status
        checks: Individual check results
        passed: Whether gate passed
        required: Whether gate was required
        started_at: When gate started
        completed_at: When gate completed
        duration_seconds: Total duration
        summary: Human-readable summary
        error: Error message if any
        metadata: Additional metadata
    """

    gate_name: str
    gate_type: str
    status: GateStatus = GateStatus.PENDING
    checks: list[CheckResult] = field(default_factory=list)
    passed: bool = False
    required: bool = True
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    summary: str = ""
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_checks(self) -> int:
        """Get total number of checks."""
        return len(self.checks)

    @property
    def passed_checks(self) -> list[CheckResult]:
        """Get passed checks."""
        return [c for c in self.checks if c.passed]

    @property
    def failed_checks(self) -> list[CheckResult]:
        """Get failed checks."""
        return [c for c in self.checks if c.failed]

    @property
    def skipped_checks(self) -> list[CheckResult]:
        """Get skipped checks."""
        return [c for c in self.checks if c.status == CheckStatus.SKIPPED]

    def mark_started(self) -> None:
        """Mark the gate as started."""
        self.status = GateStatus.RUNNING
        self.started_at = datetime.utcnow()

    def mark_complete(
        self,
        status: GateStatus,
        passed: bool = False,
        summary: str = "",
        error: Optional[str] = None,
    ) -> None:
        """
        Mark the gate as complete.

        Args:
            status: Final gate status
            passed: Whether gate passed
            summary: Human-readable summary
            error: Error message if any
        """
        self.status = status
        self.passed = passed
        self.summary = summary
        self.error = error
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "gate_name": self.gate_name,
            "gate_type": self.gate_type,
            "status": self.status.value,
            "passed": self.passed,
            "required": self.required,
            "total_checks": self.total_checks,
            "passed_count": len(self.passed_checks),
            "failed_count": len(self.failed_checks),
            "skipped_count": len(self.skipped_checks),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "summary": self.summary,
            "error": self.error,
            "checks": [c.to_dict() for c in self.checks],
            "metadata": self.metadata,
        }


class BaseGate(ABC):
    """
    Abstract base class for CI gates.

    Gates encapsulate related CI checks and provide a unified interface
    for running them. Each gate type (test, lint, security) has its own
    implementation with appropriate default checks and configuration.
    """

    gate_type: str = "base"
    gate_name: str = "base"

    # Default check definitions for this gate type
    default_checks: list[CheckDefinition] = []

    def __init__(
        self,
        config: Optional[GateConfig] = None,
        checks: Optional[list[CheckDefinition]] = None,
        workdir: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize the gate.

        Args:
            config: Gate configuration
            checks: Custom check definitions (overrides defaults)
            workdir: Default working directory
        """
        self._config = config or GateConfig()
        self._workdir = Path(workdir) if workdir else None
        self._verifier = CIVerifier(parallel=self._config.parallel)

        # Register checks
        self._checks = checks if checks is not None else self.default_checks
        for check in self._checks:
            self._verifier.register_check(
                name=check.name,
                command=check.command,
                check_type=check.check_type,
                timeout_seconds=check.timeout_seconds,
                cwd=check.cwd or self._workdir,
                env=check.env,
                expected_exit_codes=check.expected_exit_codes,
                enabled=check.enabled and self._config.enabled,
                required=check.required,
            )

    @property
    def config(self) -> GateConfig:
        """Get gate configuration."""
        return self._config

    @property
    def check_names(self) -> list[str]:
        """Get list of check names."""
        return self._verifier.check_names

    @property
    def is_enabled(self) -> bool:
        """Check if gate is enabled."""
        return self._config.enabled

    @property
    def is_required(self) -> bool:
        """Check if gate is required."""
        return self._config.severity == GateSeverity.REQUIRED

    def add_check(
        self,
        name: str,
        command: Union[str, list[str]],
        timeout_seconds: Optional[int] = None,
        required: bool = True,
        enabled: bool = True,
    ) -> None:
        """
        Add a custom check to the gate.

        Args:
            name: Check name
            command: Command to run
            timeout_seconds: Timeout override
            required: Whether check is required
            enabled: Whether check is enabled
        """
        self._verifier.register_check(
            name=name,
            command=command,
            check_type=self._get_check_type(),
            timeout_seconds=timeout_seconds or self._config.timeout_seconds,
            cwd=self._workdir,
            enabled=enabled and self._config.enabled,
            required=required,
        )

    def remove_check(self, name: str) -> bool:
        """
        Remove a check from the gate.

        Args:
            name: Check name to remove

        Returns:
            True if removed, False if not found
        """
        return self._verifier.unregister_check(name)

    def enable_check(self, name: str) -> bool:
        """Enable a specific check."""
        return self._verifier.enable_check(name)

    def disable_check(self, name: str) -> bool:
        """Disable a specific check."""
        return self._verifier.disable_check(name)

    @abstractmethod
    def _get_check_type(self) -> CheckType:
        """Get the check type for this gate."""
        pass

    @abstractmethod
    def _create_result(self) -> GateResult:
        """Create a gate result object."""
        pass

    @abstractmethod
    def _generate_summary(self, result: GateResult) -> str:
        """Generate a human-readable summary."""
        pass

    async def run(
        self,
        workdir: Optional[Union[str, Path]] = None,
        timeout_override: Optional[int] = None,
    ) -> GateResult:
        """
        Run all checks in this gate.

        Args:
            workdir: Working directory override
            timeout_override: Timeout override in seconds

        Returns:
            GateResult with check results
        """
        result = self._create_result()
        result.required = self.is_required

        if not self.is_enabled:
            result.mark_complete(
                status=GateStatus.SKIPPED,
                passed=True,
                summary="Gate is disabled",
            )
            return result

        result.mark_started()
        cwd = Path(workdir) if workdir else self._workdir

        try:
            # Run verification
            timeout = timeout_override or self._config.timeout_seconds
            verification = await self._verifier.run_all_checks(
                workdir=cwd,
                parallel=self._config.parallel,
                timeout_seconds=timeout,
            )

            # Copy check results
            result.checks = verification.check_results

            # Determine gate status
            if verification.passed:
                if result.failed_checks:
                    # Non-required failures
                    status = GateStatus.WARNING
                else:
                    status = GateStatus.PASSED
                passed = True
            else:
                status = GateStatus.FAILED
                passed = False

            # Generate summary
            summary = self._generate_summary(result)
            result.mark_complete(status=status, passed=passed, summary=summary)

        except asyncio.TimeoutError:
            result.mark_complete(
                status=GateStatus.ERROR,
                error=f"Gate timed out after {timeout} seconds",
            )
        except Exception as e:
            result.mark_complete(
                status=GateStatus.ERROR,
                error=f"Gate failed with error: {str(e)}",
            )

        return result

    def run_sync(
        self,
        workdir: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> GateResult:
        """
        Synchronous wrapper for run().

        Args:
            workdir: Working directory
            **kwargs: Additional arguments

        Returns:
            GateResult
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.run(workdir=workdir, **kwargs))

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"{self.__class__.__name__}("
            f"enabled={self.is_enabled}, "
            f"required={self.is_required}, "
            f"checks={len(self.check_names)})"
        )


class TestGate(BaseGate):
    """
    Gate for running test suites.

    Runs unit tests, integration tests, and other test suites.
    Default checks include pytest for Python projects.

    Example:
        >>> gate = TestGate()
        >>> gate.add_check("pytest", ["python", "-m", "pytest", "tests/"])
        >>> result = await gate.run(workdir="/project")
        >>> if result.passed:
        ...     print("All tests passed!")
    """

    gate_type = "test"
    gate_name = "Tests"

    default_checks: list[CheckDefinition] = [
        CheckDefinition(
            name="pytest",
            check_type=CheckType.TEST,
            command=["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
            timeout_seconds=300,
            required=True,
        ),
    ]

    def _get_check_type(self) -> CheckType:
        return CheckType.TEST

    def _create_result(self) -> GateResult:
        return GateResult(
            gate_name=self.gate_name,
            gate_type=self.gate_type,
        )

    def _generate_summary(self, result: GateResult) -> str:
        total = result.total_checks
        passed = len(result.passed_checks)
        failed = len(result.failed_checks)
        skipped = len(result.skipped_checks)

        if result.passed:
            if failed > 0:
                return f"Tests passed with warnings: {passed}/{total} passed, {failed} non-required failures"
            return f"All tests passed: {passed}/{total}"
        return f"Tests failed: {passed}/{total} passed, {failed} failures, {skipped} skipped"


class LintGate(BaseGate):
    """
    Gate for running linting and code quality checks.

    Runs linters, formatters, and style checkers.
    Default checks include ruff for Python projects.

    Example:
        >>> gate = LintGate()
        >>> gate.add_check("ruff", ["python", "-m", "ruff", "check", "."])
        >>> result = await gate.run(workdir="/project")
        >>> if result.passed:
        ...     print("No linting issues!")
    """

    gate_type = "lint"
    gate_name = "Lint"

    default_checks: list[CheckDefinition] = [
        CheckDefinition(
            name="ruff",
            check_type=CheckType.LINT,
            command=["python", "-m", "ruff", "check", "autoflow/"],
            timeout_seconds=60,
            required=False,  # Lint is usually not blocking
        ),
        CheckDefinition(
            name="ruff-format-check",
            check_type=CheckType.FORMAT,
            command=["python", "-m", "ruff", "format", "--check", "autoflow/"],
            timeout_seconds=60,
            required=False,
        ),
    ]

    def _get_check_type(self) -> CheckType:
        return CheckType.LINT

    def _create_result(self) -> GateResult:
        return GateResult(
            gate_name=self.gate_name,
            gate_type=self.gate_type,
        )

    def _generate_summary(self, result: GateResult) -> str:
        total = result.total_checks
        passed = len(result.passed_checks)
        failed = len(result.failed_checks)
        skipped = len(result.skipped_checks)

        if result.passed:
            if failed > 0:
                return f"Lint passed with warnings: {passed}/{total} passed"
            return f"Lint checks passed: {passed}/{total}"
        return f"Lint failed: {passed}/{total} passed, {failed} failures"


class SecurityGate(BaseGate):
    """
    Gate for running security scans.

    Runs security scanners, vulnerability checkers, and dependency auditors.
    Default checks include bandit for Python projects.

    Example:
        >>> gate = SecurityGate()
        >>> gate.add_check("bandit", ["python", "-m", "bandit", "-r", "src/"])
        >>> result = await gate.run(workdir="/project")
        >>> if result.passed:
        ...     print("No security issues found!")
    """

    gate_type = "security"
    gate_name = "Security"

    default_checks: list[CheckDefinition] = [
        CheckDefinition(
            name="bandit",
            check_type=CheckType.SECURITY,
            command=["python", "-m", "bandit", "-r", "autoflow/", "-f", "json"],
            timeout_seconds=120,
            required=True,  # Security issues should be blocking
        ),
    ]

    def _get_check_type(self) -> CheckType:
        return CheckType.SECURITY

    def _create_result(self) -> GateResult:
        return GateResult(
            gate_name=self.gate_name,
            gate_type=self.gate_type,
        )

    def _generate_summary(self, result: GateResult) -> str:
        total = result.total_checks
        passed = len(result.passed_checks)
        failed = len(result.failed_checks)
        skipped = len(result.skipped_checks)

        if result.passed:
            return f"Security scan passed: {passed}/{total} checks passed"
        return f"Security issues found: {passed}/{total} passed, {failed} failures"


class TypeCheckGate(BaseGate):
    """
    Gate for running type checking.

    Runs static type checkers like mypy.
    """

    gate_type = "type_check"
    gate_name = "Type Check"

    default_checks: list[CheckDefinition] = [
        CheckDefinition(
            name="mypy",
            check_type=CheckType.TYPE_CHECK,
            command=["python", "-m", "mypy", "autoflow/", "--ignore-missing-imports"],
            timeout_seconds=120,
            required=False,  # Type check is usually informational
        ),
    ]

    def _get_check_type(self) -> CheckType:
        return CheckType.TYPE_CHECK

    def _create_result(self) -> GateResult:
        return GateResult(
            gate_name=self.gate_name,
            gate_type=self.gate_type,
        )

    def _generate_summary(self, result: GateResult) -> str:
        total = result.total_checks
        passed = len(result.passed_checks)
        failed = len(result.failed_checks)

        if result.passed:
            return f"Type check passed: {passed}/{total}"
        return f"Type errors found: {passed}/{total} passed, {failed} failures"


class SymphonyCheckpointGate(BaseGate):
    """
    Checkpoint-aware review gate that integrates with Symphony framework.

    This gate wraps other gates and adds Symphony checkpoint integration,
    allowing workflows to pause at review points and wait for approval.
    When Symphony is not available, it behaves as a pass-through decorator.

    Example:
        >>> from autoflow.ci.gates import TestGate, SymphonyCheckpointGate
        >>>
        >>> # Wrap a test gate with checkpoint awareness
        >>> base_gate = TestGate()
        >>> checkpoint_gate = SymphonyCheckpointGate(
        ...     wrapped_gate=base_gate,
        ...     checkpoint_name="code-review",
        ...     require_approval=True
        ... )
        >>>
        >>> # Run the gate (will pause at checkpoint if configured)
        >>> result = await checkpoint_gate.run(workdir="/project")

    Attributes:
        wrapped_gate: The underlying gate to execute
        checkpoint_name: Name for the Symphony checkpoint
        require_approval: Whether to wait for approval at checkpoint
        symphony_bridge: Optional Symphony bridge for checkpoint integration
    """

    gate_type = "symphony_checkpoint"
    gate_name = "Symphony Checkpoint"

    def __init__(
        self,
        wrapped_gate: BaseGate,
        checkpoint_name: str = "review-gate",
        require_approval: bool = True,
        symphony_bridge: Optional[SymphonyBridge] = None,
        workdir: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize the checkpoint gate.

        Args:
            wrapped_gate: The gate to wrap with checkpoint awareness
            checkpoint_name: Name for the Symphony checkpoint
            require_approval: Whether to wait for approval before continuing
            symphony_bridge: Optional Symphony bridge (uses default if not provided)
            workdir: Working directory for the gate
        """
        self._wrapped_gate = wrapped_gate
        self._checkpoint_name = checkpoint_name
        self._require_approval = require_approval
        self._symphony_bridge = symphony_bridge
        self._checkpoint_id: Optional[str] = None
        self._approval_received = False

        # Initialize base gate with minimal config
        # We delegate most operations to the wrapped gate
        super().__init__(
            config=wrapped_gate.config,
            checks=[],
            workdir=workdir,
        )

    @property
    def wrapped_gate(self) -> BaseGate:
        """Get the wrapped gate."""
        return self._wrapped_gate

    @property
    def checkpoint_name(self) -> str:
        """Get the checkpoint name."""
        return self._checkpoint_name

    @property
    def checkpoint_id(self) -> Optional[str]:
        """Get the checkpoint ID (set after checkpoint creation)."""
        return self._checkpoint_id

    @property
    def is_symphony_enabled(self) -> bool:
        """Check if Symphony integration is available."""
        return SYMPHONY_AVAILABLE and self._symphony_bridge is not None

    def _get_check_type(self) -> CheckType:
        """Get the check type (delegate to wrapped gate)."""
        return self._wrapped_gate._get_check_type()

    def _create_result(self) -> GateResult:
        """Create a gate result object."""
        result = GateResult(
            gate_name=self.gate_name,
            gate_type=self.gate_type,
        )
        # Add wrapped gate info to metadata
        result.metadata["wrapped_gate"] = self._wrapped_gate.gate_name
        result.metadata["checkpoint_name"] = self._checkpoint_name
        result.metadata["symphony_enabled"] = self.is_symphony_enabled
        return result

    def _generate_summary(self, result: GateResult) -> str:
        """Generate a human-readable summary."""
        if self.is_symphony_enabled and self._checkpoint_id:
            base_summary = self._wrapped_gate._generate_summary(result)
            return f"{base_summary} (Checkpoint: {self._checkpoint_id})"
        return self._wrapped_gate._generate_summary(result)

    async def run(
        self,
        workdir: Optional[Union[str, Path]] = None,
        timeout_override: Optional[int] = None,
    ) -> GateResult:
        """
        Run the wrapped gate with checkpoint integration.

        If Symphony is enabled and require_approval is True:
        1. Create a checkpoint before running the gate
        2. Run the wrapped gate
        3. Wait for approval at the checkpoint
        4. Continue after approval is received

        Args:
            workdir: Working directory override
            timeout_override: Timeout override in seconds

        Returns:
            GateResult with check results and checkpoint info
        """
        result = self._create_result()
        result.required = self.is_required

        if not self.is_enabled:
            result.mark_complete(
                status=GateStatus.SKIPPED,
                passed=True,
                summary="Checkpoint gate is disabled",
            )
            return result

        result.mark_started()
        cwd = Path(workdir) if workdir else self._workdir

        try:
            # Initialize Symphony bridge if needed
            if self.is_symphony_enabled and self._symphony_bridge is None:
                self._symphony_bridge = SymphonyBridge()

            # Create checkpoint if Symphony is enabled
            if self.is_symphony_enabled and self._require_approval:
                self._checkpoint_id = await self._create_checkpoint(cwd)
                result.metadata["checkpoint_id"] = self._checkpoint_id

            # Run the wrapped gate
            wrapped_result = await self._wrapped_gate.run(
                workdir=cwd,
                timeout_override=timeout_override,
            )

            # Copy wrapped gate results
            result.checks = wrapped_result.checks
            result.passed = wrapped_result.passed

            # Wait for approval if configured
            if self.is_symphony_enabled and self._require_approval and self._checkpoint_id:
                await self._wait_for_approval(cwd)

            # Determine final status
            if result.passed:
                if result.failed_checks:
                    status = GateStatus.WARNING
                else:
                    status = GateStatus.PASSED
            else:
                status = GateStatus.FAILED

            summary = self._generate_summary(result)
            result.mark_complete(status=status, passed=result.passed, summary=summary)

        except asyncio.TimeoutError:
            result.mark_complete(
                status=GateStatus.ERROR,
                error=f"Checkpoint gate timed out after {timeout_override} seconds",
            )
        except Exception as e:
            result.mark_complete(
                status=GateStatus.ERROR,
                error=f"Checkpoint gate failed with error: {str(e)}",
            )

        return result

    async def _create_checkpoint(self, workdir: Optional[Path]) -> str:
        """
        Create a Symphony checkpoint.

        Args:
            workdir: Working directory for checkpoint

        Returns:
            Checkpoint ID

        Raises:
            RuntimeError: If Symphony bridge is not available
        """
        if not self.is_symphony_enabled or self._symphony_bridge is None:
            raise RuntimeError("Symphony bridge is not available for checkpoint creation")

        # Create checkpoint via Symphony bridge
        # Note: This is a simplified implementation
        # In practice, you would call SymphonyBridge methods to create checkpoints
        checkpoint_id = f"checkpoint-{self._checkpoint_name}-{id(self)}"

        return checkpoint_id

    async def _wait_for_approval(self, workdir: Optional[Path]) -> None:
        """
        Wait for approval at the checkpoint.

        Args:
            workdir: Working directory

        Raises:
            RuntimeError: If Symphony bridge is not available
        """
        if not self.is_symphony_enabled or self._symphony_bridge is None:
            raise RuntimeError("Symphony bridge is not available for approval waiting")

        # Wait for approval via Symphony bridge
        # Note: This is a simplified implementation
        # In practice, you would call SymphonyBridge methods to wait for approval
        self._approval_received = True

    def approve_checkpoint(self) -> None:
        """
        Approve the checkpoint (external approval callback).

        This method can be called externally to approve the checkpoint
        and allow the workflow to continue.
        """
        self._approval_received = True

    def reject_checkpoint(self, reason: str = "") -> None:
        """
        Reject the checkpoint (external rejection callback).

        This method can be called externally to reject the checkpoint.

        Args:
            reason: Optional reason for rejection
        """
        self._approval_received = False
        # Note: In practice, you might want to store the rejection reason
        # and potentially update checkpoint state via Symphony bridge

    def add_check(
        self,
        name: str,
        command: Union[str, list[str]],
        timeout_seconds: Optional[int] = None,
        required: bool = True,
        enabled: bool = True,
    ) -> None:
        """Add a check to the wrapped gate."""
        self._wrapped_gate.add_check(
            name=name,
            command=command,
            timeout_seconds=timeout_seconds,
            required=required,
            enabled=enabled,
        )

    def remove_check(self, name: str) -> bool:
        """Remove a check from the wrapped gate."""
        return self._wrapped_gate.remove_check(name)

    def enable_check(self, name: str) -> bool:
        """Enable a check in the wrapped gate."""
        return self._wrapped_gate.enable_check(name)

    def disable_check(self, name: str) -> bool:
        """Disable a check in the wrapped gate."""
        return self._wrapped_gate.disable_check(name)

    @property
    def check_names(self) -> list[str]:
        """Get list of check names from wrapped gate."""
        return self._wrapped_gate.check_names

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SymphonyCheckpointGate("
            f"wrapped_gate={self._wrapped_gate.gate_name}, "
            f"checkpoint={self._checkpoint_name}, "
            f"symphony_enabled={self.is_symphony_enabled}, "
            f"require_approval={self._require_approval})"
        )


@dataclass
class GateRunnerResult:
    """
    Aggregated result from running multiple gates.

    Attributes:
        gates: Individual gate results
        status: Overall status
        passed: Whether all required gates passed
        started_at: When runner started
        completed_at: When runner completed
        duration_seconds: Total duration
    """

    gates: list[GateResult] = field(default_factory=list)
    status: GateStatus = GateStatus.PENDING
    passed: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    @property
    def total_gates(self) -> int:
        """Get total number of gates."""
        return len(self.gates)

    @property
    def passed_gates(self) -> list[GateResult]:
        """Get passed gates."""
        return [g for g in self.gates if g.passed]

    @property
    def failed_gates(self) -> list[GateResult]:
        """Get failed gates."""
        return [g for g in self.gates if not g.passed]

    @property
    def required_failures(self) -> list[GateResult]:
        """Get failed required gates."""
        return [g for g in self.failed_gates if g.required]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "passed": self.passed,
            "total_gates": self.total_gates,
            "passed_count": len(self.passed_gates),
            "failed_count": len(self.failed_gates),
            "required_failures": len(self.required_failures),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "gates": [g.to_dict() for g in self.gates],
        }


class GateRunner:
    """
    Orchestrates running multiple CI gates.

    The GateRunner manages a collection of gates and provides
    methods to run them individually or all together.

    Example:
        >>> runner = GateRunner()
        >>> runner.add_gate(TestGate())
        >>> runner.add_gate(LintGate())
        >>> runner.add_gate(SecurityGate())
        >>>
        >>> result = await runner.run_all(workdir="/project")
        >>> if result.passed:
        ...     print("All gates passed!")
        ... else:
        ...     for gate in result.failed_gates:
        ...         print(f"Failed: {gate.gate_name}")
    """

    def __init__(
        self,
        parallel: bool = True,
        fail_fast: bool = False,
    ):
        """
        Initialize the gate runner.

        Args:
            parallel: Run gates in parallel
            fail_fast: Stop on first required failure
        """
        self._gates: dict[str, BaseGate] = {}
        self._parallel = parallel
        self._fail_fast = fail_fast

    @property
    def gate_names(self) -> list[str]:
        """Get list of gate names."""
        return list(self._gates.keys())

    def add_gate(self, gate: BaseGate) -> None:
        """
        Add a gate to the runner.

        Args:
            gate: Gate to add
        """
        self._gates[gate.gate_name] = gate

    def remove_gate(self, name: str) -> bool:
        """
        Remove a gate from the runner.

        Args:
            name: Gate name to remove

        Returns:
            True if removed, False if not found
        """
        if name in self._gates:
            del self._gates[name]
            return True
        return False

    def get_gate(self, name: str) -> Optional[BaseGate]:
        """
        Get a gate by name.

        Args:
            name: Gate name

        Returns:
            Gate if found, None otherwise
        """
        return self._gates.get(name)

    async def run_gate(
        self,
        name: str,
        workdir: Optional[Union[str, Path]] = None,
    ) -> GateResult:
        """
        Run a single gate.

        Args:
            name: Gate name
            workdir: Working directory

        Returns:
            GateResult

        Raises:
            ValueError: If gate not found
        """
        gate = self._gates.get(name)
        if gate is None:
            raise ValueError(f"Gate not found: {name}")

        return await gate.run(workdir=workdir)

    async def run_all(
        self,
        workdir: Optional[Union[str, Path]] = None,
        parallel: Optional[bool] = None,
    ) -> GateRunnerResult:
        """
        Run all registered gates.

        Args:
            workdir: Working directory
            parallel: Override parallel setting

        Returns:
            GateRunnerResult with all gate results
        """
        result = GateRunnerResult()
        result.started_at = datetime.utcnow()
        result.status = GateStatus.RUNNING

        use_parallel = parallel if parallel is not None else self._parallel

        if use_parallel:
            # Run all gates in parallel
            tasks = [
                gate.run(workdir=workdir)
                for gate in self._gates.values()
            ]
            gate_results = await asyncio.gather(*tasks, return_exceptions=True)

            for gate_name, gate_result in zip(self._gates.keys(), gate_results):
                if isinstance(gate_result, Exception):
                    # Create error result
                    error_result = GateResult(
                        gate_name=gate_name,
                        gate_type="unknown",
                        status=GateStatus.ERROR,
                        error=str(gate_result),
                    )
                    result.gates.append(error_result)
                else:
                    result.gates.append(gate_result)

                # Check fail-fast
                if self._fail_fast:
                    last_result = result.gates[-1]
                    if not last_result.passed and last_result.required:
                        break
        else:
            # Run gates sequentially
            for gate in self._gates.values():
                gate_result = await gate.run(workdir=workdir)
                result.gates.append(gate_result)

                # Check fail-fast
                if self._fail_fast and not gate_result.passed and gate_result.required:
                    break

        # Determine overall status
        result.completed_at = datetime.utcnow()
        result.duration_seconds = (
            result.completed_at - result.started_at
        ).total_seconds()

        # Pass if no required gates failed
        if len(result.required_failures) == 0:
            result.passed = True
            result.status = GateStatus.PASSED
        else:
            result.passed = False
            result.status = GateStatus.FAILED

        return result

    def run_all_sync(
        self,
        workdir: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> GateRunnerResult:
        """
        Synchronous wrapper for run_all().

        Args:
            workdir: Working directory
            **kwargs: Additional arguments

        Returns:
            GateRunnerResult
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.run_all(workdir=workdir, **kwargs))

    def __repr__(self) -> str:
        """Return string representation."""
        return f"GateRunner(gates={len(self._gates)}, parallel={self._parallel})"


def create_default_gates(
    test: bool = True,
    lint: bool = True,
    security: bool = True,
    type_check: bool = False,
    workdir: Optional[Union[str, Path]] = None,
) -> list[BaseGate]:
    """
    Create a list of default gates.

    Args:
        test: Include test gate
        lint: Include lint gate
        security: Include security gate
        type_check: Include type check gate
        workdir: Working directory for all gates

    Returns:
        List of configured gates
    """
    gates: list[BaseGate] = []

    if test:
        gates.append(TestGate(workdir=workdir))
    if lint:
        gates.append(LintGate(workdir=workdir))
    if security:
        gates.append(SecurityGate(workdir=workdir))
    if type_check:
        gates.append(TypeCheckGate(workdir=workdir))

    return gates


def create_default_runner(
    test: bool = True,
    lint: bool = True,
    security: bool = True,
    type_check: bool = False,
    parallel: bool = True,
    workdir: Optional[Union[str, Path]] = None,
) -> GateRunner:
    """
    Create a gate runner with default gates.

    Args:
        test: Include test gate
        lint: Include lint gate
        security: Include security gate
        type_check: Include type check gate
        parallel: Run gates in parallel
        workdir: Working directory for all gates

    Returns:
        Configured GateRunner

    Example:
        >>> runner = create_default_runner()
        >>> result = runner.run_all_sync(workdir="/project")
        >>> print(f"All gates passed: {result.passed}")
    """
    runner = GateRunner(parallel=parallel)

    for gate in create_default_gates(
        test=test,
        lint=lint,
        security=security,
        type_check=type_check,
        workdir=workdir,
    ):
        runner.add_gate(gate)

    return runner
