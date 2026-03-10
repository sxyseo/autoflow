#!/usr/bin/env python3
"""
Autoflow Verification Orchestrator Module

Provides unified verification orchestration that combines test execution,
coverage analysis, and QA findings management into a single workflow.
Generates comprehensive verification reports and coordinates with approval gates.
"""

import contextlib
import json
import os
import subprocess
import sys
import unittest
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .approval import ApprovalGate, ApprovalToken
from .coverage import CoverageReport, CoverageTracker
from .qa_findings import QAFinding, QAFindingReport, QAFindingsManager, SeverityLevel


@dataclass
class VerificationResult:
    """
    Result of verification orchestration.

    Args:
        success: Whether verification passed all gates
        test_results: Test execution summary
        coverage_report: Coverage analysis results
        qa_findings: QA findings collected during verification
        approval_token: Approval token if verification passed
        fix_tasks_generated: Number of fix tasks automatically generated
        errors: List of errors encountered during verification
        warnings: List of warnings (non-blocking)
        timestamp: Verification timestamp
        duration_seconds: Time taken for verification
    """

    success: bool
    test_results: dict[str, int]
    coverage_report: CoverageReport | None
    qa_findings: QAFindingReport
    approval_token: ApprovalToken | None
    fix_tasks_generated: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Convert result to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "test_results": self.test_results,
            "coverage_report": (
                self.coverage_report.to_dict() if self.coverage_report else None
            ),
            "qa_findings": self.qa_findings.to_dict(),
            "approval_token": (
                self.approval_token.to_dict() if self.approval_token else None
            ),
            "fix_tasks_generated": self.fix_tasks_generated,
            "errors": self.errors,
            "warnings": self.warnings,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
        }

    def get_summary(self) -> dict:
        """Get summary of verification results."""
        summary = {
            "status": "PASS" if self.success else "FAIL",
            "tests": self.test_results,
            "coverage": None,
            "qa_findings": self.qa_findings.get_summary(),
            "has_approval": self.approval_token is not None,
        }

        if self.coverage_report:
            summary["coverage"] = {
                "total": self.coverage_report.total,
                "branches": self.coverage_report.branches,
                "functions": self.coverage_report.functions,
                "lines": self.coverage_report.lines,
            }

        return summary


@dataclass
class VerificationConfig:
    """
    Configuration for verification orchestration.

    Args:
        run_tests: Whether to run tests
        run_coverage: Whether to run coverage analysis
        check_coverage_thresholds: Whether to enforce coverage thresholds
        generate_qa_findings: Whether to generate QA findings from failures
        grant_approval_on_success: Whether to grant approval on successful verification
        generate_fix_tasks: Whether to automatically generate fix tasks on verification failure
        fix_task_agent: Agent to assign fix tasks to
        fix_tasks_output_dir: Directory to save fix tasks in
        test_dir: Directory containing tests
        test_pattern: Pattern for test discovery
        source_dirs: Source directories for coverage measurement
        test_command: Command to run tests for coverage
        blocking_severities: Severity levels that block verification
        work_dir: Working directory for verification
        config_path: Path to QA gates configuration file
    """

    run_tests: bool = True
    run_coverage: bool = True
    check_coverage_thresholds: bool = True
    generate_qa_findings: bool = True
    grant_approval_on_success: bool = True
    generate_fix_tasks: bool = True
    fix_task_agent: str = "implementation-runner"
    fix_tasks_output_dir: str = ".autoflow/tasks"
    test_dir: str = "tests"
    test_pattern: str = "test*.py"
    source_dirs: list[str] = field(default_factory=lambda: ["autoflow"])
    test_command: str = "python -m unittest discover tests/"
    blocking_severities: list[str] = field(default_factory=lambda: ["CRITICAL", "HIGH"])
    work_dir: str = "."
    config_path: str | None = None

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return asdict(self)


class VerificationOrchestrator:
    """
    Unified verification orchestrator.

    Coordinates test execution, coverage analysis, and QA findings management
    to provide comprehensive verification of code quality.
    """

    def __init__(self, config: VerificationConfig | None = None):
        """
        Initialize verification orchestrator.

        Args:
            config: Verification configuration
        """
        self.config = config or VerificationConfig()
        self.work_dir = Path(self.config.work_dir)

        # Initialize components
        self.coverage_tracker = CoverageTracker(
            config_path=self.config.config_path, work_dir=self.config.work_dir
        )
        self.qa_manager = QAFindingsManager(work_dir=self.config.work_dir)
        self.approval_gate = ApprovalGate(work_dir=self.config.work_dir)

    def run_tests(self) -> tuple[dict[str, int], list[str]]:
        """
        Run test suite.

        Returns:
            Tuple of (test_results, errors)
        """
        if not self.config.run_tests:
            return {"skipped": True}, []

        test_dir = self.work_dir / self.config.test_dir

        if not test_dir.exists():
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": True,
                "errors": ["Test directory not found"],
            }, ["Test directory not found"]

        try:
            # Discover and run tests
            loader = unittest.TestLoader()
            suite = loader.discover(
                start_dir=str(test_dir), pattern=self.config.test_pattern
            )

            runner = unittest.TextTestRunner(
                stream=open(os.devnull, "w"), verbosity=0  # Suppress output
            )

            result = runner.run(suite)

            test_results = {
                "total": result.testsRun,
                "passed": result.testsRun - len(result.failures) - len(result.errors),
                "failed": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
            }

            errors = []
            if result.failures:
                errors.append(f"{len(result.failures)} test(s) failed")
            if result.errors:
                errors.append(f"{len(result.errors)} test(s) had errors")

            return test_results, errors

        except Exception as e:
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "skipped": True,
            }, [f"Error running tests: {e}"]

    def run_coverage_analysis(self) -> tuple[CoverageReport | None, list[str]]:
        """
        Run coverage analysis.

        Returns:
            Tuple of (coverage_report, errors)
        """
        if not self.config.run_coverage:
            return None, []

        try:
            # Run coverage
            exit_code, output = self.coverage_tracker.run_coverage(
                test_command=self.config.test_command,
                source_dirs=self.config.source_dirs,
            )

            if exit_code != 0:
                return None, [f"Coverage execution failed: {output}"]

            # Generate report
            report = self.coverage_tracker.generate_report()

            errors = []
            if self.config.check_coverage_thresholds:
                passes, failing = self.coverage_tracker.check_thresholds(report)
                if not passes:
                    errors.extend(failing)

            return report, errors

        except Exception as e:
            return None, [f"Error running coverage: {e}"]

    def generate_qa_findings(
        self, test_results: dict[str, int], coverage_report: CoverageReport | None
    ) -> QAFindingReport:
        """
        Generate QA findings from test and coverage results.

        Args:
            test_results: Test execution results
            coverage_report: Coverage analysis results

        Returns:
            QAFindingReport with generated findings
        """
        if not self.config.generate_qa_findings:
            return QAFindingReport(source="verification")

        report = self.qa_manager.create_report(source="verification")

        # Add findings for test failures
        if test_results.get("failed", 0) > 0:
            report.add_finding(
                QAFinding(
                    file="test_results",
                    line=0,
                    severity=SeverityLevel.HIGH,
                    category="test",
                    message=f"{test_results['failed']} test(s) failed",
                    suggested_fix="Fix failing tests before committing",
                    context=f"Passed: {test_results.get('passed', 0)}, Failed: {test_results['failed']}",
                    rule_id="test-failure",
                )
            )

        if test_results.get("errors", 0) > 0:
            report.add_finding(
                QAFinding(
                    file="test_results",
                    line=0,
                    severity=SeverityLevel.CRITICAL,
                    category="test",
                    message=f"{test_results['errors']} test(s) had errors",
                    suggested_fix="Fix test errors before committing",
                    context=f"Errors: {test_results['errors']}",
                    rule_id="test-error",
                )
            )

        # Add findings for coverage gaps
        if coverage_report:
            threshold = self.coverage_tracker.threshold.minimum

            # Check total coverage
            if coverage_report.total < threshold:
                report.add_finding(
                    self.qa_manager.parse_coverage_gap(
                        file_path="total",
                        coverage_percent=coverage_report.total,
                        threshold=threshold,
                    )
                )

            # Check per-file coverage
            for file_path, coverage in coverage_report.files.items():
                if coverage < threshold:
                    report.add_finding(
                        self.qa_manager.parse_coverage_gap(
                            file_path=file_path,
                            coverage_percent=coverage,
                            threshold=threshold,
                        )
                    )

        return report

    def generate_fix_tasks_from_findings(
        self, qa_findings: QAFindingReport
    ) -> tuple[int, list[str]]:
        """
        Generate fix tasks from QA findings.

        Args:
            qa_findings: QA findings report to generate tasks from

        Returns:
            Tuple of (number_of_tasks_generated, errors)
        """
        if not self.config.generate_fix_tasks:
            return 0, []

        if not qa_findings.findings:
            return 0, []

        try:
            # Save QA findings to temporary file for the generator script
            temp_findings_file = self.work_dir / ".qa_findings_temp.json"
            qa_findings_manager = QAFindingsManager(work_dir=str(self.work_dir))
            qa_findings_manager.save_report(qa_findings, str(temp_findings_file))

            # Build command to run fix task generator
            script_path = (
                Path(__file__).parent.parent.parent
                / "scripts"
                / "generate_fix_tasks.py"
            )

            if not script_path.exists():
                return 0, [f"Fix task generator script not found: {script_path}"]

            cmd = [
                sys.executable,
                str(script_path),
                "--input",
                str(temp_findings_file),
                "--output",
                self.config.fix_tasks_output_dir,
                "--agent",
                self.config.fix_task_agent,
                "--blocking-only",  # Only generate tasks for blocking findings
                "--work-dir",
                str(self.work_dir),
            ]

            # Run the generator script
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(self.work_dir)
            )

            # Clean up temp file
            with contextlib.suppress(Exception):
                temp_findings_file.unlink()

            if result.returncode != 0:
                return 0, [f"Fix task generation failed: {result.stderr}"]

            # Parse output to get count
            # The script outputs "✓ Generated N fix task(s)"
            output_lines = result.stdout.strip().split("\n")
            for line in output_lines:
                if "Generated" in line and "fix task" in line:
                    try:
                        # Extract number from "✓ Generated N fix task(s)"
                        count = int("".join(filter(str.isdigit, line.split()[1])))
                        return count, []
                    except (ValueError, IndexError):
                        pass

            # If we couldn't parse the count, check output directory
            output_dir = self.work_dir / self.config.fix_tasks_output_dir
            if output_dir.exists():
                task_count = len(list(output_dir.glob("fix-*.json")))
                return task_count, []

            return 0, []

        except Exception as e:
            return 0, [f"Error generating fix tasks: {e}"]

    def verify(self) -> VerificationResult:
        """
        Run full verification workflow.

        Returns:
            VerificationResult with comprehensive verification status
        """
        start_time = datetime.now()
        timestamp = start_time.isoformat()

        errors = []
        warnings = []

        # Run tests
        test_results, test_errors = self.run_tests()
        errors.extend(test_errors)

        # Run coverage
        coverage_report, coverage_errors = self.run_coverage_analysis()
        if coverage_errors:
            errors.extend(coverage_errors)

        # Generate QA findings
        qa_findings = self.generate_qa_findings(test_results, coverage_report)

        # Check for blocking QA findings
        blocking_findings = qa_findings.get_blocking_findings()
        if blocking_findings:
            errors.append(
                f"Found {len(blocking_findings)} blocking QA finding(s) "
                f"({', '.join(self.config.blocking_severities)} severity)"
            )

        # Determine overall success
        # Verification passes if:
        # - No test failures or errors
        # - Coverage meets thresholds (if checking)
        # - No blocking QA findings
        success = (
            test_results.get("failed", 0) == 0
            and test_results.get("errors", 0) == 0
            and len(coverage_errors) == 0
            and len(blocking_findings) == 0
        )

        # Generate fix tasks if verification failed
        fix_tasks_generated = 0
        if not success and qa_findings.findings:
            fix_tasks_count, fix_task_errors = self.generate_fix_tasks_from_findings(
                qa_findings
            )
            if fix_task_errors:
                warnings.extend(fix_task_errors)
            elif fix_tasks_count > 0:
                fix_tasks_generated = fix_tasks_count
                warnings.append(
                    f"Generated {fix_tasks_count} fix task(s) in {self.config.fix_tasks_output_dir}"
                )

        # Grant approval if successful and configured
        approval_token = None
        if success and self.config.grant_approval_on_success:
            # Prepare QA findings count for approval
            qa_findings_count = qa_findings.get_summary()

            # Prepare coverage data for approval
            coverage_data = None
            if coverage_report:
                coverage_data = {
                    "total": coverage_report.total,
                    "branches": coverage_report.branches,
                    "functions": coverage_report.functions,
                    "lines": coverage_report.lines,
                }

            # Grant approval
            approved, approval_errors = self.approval_gate.grant_approval(
                test_results=test_results,
                coverage_data=coverage_data,
                qa_findings_count=qa_findings_count,
            )

            if approved:
                approval_token = self.approval_gate.load_token()
            else:
                errors.extend(approval_errors)
                success = False

        # Calculate duration
        end_time = datetime.now()
        duration_seconds = (end_time - start_time).total_seconds()

        return VerificationResult(
            success=success,
            test_results=test_results,
            coverage_report=coverage_report,
            qa_findings=qa_findings,
            approval_token=approval_token,
            fix_tasks_generated=fix_tasks_generated,
            errors=errors,
            warnings=warnings,
            timestamp=timestamp,
            duration_seconds=duration_seconds,
        )

    def save_result(self, result: VerificationResult, output_path: str) -> None:
        """
        Save verification result to file.

        Args:
            result: VerificationResult to save
            output_path: Path to output file
        """
        output_file = self.work_dir / output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    def load_result(self, input_path: str) -> VerificationResult:
        """
        Load verification result from file.

        Args:
            input_path: Path to input file

        Returns:
            VerificationResult with loaded data
        """
        input_file = self.work_dir / input_path

        with open(input_file) as f:
            data = json.load(f)

        # Reconstruct objects
        coverage_report = None
        if data.get("coverage_report"):
            cr_data = data["coverage_report"]
            coverage_report = CoverageReport(
                total=cr_data["total"],
                branches=cr_data.get("branches"),
                functions=cr_data.get("functions"),
                lines=cr_data.get("lines"),
                files=cr_data.get("files", {}),
                timestamp=cr_data.get("timestamp", ""),
            )

        qa_findings = QAFindingReport.from_dict(data["qa_findings"])

        approval_token = None
        if data.get("approval_token"):
            approval_token = ApprovalToken.from_dict(data["approval_token"])

        return VerificationResult(
            success=data["success"],
            test_results=data["test_results"],
            coverage_report=coverage_report,
            qa_findings=qa_findings,
            approval_token=approval_token,
            fix_tasks_generated=data.get("fix_tasks_generated", 0),
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
            timestamp=data["timestamp"],
            duration_seconds=data["duration_seconds"],
        )

    def check_commit_allowed(self) -> tuple[bool, list[str]]:
        """
        Check if commit is allowed based on current verification state.

        Returns:
            Tuple of (allowed, error_messages)
        """
        return self.approval_gate.verify_commit_allowed()

    def get_verification_status(self) -> dict:
        """
        Get current verification status.

        Returns:
            Dictionary with verification status information
        """
        token_status = self.approval_gate.get_token_status()

        return {"token_status": token_status, "config": self.config.to_dict()}


def create_verification_report(
    result: VerificationResult, verbose: bool = False
) -> str:
    """
    Create human-readable verification report.

    Args:
        result: VerificationResult to report on
        verbose: Whether to include detailed information

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("VERIFICATION REPORT")
    lines.append("=" * 70)

    # Status
    status_symbol = "✓ PASS" if result.success else "✗ FAIL"
    lines.append(f"\nStatus: {status_symbol}")
    lines.append(f"Time: {result.timestamp}")
    lines.append(f"Duration: {result.duration_seconds:.2f}s")

    # Test Results
    lines.append("\n" + "-" * 70)
    lines.append("TEST RESULTS")
    lines.append("-" * 70)

    if result.test_results.get("skipped"):
        lines.append("  Tests: SKIPPED")
    else:
        total = result.test_results.get("total", 0)
        passed = result.test_results.get("passed", 0)
        failed = result.test_results.get("failed", 0)
        errors = result.test_results.get("errors", 0)
        skipped = result.test_results.get("skipped", 0)

        lines.append(f"  Total:   {total}")
        lines.append(f"  Passed:  {passed}")
        if failed > 0:
            lines.append(f"  Failed:  {failed} ✗")
        if errors > 0:
            lines.append(f"  Errors:  {errors} ✗")
        if skipped > 0:
            lines.append(f"  Skipped: {skipped}")

    # Coverage Results
    if result.coverage_report:
        lines.append("\n" + "-" * 70)
        lines.append("COVERAGE")
        lines.append("-" * 70)

        cr = result.coverage_report
        lines.append(f"  Total:     {cr.total:.1f}%")
        if cr.branches:
            lines.append(f"  Branches:  {cr.branches:.1f}%")
        if cr.functions:
            lines.append(f"  Functions: {cr.functions:.1f}%")
        if cr.lines:
            lines.append(f"  Lines:     {cr.lines:.1f}%")

        if verbose and cr.files:
            lines.append("\n  Per-File Coverage:")
            for file_path, coverage in sorted(cr.files.items()):
                status = "✓" if coverage >= 80.0 else "✗"
                lines.append(f"    {status} {file_path}: {coverage:.1f}%")

    # QA Findings
    if result.qa_findings.findings:
        lines.append("\n" + "-" * 70)
        lines.append("QA FINDINGS")
        lines.append("-" * 70)

        summary = result.qa_findings.get_summary()
        lines.append(f"  Total: {summary['total']}")
        lines.append(f"  Critical: {summary['critical']} 🔴")
        lines.append(f"  High:     {summary['high']} 🟠")
        lines.append(f"  Medium:   {summary['medium']} 🟡")
        lines.append(f"  Low:      {summary['low']} 🔵")

        if verbose and result.qa_findings.findings:
            lines.append("\n  Findings:")
            for finding in result.qa_findings.findings[:10]:  # Limit to first 10
                lines.append(f"    - {finding}")
            if len(result.qa_findings.findings) > 10:
                lines.append(
                    f"    ... and {len(result.qa_findings.findings) - 10} more"
                )

    # Approval Token
    if result.approval_token:
        lines.append("\n" + "-" * 70)
        lines.append("APPROVAL")
        lines.append("-" * 70)
        lines.append("  Status: APPROVED ✓")
        lines.append(f"  Hash:   {result.approval_token.hash[:16]}...")
        lines.append(f"  Time:   {result.approval_token.timestamp}")

    # Fix Tasks
    if result.fix_tasks_generated > 0:
        lines.append("\n" + "-" * 70)
        lines.append("FIX TASKS")
        lines.append("-" * 70)
        lines.append(f"  Generated: {result.fix_tasks_generated} task(s)")
        lines.append("  Location: .autoflow/tasks/")
        lines.append("  Agent: implementation-runner")

    # Errors and Warnings
    if result.errors:
        lines.append("\n" + "-" * 70)
        lines.append("ERRORS")
        lines.append("-" * 70)
        for error in result.errors:
            lines.append(f"  ✗ {error}")

    if result.warnings:
        lines.append("\n" + "-" * 70)
        lines.append("WARNINGS")
        lines.append("-" * 70)
        for warning in result.warnings:
            lines.append(f"  ⚠ {warning}")

    lines.append("\n" + "=" * 70)

    return "\n".join(lines)


# Import os for devnull
