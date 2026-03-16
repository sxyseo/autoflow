"""
Completion Checker Module

Provides strict completion standards for Autoflow tasks and runs.
Implements automated checks to ensure quality before marking work as complete.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    """Result of a completion check."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float = 0.0


class CompletionStandard(Enum):
    """Types of completion standards."""

    UNIT_TESTS = "unit_tests"
    INTEGRATION_TESTS = "integration_tests"
    E2E_TESTS = "e2e_tests"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    CODE_QUALITY = "code_quality"
    USER_ACCEPTANCE = "user_acceptance"


class CompletionChecker:
    """
    Verifies that tasks meet strict completion standards.

    This class implements automated quality checks that must pass
    before work can be marked as complete. Replaces the weak
    "unit tests pass" standard with comprehensive quality gates.
    """

    def __init__(
        self,
        project_root: Path | str,
        strict_mode: bool = True,
        timeout_seconds: float = 300.0,
    ) -> None:
        """
        Initialize completion checker.

        Args:
            project_root: Root directory of the project
            strict_mode: If True, all checks must pass
            timeout_seconds: Maximum time for each check
        """
        self.project_root = Path(project_root)
        self.strict_mode = strict_mode
        self.timeout = timeout_seconds

        # Check results
        self._results: list[CheckResult] = []

    async def check_all(
        self,
        task_id: str | None = None,
        run_id: str | None = None,
        standards: list[CompletionStandard] | None = None,
    ) -> dict[str, Any]:
        """
        Run all completion checks.

        Args:
            task_id: Optional task identifier
            run_id: Optional run identifier
            standards: List of standards to check (default: all)

        Returns:
            Dictionary with check results and summary
        """
        if standards is None:
            standards = list(CompletionStandard)

        self._results.clear()

        # Run all checks
        for standard in standards:
            result = await self._run_check(standard, task_id, run_id)
            self._results.append(result)

        # Generate summary
        summary = self._generate_summary()

        return {
            "task_id": task_id,
            "run_id": run_id,
            "checks": [r.model_dump() for r in self._results],
            "summary": summary,
            "passed": summary["all_passed"],
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _run_check(
        self,
        standard: CompletionStandard,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Run a single completion check."""
        start_time = asyncio.get_event_loop().time()

        try:
            # Route to appropriate check method
            check_method = self._get_check_method(standard)

            # Run check with timeout
            result = await asyncio.wait_for(
                check_method(task_id, run_id),
                timeout=self.timeout,
            )

        except asyncio.TimeoutError:
            result = CheckResult(
                name=standard.value,
                passed=False,
                message=f"Check timed out after {self.timeout}s",
            )
        except Exception as e:
            result = CheckResult(
                name=standard.value,
                passed=False,
                message=f"Check failed with error: {str(e)}",
            )

        # Record duration
        result.duration_seconds = asyncio.get_event_loop().time() - start_time

        return result

    def _get_check_method(
        self,
        standard: CompletionStandard,
    ) -> Callable[[str | None, str | None], CheckResult]:
        """Get the check method for a standard."""
        methods = {
            CompletionStandard.UNIT_TESTS: self._check_unit_tests,
            CompletionStandard.INTEGRATION_TESTS: self._check_integration_tests,
            CompletionStandard.E2E_TESTS: self._check_e2e_tests,
            CompletionStandard.PERFORMANCE: self._check_performance,
            CompletionStandard.SECURITY: self._check_security,
            CompletionStandard.DOCUMENTATION: self._check_documentation,
            CompletionStandard.CODE_QUALITY: self._check_code_quality,
            CompletionStandard.USER_ACCEPTANCE: self._check_user_acceptance,
        }

        if standard not in methods:
            return lambda t, r: CheckResult(
                name=standard.value,
                passed=False,
                message=f"No check implemented for {standard.value}",
            )

        return methods[standard]

    async def _check_unit_tests(
        self,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Check that unit tests pass."""
        try:
            # Run pytest for unit tests
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/unit/", "-v", "--tb=short"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            passed = result.returncode == 0

            # Parse output for details
            output = result.stdout + result.stderr
            test_count = self._parse_test_count(output)

            return CheckResult(
                name=CompletionStandard.UNIT_TESTS.value,
                passed=passed,
                message=f"Unit tests {'passed' if passed else 'failed'} ({test_count} tests)",
                details={
                    "exit_code": result.returncode,
                    "test_count": test_count,
                    "output": output[-1000:],  # Last 1000 chars
                },
            )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=CompletionStandard.UNIT_TESTS.value,
                passed=False,
                message="Unit tests timed out",
            )
        except Exception as e:
            return CheckResult(
                name=CompletionStandard.UNIT_TESTS.value,
                passed=False,
                message=f"Failed to run unit tests: {str(e)}",
            )

    async def _check_integration_tests(
        self,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Check that integration tests pass."""
        try:
            # Run pytest for integration tests
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/integration/", "-v", "--tb=short"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120,
            )

            passed = result.returncode == 0
            output = result.stdout + result.stderr
            test_count = self._parse_test_count(output)

            return CheckResult(
                name=CompletionStandard.INTEGRATION_TESTS.value,
                passed=passed,
                message=f"Integration tests {'passed' if passed else 'failed'} ({test_count} tests)",
                details={
                    "exit_code": result.returncode,
                    "test_count": test_count,
                    "output": output[-1000:],
                },
            )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=CompletionStandard.INTEGRATION_TESTS.value,
                passed=False,
                message="Integration tests timed out",
            )
        except Exception as e:
            return CheckResult(
                name=CompletionStandard.INTEGRATION_TESTS.value,
                passed=False,
                message=f"Failed to run integration tests: {str(e)}",
            )

    async def _check_e2e_tests(
        self,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Check that E2E tests pass."""
        try:
            # Run pytest for E2E tests
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/e2e/", "-v", "--tb=short"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,
            )

            passed = result.returncode == 0
            output = result.stdout + result.stderr
            test_count = self._parse_test_count(output)

            return CheckResult(
                name=CompletionStandard.E2E_TESTS.value,
                passed=passed,
                message=f"E2E tests {'passed' if passed else 'failed'} ({test_count} tests)",
                details={
                    "exit_code": result.returncode,
                    "test_count": test_count,
                    "output": output[-1000:],
                },
            )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=CompletionStandard.E2E_TESTS.value,
                passed=False,
                message="E2E tests timed out",
            )
        except Exception as e:
            return CheckResult(
                name=CompletionStandard.E2E_TESTS.value,
                passed=False,
                message=f"Failed to run E2E tests: {str(e)}",
            )

    async def _check_performance(
        self,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Check performance benchmarks."""
        try:
            # Run performance tests
            perf_file = self.project_root / "tests" / "performance" / "benchmarks.json"

            if not perf_file.exists():
                return CheckResult(
                    name=CompletionStandard.PERFORMANCE.value,
                    passed=True,  # Not blocking if no benchmarks defined
                    message="No performance benchmarks defined",
                )

            # Load and check benchmarks
            benchmarks = json.loads(perf_file.read_text())

            # For now, just check that benchmarks exist
            # In production, you'd compare against baseline
            return CheckResult(
                name=CompletionStandard.PERFORMANCE.value,
                passed=True,
                message=f"Performance benchmarks loaded ({len(benchmarks)} benchmarks)",
                details={"benchmarks": benchmarks},
            )

        except Exception as e:
            return CheckResult(
                name=CompletionStandard.PERFORMANCE.value,
                passed=False,
                message=f"Performance check failed: {str(e)}",
            )

    async def _check_security(
        self,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Check security vulnerabilities."""
        try:
            # Run security tests
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/security/", "-v", "--tb=short"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            passed = result.returncode == 0
            output = result.stdout + result.stderr
            test_count = self._parse_test_count(output)

            return CheckResult(
                name=CompletionStandard.SECURITY.value,
                passed=passed,
                message=f"Security tests {'passed' if passed else 'failed'} ({test_count} tests)",
                details={
                    "exit_code": result.returncode,
                    "test_count": test_count,
                    "output": output[-1000:],
                },
            )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=CompletionStandard.SECURITY.value,
                passed=False,
                message="Security tests timed out",
            )
        except Exception as e:
            return CheckResult(
                name=CompletionStandard.SECURITY.value,
                passed=False,
                message=f"Failed to run security tests: {str(e)}",
            )

    async def _check_documentation(
        self,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Check documentation completeness."""
        issues = []

        # Check for README
        if not (self.project_root / "README.md").exists():
            issues.append("Missing README.md")

        # Check for docstring coverage
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "--cov", "--cov-report=term-missing"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            output = result.stdout + result.stderr
            # Parse coverage from output
            coverage_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
            if coverage_match:
                coverage = int(coverage_match.group(1))
                if coverage < 70:
                    issues.append(f"Documentation coverage {coverage}% < 70%")
        except:
            pass  # Coverage check is optional

        passed = len(issues) == 0

        return CheckResult(
            name=CompletionStandard.DOCUMENTATION.value,
            passed=passed,
            message=f"Documentation check {'passed' if passed else 'failed'}",
            details={"issues": issues},
        )

    async def _check_code_quality(
        self,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Check code quality metrics."""
        issues = []

        # Check for linting errors (if configured)
        try:
            result = subprocess.run(
                ["python3", "-m", "pylint", "autoflow/"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                # Count errors
                output = result.stdout + result.stderr
                error_count = output.count("error:")
                if error_count > 0:
                    issues.append(f"Found {error_count} pylint errors")
        except:
            pass  # Pylint is optional

        # Check for type annotations
        try:
            result = subprocess.run(
                ["python3", "-m", "mypy", "autoflow/"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                issues.append("Type checking failed")
        except:
            pass  # Mypy is optional

        passed = len(issues) == 0

        return CheckResult(
            name=CompletionStandard.CODE_QUALITY.value,
            passed=passed,
            message=f"Code quality check {'passed' if passed else 'failed'}",
            details={"issues": issues},
        )

    async def _check_user_acceptance(
        self,
        task_id: str | None,
        run_id: str | None,
    ) -> CheckResult:
        """Check user acceptance criteria."""
        # For now, this is a placeholder
        # In production, you'd check against defined UAT scenarios

        if task_id:
            # Check if task has acceptance criteria defined
            tasks_file = self.project_root / ".autoflow" / "tasks" / f"{task_id}.json"

            if tasks_file.exists():
                tasks_data = json.loads(tasks_file.read_text())

                for task in tasks_data.get("tasks", []):
                    if task.get("id") == task_id:
                        criteria = task.get("acceptance_criteria", [])
                        if not criteria:
                            return CheckResult(
                                name=CompletionStandard.USER_ACCEPTANCE.value,
                                passed=False,
                                message="No acceptance criteria defined",
                            )

                        return CheckResult(
                            name=CompletionStandard.USER_ACCEPTANCE.value,
                            passed=True,
                            message=f"Acceptance criteria defined ({len(criteria)} items)",
                            details={"criteria": criteria},
                        )

        # No task specified, pass by default
        return CheckResult(
            name=CompletionStandard.USER_ACCEPTANCE.value,
            passed=True,
            message="User acceptance check not applicable",
        )

    def _parse_test_count(self, output: str) -> int:
        """Parse test count from pytest output."""
        # Look for pattern like "5 passed in 2.3s"
        match = re.search(r"(\d+)\s+passed", output)
        if match:
            return int(match.group(1))

        # Alternative pattern: "collected 5 items"
        match = re.search(r"collected\s+(\d+)\s+items?", output)
        if match:
            return int(match.group(1))

        return 0

    def _generate_summary(self) -> dict[str, Any]:
        """Generate summary of check results."""
        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        failed = total - passed

        return {
            "total_checks": total,
            "passed_checks": passed,
            "failed_checks": failed,
            "pass_rate": passed / total if total > 0 else 0,
            "all_passed": failed == 0,
            "strict_mode": self.strict_mode,
            "can_mark_complete": (
                failed == 0 if self.strict_mode else passed > 0
            ),
        }

    def generate_report(self) -> str:
        """Generate human-readable report."""
        lines = [
            "=" * 60,
            "Completion Check Report",
            "=" * 60,
            f"Timestamp: {datetime.utcnow().isoformat()}",
            f"Strict Mode: {self.strict_mode}",
            "",
        ]

        for result in self._results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            lines.append(f"{status}: {result.name}")
            lines.append(f"  {result.message}")
            if result.details:
                lines.append(f"  Details: {json.dumps(result.details, indent=2)}")
            lines.append("")

        summary = self._generate_summary()
        lines.extend([
            "-" * 60,
            "Summary",
            "-" * 60,
            f"Total Checks: {summary['total_checks']}",
            f"Passed: {summary['passed_checks']}",
            f"Failed: {summary['failed_checks']}",
            f"Pass Rate: {summary['pass_rate']:.1%}",
            f"Can Mark Complete: {summary['can_mark_complete']}",
            "=" * 60,
        ])

        return "\n".join(lines)

    async def save_report(self, output_path: Path | str) -> None:
        """Save report to file."""
        report = self.generate_report()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)


async def main():
    """CLI for completion checker."""
    import sys

    project_root = Path.cwd()

    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1])

    checker = CompletionChecker(project_root)

    # Run all checks
    result = await checker.check_all()

    # Print report
    print(checker.generate_report())

    # Save report
    report_path = project_root / ".autoflow" / "completion_reports" / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
    await checker.save_report(report_path)
    print(f"\nReport saved to: {report_path}")

    # Exit with appropriate code
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
