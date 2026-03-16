"""
Unit Tests for CI Gates

Tests the CIVerifier, CheckResult, CheckDefinition, and gate classes
for running CI checks and verification gates.

These tests mock subprocess execution to avoid requiring actual
CI tools to be installed in the test environment.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.ci import (
    CheckDefinition,
    CheckResult,
    CheckStatus,
    CheckType,
    CIVerifier,
    CIVerifierError,
    CIVerifierStats,
    GateConfig,
    GateResult,
    GateRunner,
    GateRunnerResult,
    GateSeverity,
    GateStatus,
    LintGate,
    SecurityGate,
    TestGate,
    TypeCheckGate,
    VerificationResult,
    create_default_gates,
    create_default_runner,
    create_verifier,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_workdir(tmp_path: Path) -> Path:
    """Create a temporary working directory."""
    workdir = tmp_path / "project"
    workdir.mkdir()
    return workdir


@pytest.fixture
def mock_subprocess_success() -> MagicMock:
    """Mock subprocess that returns success."""
    mock = MagicMock()
    mock.returncode = 0
    mock.communicate = AsyncMock(return_value=(b"Success output", b""))
    return mock


@pytest.fixture
def mock_subprocess_failure() -> MagicMock:
    """Mock subprocess that returns failure."""
    mock = MagicMock()
    mock.returncode = 1
    mock.communicate = AsyncMock(return_value=(b"", b"Error output"))
    return mock


@pytest.fixture
def verifier() -> CIVerifier:
    """Create a basic CIVerifier instance for testing."""
    return CIVerifier(checks=[], parallel=True)


@pytest.fixture
def configured_verifier() -> CIVerifier:
    """Create a CIVerifier with some pre-configured checks."""
    return CIVerifier(
        checks=[
            CheckDefinition(
                name="test-check",
                check_type=CheckType.TEST,
                command=["echo", "test"],
                timeout_seconds=10,
                required=True,
            ),
            CheckDefinition(
                name="lint-check",
                check_type=CheckType.LINT,
                command=["echo", "lint"],
                timeout_seconds=10,
                required=False,
            ),
        ],
        parallel=True,
    )


# ============================================================================
# CheckResult Tests
# ============================================================================


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_result_init_defaults(self) -> None:
        """Test result initialization with defaults."""
        result = CheckResult()

        assert result.status == CheckStatus.PENDING
        assert result.name == ""
        assert result.output == ""
        assert result.error == ""
        assert result.exit_code is None

    def test_result_passed_property(self) -> None:
        """Test passed property."""
        result = CheckResult(status=CheckStatus.PASSED)
        assert result.passed is True

        result = CheckResult(status=CheckStatus.FAILED)
        assert result.passed is False

    def test_result_failed_property(self) -> None:
        """Test failed property."""
        result = CheckResult(status=CheckStatus.FAILED)
        assert result.failed is True

        result = CheckResult(status=CheckStatus.ERROR)
        assert result.failed is True

        result = CheckResult(status=CheckStatus.TIMEOUT)
        assert result.failed is True

        result = CheckResult(status=CheckStatus.PASSED)
        assert result.failed is False

    def test_result_mark_started(self) -> None:
        """Test mark_started method."""
        result = CheckResult()
        result.mark_started()

        assert result.status == CheckStatus.RUNNING
        assert result.started_at is not None

    def test_result_mark_complete(self) -> None:
        """Test mark_complete method."""
        result = CheckResult()
        result.mark_started()
        result.mark_complete(
            status=CheckStatus.PASSED,
            output="Test output",
            error="",
            exit_code=0,
        )

        assert result.status == CheckStatus.PASSED
        assert result.output == "Test output"
        assert result.exit_code == 0
        assert result.completed_at is not None
        assert result.duration_seconds is not None

    def test_result_to_dict(self) -> None:
        """Test to_dict method."""
        result = CheckResult(
            check_type=CheckType.TEST,
            name="pytest",
            status=CheckStatus.PASSED,
            exit_code=0,
        )
        data = result.to_dict()

        assert data["check_type"] == "test"
        assert data["name"] == "pytest"
        assert data["status"] == "passed"
        assert data["passed"] is True
        assert data["exit_code"] == 0


# ============================================================================
# CheckDefinition Tests
# ============================================================================


class TestCheckDefinition:
    """Tests for CheckDefinition dataclass."""

    def test_definition_init_minimal(self) -> None:
        """Test definition initialization with minimal fields."""
        definition = CheckDefinition(
            name="test",
            check_type=CheckType.TEST,
            command=["echo", "test"],
        )

        assert definition.name == "test"
        assert definition.check_type == CheckType.TEST
        assert definition.command == ["echo", "test"]
        assert definition.timeout_seconds == 300
        assert definition.enabled is True
        assert definition.required is True

    def test_definition_command_string_conversion(self) -> None:
        """Test that string command is converted to list."""
        definition = CheckDefinition(
            name="test",
            check_type=CheckType.CUSTOM,
            command="echo test",
        )

        assert definition.command == ["echo test"]

    def test_definition_full_config(self) -> None:
        """Test definition with full configuration."""
        definition = CheckDefinition(
            name="custom-check",
            check_type=CheckType.CUSTOM,
            command=["python", "-m", "custom"],
            cwd="/project",
            timeout_seconds=60,
            env={"VAR": "value"},
            expected_exit_codes=[0, 2],
            enabled=False,
            required=False,
        )

        assert definition.name == "custom-check"
        assert definition.cwd == "/project"
        assert definition.timeout_seconds == 60
        assert definition.env == {"VAR": "value"}
        assert definition.expected_exit_codes == [0, 2]
        assert definition.enabled is False
        assert definition.required is False


# ============================================================================
# VerificationResult Tests
# ============================================================================


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_result_init(self) -> None:
        """Test verification result initialization."""
        result = VerificationResult()

        assert result.status == CheckStatus.PENDING
        assert result.passed is False
        assert result.check_results == []

    def test_result_properties(self) -> None:
        """Test verification result properties."""
        result = VerificationResult()
        result.check_results = [
            CheckResult(name="pass1", status=CheckStatus.PASSED),
            CheckResult(name="pass2", status=CheckStatus.PASSED),
            CheckResult(name="fail1", status=CheckStatus.FAILED),
            CheckResult(name="skip1", status=CheckStatus.SKIPPED),
        ]

        assert result.total_checks == 4
        assert len(result.passed_checks) == 2
        assert len(result.failed_checks) == 1
        assert len(result.skipped_checks) == 1

    def test_result_required_failures(self) -> None:
        """Test required_failures property."""
        result = VerificationResult()
        result.check_results = [
            CheckResult(
                name="required-fail",
                status=CheckStatus.FAILED,
                metadata={"required": True},
            ),
            CheckResult(
                name="optional-fail",
                status=CheckStatus.FAILED,
                metadata={"required": False},
            ),
        ]

        assert len(result.failed_checks) == 2
        assert len(result.required_failures) == 1
        assert result.required_failures[0].name == "required-fail"

    def test_result_mark_complete(self) -> None:
        """Test mark_complete method."""
        result = VerificationResult()
        result.mark_complete(status=CheckStatus.PASSED, passed=True)

        assert result.status == CheckStatus.PASSED
        assert result.passed is True
        assert result.completed_at is not None
        assert result.duration_seconds is not None

    def test_result_to_dict(self) -> None:
        """Test to_dict method."""
        result = VerificationResult(
            verification_id="test-123",
            status=CheckStatus.PASSED,
            passed=True,
        )
        data = result.to_dict()

        assert data["verification_id"] == "test-123"
        assert data["status"] == "passed"
        assert data["passed"] is True


# ============================================================================
# CIVerifierStats Tests
# ============================================================================


class TestCIVerifierStats:
    """Tests for CIVerifierStats class."""

    def test_stats_init(self) -> None:
        """Test stats initialization."""
        stats = CIVerifierStats()

        assert stats.total_verifications == 0
        assert stats.passed_verifications == 0
        assert stats.failed_verifications == 0

    def test_stats_update(self) -> None:
        """Test stats update method."""
        stats = CIVerifierStats()

        result = VerificationResult(
            passed=True,
            check_results=[
                CheckResult(name="pass1", status=CheckStatus.PASSED),
                CheckResult(name="pass2", status=CheckStatus.PASSED),
            ],
            duration_seconds=5.0,
        )
        stats.update(result)

        assert stats.total_verifications == 1
        assert stats.passed_verifications == 1
        assert stats.total_checks_run == 2
        assert stats.checks_passed == 2
        assert stats.average_duration == 5.0

    def test_stats_to_dict(self) -> None:
        """Test stats to_dict method."""
        stats = CIVerifierStats()
        stats.total_verifications = 10
        stats.passed_verifications = 8
        stats.failed_verifications = 2

        data = stats.to_dict()

        assert data["total_verifications"] == 10
        assert data["passed_verifications"] == 8
        assert data["failed_verifications"] == 2
        assert data["pass_rate"] == 0.8


# ============================================================================
# CIVerifier Initialization Tests
# ============================================================================


class TestCIVerifierInit:
    """Tests for CIVerifier initialization."""

    def test_init_empty(self) -> None:
        """Test empty verifier initialization."""
        verifier = CIVerifier(checks=[])

        assert len(verifier.check_names) == 0
        assert verifier.default_timeout == 300
        assert verifier._parallel is True

    def test_init_with_checks(self) -> None:
        """Test initialization with checks."""
        verifier = CIVerifier(
            checks=[
                CheckDefinition(
                    name="pytest",
                    check_type=CheckType.TEST,
                    command=["pytest"],
                ),
            ],
        )

        assert len(verifier.check_names) == 1
        assert "pytest" in verifier.check_names

    def test_init_with_custom_timeout(self) -> None:
        """Test initialization with custom timeout."""
        verifier = CIVerifier(checks=[], default_timeout=600)

        assert verifier.default_timeout == 600

    def test_init_sequential_mode(self) -> None:
        """Test initialization in sequential mode."""
        verifier = CIVerifier(checks=[], parallel=False)

        assert verifier._parallel is False


# ============================================================================
# CIVerifier Check Management Tests
# ============================================================================


class TestCIVerifierCheckManagement:
    """Tests for CIVerifier check management methods."""

    def test_register_check(self, verifier: CIVerifier) -> None:
        """Test registering a check."""
        verifier.register_check(
            name="pytest",
            command=["python", "-m", "pytest"],
            check_type=CheckType.TEST,
        )

        assert "pytest" in verifier.check_names
        check = verifier.get_check("pytest")
        assert check is not None
        assert check.check_type == CheckType.TEST

    def test_unregister_check(self, verifier: CIVerifier) -> None:
        """Test unregistering a check."""
        verifier.register_check(
            name="pytest",
            command=["pytest"],
            check_type=CheckType.TEST,
        )

        result = verifier.unregister_check("pytest")
        assert result is True
        assert "pytest" not in verifier.check_names

    def test_unregister_check_not_found(self, verifier: CIVerifier) -> None:
        """Test unregistering a non-existent check."""
        result = verifier.unregister_check("nonexistent")
        assert result is False

    def test_enable_check(self, verifier: CIVerifier) -> None:
        """Test enabling a check."""
        verifier.register_check(
            name="pytest",
            command=["pytest"],
            check_type=CheckType.TEST,
            enabled=False,
        )

        result = verifier.enable_check("pytest")
        assert result is True
        assert verifier.get_check("pytest").enabled is True

    def test_disable_check(self, verifier: CIVerifier) -> None:
        """Test disabling a check."""
        verifier.register_check(
            name="pytest",
            command=["pytest"],
            check_type=CheckType.TEST,
        )

        result = verifier.disable_check("pytest")
        assert result is True
        assert verifier.get_check("pytest").enabled is False

    def test_enable_check_not_found(self, verifier: CIVerifier) -> None:
        """Test enabling a non-existent check."""
        result = verifier.enable_check("nonexistent")
        assert result is False


# ============================================================================
# CIVerifier Run Check Tests
# ============================================================================


class TestCIVerifierRunCheck:
    """Tests for CIVerifier.run_check method."""

    @pytest.mark.asyncio
    async def test_run_check_disabled(self, verifier: CIVerifier) -> None:
        """Test running a disabled check."""
        verifier.register_check(
            name="disabled-check",
            command=["pytest"],
            check_type=CheckType.TEST,
            enabled=False,
        )

        result = await verifier.run_check("disabled-check")

        assert result.status == CheckStatus.SKIPPED
        assert result.metadata.get("reason") == "disabled"

    @pytest.mark.asyncio
    async def test_run_check_not_found(self, verifier: CIVerifier) -> None:
        """Test running a non-existent check."""
        with pytest.raises(CIVerifierError) as exc_info:
            await verifier.run_check("nonexistent")

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_check_success(
        self,
        verifier: CIVerifier,
        mock_subprocess_success: MagicMock,
    ) -> None:
        """Test running a check that succeeds."""
        verifier.register_check(
            name="pytest",
            command=["python", "-m", "pytest"],
            check_type=CheckType.TEST,
        )

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_subprocess_success
        ):
            result = await verifier.run_check("pytest")

        assert result.status == CheckStatus.PASSED
        assert result.passed is True
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_run_check_failure(
        self,
        verifier: CIVerifier,
        mock_subprocess_failure: MagicMock,
    ) -> None:
        """Test running a check that fails."""
        verifier.register_check(
            name="pytest",
            command=["python", "-m", "pytest"],
            check_type=CheckType.TEST,
        )

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_subprocess_failure
        ):
            result = await verifier.run_check("pytest")

        assert result.status == CheckStatus.FAILED
        assert result.failed is True
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_run_check_timeout(self, verifier: CIVerifier) -> None:
        """Test running a check that times out."""
        verifier.register_check(
            name="slow-check",
            command=["sleep", "100"],
            check_type=CheckType.TEST,
            timeout_seconds=1,
        )

        # Create a mock process that hangs
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(side_effect=TimeoutError())
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=TimeoutError()):
                result = await verifier.run_check("slow-check")

        assert result.status == CheckStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_run_check_command_not_found(self, verifier: CIVerifier) -> None:
        """Test running a check with non-existent command."""
        verifier.register_check(
            name="missing-cmd",
            command=["nonexistent_command_12345"],
            check_type=CheckType.CUSTOM,
        )

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("Command not found"),
        ):
            result = await verifier.run_check("missing-cmd")

        assert result.status == CheckStatus.ERROR
        assert "not found" in result.error.lower()


# ============================================================================
# CIVerifier Run Multiple Tests
# ============================================================================


class TestCIVerifierRunMultiple:
    """Tests for CIVerifier.run_checks and run_all_checks methods."""

    @pytest.mark.asyncio
    async def test_run_checks_parallel(self, configured_verifier: CIVerifier) -> None:
        """Test running multiple checks in parallel."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            results = await configured_verifier.run_checks(
                ["test-check", "lint-check"],
                parallel=True,
            )

        assert len(results) == 2
        assert all(r.status == CheckStatus.PASSED for r in results)

    @pytest.mark.asyncio
    async def test_run_checks_sequential(self, configured_verifier: CIVerifier) -> None:
        """Test running multiple checks sequentially."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            results = await configured_verifier.run_checks(
                ["test-check", "lint-check"],
                parallel=False,
            )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_run_all_checks(self, configured_verifier: CIVerifier) -> None:
        """Test running all registered checks."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await configured_verifier.run_all_checks()

        assert result.passed is True
        assert len(result.check_results) == 2

    @pytest.mark.asyncio
    async def test_run_all_checks_with_failure(self, verifier: CIVerifier) -> None:
        """Test run_all_checks with a required failure."""
        verifier.register_check(
            name="required-fail",
            command=["fail"],
            check_type=CheckType.TEST,
            required=True,
        )
        verifier.register_check(
            name="optional-fail",
            command=["fail"],
            check_type=CheckType.LINT,
            required=False,
        )

        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.communicate = AsyncMock(return_value=(b"", b"error"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_fail):
            result = await verifier.run_all_checks()

        assert result.passed is False
        assert len(result.required_failures) == 1

    @pytest.mark.asyncio
    async def test_run_all_checks_empty(self, verifier: CIVerifier) -> None:
        """Test run_all_checks with no checks."""
        result = await verifier.run_all_checks()

        assert result.passed is True
        assert result.status == CheckStatus.SKIPPED

    def test_run_all_checks_sync(self, configured_verifier: CIVerifier) -> None:
        """Test synchronous wrapper for run_all_checks."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = configured_verifier.run_all_checks_sync()

        assert result.passed is True


# ============================================================================
# CIVerifier Verification Management Tests
# ============================================================================


class TestCIVerifierVerificationManagement:
    """Tests for verification management methods."""

    @pytest.mark.asyncio
    async def test_get_active_verifications(
        self,
        configured_verifier: CIVerifier,
    ) -> None:
        """Test getting active verifications."""
        # Initially empty
        assert len(configured_verifier.get_active_verifications()) == 0

    def test_get_verification_not_found(self, verifier: CIVerifier) -> None:
        """Test getting a non-existent verification."""
        result = verifier.get_verification("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_verification_not_found(self, verifier: CIVerifier) -> None:
        """Test cancelling a non-existent verification."""
        result = await verifier.cancel_verification("nonexistent")
        assert result is False


# ============================================================================
# Gate Config Tests
# ============================================================================


class TestGateConfig:
    """Tests for GateConfig dataclass."""

    def test_config_defaults(self) -> None:
        """Test config default values."""
        config = GateConfig()

        assert config.enabled is True
        assert config.severity == GateSeverity.REQUIRED
        assert config.timeout_seconds == 300
        assert config.fail_fast is False
        assert config.parallel is True

    def test_config_custom(self) -> None:
        """Test config with custom values."""
        config = GateConfig(
            enabled=False,
            severity=GateSeverity.OPTIONAL,
            timeout_seconds=600,
            fail_fast=True,
            parallel=False,
        )

        assert config.enabled is False
        assert config.severity == GateSeverity.OPTIONAL
        assert config.timeout_seconds == 600
        assert config.fail_fast is True
        assert config.parallel is False


# ============================================================================
# Gate Result Tests
# ============================================================================


class TestGateResult:
    """Tests for GateResult dataclass."""

    def test_result_init(self) -> None:
        """Test gate result initialization."""
        result = GateResult(
            gate_name="Test Gate",
            gate_type="test",
        )

        assert result.gate_name == "Test Gate"
        assert result.gate_type == "test"
        assert result.status == GateStatus.PENDING
        assert result.passed is False

    def test_result_check_properties(self) -> None:
        """Test gate result check properties."""
        result = GateResult(
            gate_name="Test",
            gate_type="test",
            checks=[
                CheckResult(name="pass", status=CheckStatus.PASSED),
                CheckResult(name="fail", status=CheckStatus.FAILED),
                CheckResult(name="skip", status=CheckStatus.SKIPPED),
            ],
        )

        assert result.total_checks == 3
        assert len(result.passed_checks) == 1
        assert len(result.failed_checks) == 1
        assert len(result.skipped_checks) == 1

    def test_result_mark_methods(self) -> None:
        """Test mark_started and mark_complete methods."""
        result = GateResult(gate_name="Test", gate_type="test")
        result.mark_started()

        assert result.status == GateStatus.RUNNING
        assert result.started_at is not None

        result.mark_complete(
            status=GateStatus.PASSED,
            passed=True,
            summary="All tests passed",
        )

        assert result.status == GateStatus.PASSED
        assert result.passed is True
        assert result.summary == "All tests passed"
        assert result.duration_seconds is not None

    def test_result_to_dict(self) -> None:
        """Test to_dict method."""
        result = GateResult(
            gate_name="Test",
            gate_type="test",
            status=GateStatus.PASSED,
            passed=True,
        )
        data = result.to_dict()

        assert data["gate_name"] == "Test"
        assert data["gate_type"] == "test"
        assert data["status"] == "passed"
        assert data["passed"] is True


# ============================================================================
# TestGate Tests
# ============================================================================


class TestTestGate:
    """Tests for TestGate class."""

    def test_gate_init(self) -> None:
        """Test gate initialization."""
        gate = TestGate()

        assert gate.gate_type == "test"
        assert gate.gate_name == "Tests"
        assert len(gate.check_names) == 1
        assert "pytest" in gate.check_names

    def test_gate_with_custom_config(self) -> None:
        """Test gate with custom configuration."""
        config = GateConfig(
            enabled=False,
            severity=GateSeverity.OPTIONAL,
        )
        gate = TestGate(config=config)

        assert gate.is_enabled is False
        assert gate.is_required is False

    def test_gate_add_check(self) -> None:
        """Test adding a custom check."""
        gate = TestGate()
        gate.add_check(
            name="integration-tests",
            command=["pytest", "tests/integration/"],
            required=False,
        )

        assert "integration-tests" in gate.check_names

    def test_gate_remove_check(self) -> None:
        """Test removing a check."""
        gate = TestGate()
        result = gate.remove_check("pytest")

        assert result is True
        assert "pytest" not in gate.check_names

    @pytest.mark.asyncio
    async def test_gate_run_disabled(self) -> None:
        """Test running a disabled gate."""
        config = GateConfig(enabled=False)
        gate = TestGate(config=config)

        result = await gate.run()

        assert result.status == GateStatus.SKIPPED
        assert result.passed is True

    def test_gate_repr(self) -> None:
        """Test string representation."""
        gate = TestGate()
        repr_str = repr(gate)

        assert "TestGate" in repr_str
        assert "enabled=True" in repr_str


# ============================================================================
# LintGate Tests
# ============================================================================


class TestLintGate:
    """Tests for LintGate class."""

    def test_gate_init(self) -> None:
        """Test gate initialization."""
        gate = LintGate()

        assert gate.gate_type == "lint"
        assert gate.gate_name == "Lint"
        assert "ruff" in gate.check_names
        assert "ruff-format-check" in gate.check_names

    def test_gate_not_required_by_default(self) -> None:
        """Test that lint checks are not required by default."""
        gate = LintGate()

        # Default lint checks are optional
        check = gate._verifier.get_check("ruff")
        assert check.required is False


# ============================================================================
# SecurityGate Tests
# ============================================================================


class TestSecurityGate:
    """Tests for SecurityGate class."""

    def test_gate_init(self) -> None:
        """Test gate initialization."""
        gate = SecurityGate()

        assert gate.gate_type == "security"
        assert gate.gate_name == "Security"
        assert "bandit" in gate.check_names

    def test_gate_required_by_default(self) -> None:
        """Test that security checks are required by default."""
        gate = SecurityGate()

        check = gate._verifier.get_check("bandit")
        assert check.required is True


# ============================================================================
# TypeCheckGate Tests
# ============================================================================


class TestTypeCheckGate:
    """Tests for TypeCheckGate class."""

    def test_gate_init(self) -> None:
        """Test gate initialization."""
        gate = TypeCheckGate()

        assert gate.gate_type == "type_check"
        assert gate.gate_name == "Type Check"
        assert "mypy" in gate.check_names


# ============================================================================
# GateRunner Tests
# ============================================================================


class TestGateRunner:
    """Tests for GateRunner class."""

    def test_runner_init(self) -> None:
        """Test runner initialization."""
        runner = GateRunner()

        assert len(runner.gate_names) == 0
        assert runner._parallel is True
        assert runner._fail_fast is False

    def test_add_gate(self) -> None:
        """Test adding a gate."""
        runner = GateRunner()
        runner.add_gate(TestGate())

        assert len(runner.gate_names) == 1
        assert "Tests" in runner.gate_names

    def test_remove_gate(self) -> None:
        """Test removing a gate."""
        runner = GateRunner()
        runner.add_gate(TestGate())

        result = runner.remove_gate("Tests")

        assert result is True
        assert len(runner.gate_names) == 0

    def test_remove_gate_not_found(self) -> None:
        """Test removing a non-existent gate."""
        runner = GateRunner()
        result = runner.remove_gate("Nonexistent")

        assert result is False

    def test_get_gate(self) -> None:
        """Test getting a gate by name."""
        runner = GateRunner()
        gate = TestGate()
        runner.add_gate(gate)

        found = runner.get_gate("Tests")
        assert found is gate

    def test_get_gate_not_found(self) -> None:
        """Test getting a non-existent gate."""
        runner = GateRunner()
        found = runner.get_gate("Nonexistent")
        assert found is None

    @pytest.mark.asyncio
    async def test_run_gate(self) -> None:
        """Test running a single gate."""
        runner = GateRunner()
        config = GateConfig(enabled=False)  # Disabled to skip actual execution
        runner.add_gate(TestGate(config=config))

        result = await runner.run_gate("Tests")

        assert result.gate_name == "Tests"
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_gate_not_found(self) -> None:
        """Test running a non-existent gate."""
        runner = GateRunner()

        with pytest.raises(ValueError) as exc_info:
            await runner.run_gate("Nonexistent")

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_all_parallel(self) -> None:
        """Test running all gates in parallel."""
        runner = GateRunner(parallel=True)
        runner.add_gate(TestGate(GateConfig(enabled=False)))
        runner.add_gate(LintGate(GateConfig(enabled=False)))

        result = await runner.run_all(parallel=True)

        assert result.status == GateStatus.PASSED
        assert len(result.gates) == 2

    @pytest.mark.asyncio
    async def test_run_all_sequential(self) -> None:
        """Test running all gates sequentially."""
        runner = GateRunner(parallel=False)
        runner.add_gate(TestGate(GateConfig(enabled=False)))
        runner.add_gate(LintGate(GateConfig(enabled=False)))

        result = await runner.run_all(parallel=False)

        assert result.status == GateStatus.PASSED
        assert len(result.gates) == 2

    @pytest.mark.asyncio
    async def test_run_all_fail_fast(self) -> None:
        """Test fail-fast behavior."""
        runner = GateRunner(fail_fast=True)
        runner.add_gate(TestGate(GateConfig(enabled=False)))
        runner.add_gate(LintGate(GateConfig(enabled=False)))

        result = await runner.run_all()

        assert result.status == GateStatus.PASSED

    def test_run_all_sync(self) -> None:
        """Test synchronous wrapper for run_all."""
        runner = GateRunner()
        runner.add_gate(TestGate(GateConfig(enabled=False)))

        result = runner.run_all_sync()

        assert result.status == GateStatus.PASSED

    def test_runner_repr(self) -> None:
        """Test string representation."""
        runner = GateRunner()
        runner.add_gate(TestGate())
        repr_str = repr(runner)

        assert "GateRunner" in repr_str
        assert "gates=1" in repr_str


# ============================================================================
# GateRunnerResult Tests
# ============================================================================


class TestGateRunnerResult:
    """Tests for GateRunnerResult dataclass."""

    def test_result_init(self) -> None:
        """Test result initialization."""
        result = GateRunnerResult()

        assert result.gates == []
        assert result.status == GateStatus.PENDING
        assert result.passed is False

    def test_result_properties(self) -> None:
        """Test result properties."""
        result = GateRunnerResult()
        result.gates = [
            GateResult(gate_name="pass1", gate_type="test", passed=True),
            GateResult(gate_name="pass2", gate_type="lint", passed=True),
            GateResult(
                gate_name="fail1", gate_type="security", passed=False, required=True
            ),
        ]

        assert result.total_gates == 3
        assert len(result.passed_gates) == 2
        assert len(result.failed_gates) == 1
        assert len(result.required_failures) == 1

    def test_result_to_dict(self) -> None:
        """Test to_dict method."""
        result = GateRunnerResult(
            status=GateStatus.PASSED,
            passed=True,
        )
        data = result.to_dict()

        assert data["status"] == "passed"
        assert data["passed"] is True


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_verifier(self) -> None:
        """Test create_verifier factory function."""
        verifier = create_verifier(parallel=True, add_defaults=True)

        assert isinstance(verifier, CIVerifier)
        assert verifier._parallel is True
        assert len(verifier.check_names) > 0

    def test_create_default_gates(self) -> None:
        """Test create_default_gates factory function."""
        gates = create_default_gates(
            test=True,
            lint=True,
            security=True,
            type_check=False,
        )

        assert len(gates) == 3
        gate_types = {g.gate_type for g in gates}
        assert "test" in gate_types
        assert "lint" in gate_types
        assert "security" in gate_types
        assert "type_check" not in gate_types

    def test_create_default_runner(self) -> None:
        """Test create_default_runner factory function."""
        runner = create_default_runner(
            test=True,
            lint=True,
            security=True,
            type_check=False,
            parallel=True,
        )

        assert isinstance(runner, GateRunner)
        assert len(runner.gate_names) == 3
        assert runner._parallel is True


# ============================================================================
# CIVerifier Representation Tests
# ============================================================================


class TestCIVerifierRepr:
    """Tests for CIVerifier string representation."""

    def test_repr_empty(self, verifier: CIVerifier) -> None:
        """Test repr of empty verifier."""
        repr_str = repr(verifier)

        assert "CIVerifier" in repr_str
        assert "checks=0" in repr_str

    def test_repr_with_checks(self, configured_verifier: CIVerifier) -> None:
        """Test repr of verifier with checks."""
        repr_str = repr(configured_verifier)

        assert "checks=2" in repr_str
        assert "enabled=2" in repr_str
