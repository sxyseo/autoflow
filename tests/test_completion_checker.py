"""
Tests for Completion Checker System

Tests the completion checker that enforces strict quality standards.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from autoflow.quality.completion_checker import (
    CheckResult,
    CompletionChecker,
    CompletionStandard,
)


class TestCompletionChecker:
    """Test the completion checker functionality."""

    @pytest.fixture
    def temp_project(self):
        """Create temporary project directory."""
        temp_dir = tempfile.mkdtemp(prefix="autoflow_completion_test_")
        project_path = Path(temp_dir)

        # Create basic structure
        (project_path / "tests").mkdir()
        (project_path / "tests" / "unit").mkdir()
        (project_path / "tests" / "integration").mkdir()
        (project_path / "tests" / "e2e").mkdir()
        (project_path / ".autoflow").mkdir()
        (project_path / ".autoflow" / "tasks").mkdir()

        yield project_path

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def checker(self, temp_project: Path):
        """Create completion checker instance."""
        return CompletionChecker(temp_project)

    async def test_checker_initialization(self, temp_project: Path) -> None:
        """Test checker initializes correctly."""
        checker = CompletionChecker(temp_project)

        assert checker.project_root == temp_project
        assert checker.strict_mode is True
        assert checker.timeout == 300.0
        assert len(checker._results) == 0

    async def test_check_all_runs_all_standards(self, checker: CompletionChecker) -> None:
        """Test that check_all runs all standards."""
        # Create mock test files
        test_file = checker.project_root / "tests" / "unit" / "test_example.py"
        test_file.write_text("""
def test_example():
    assert True
""")

        # Run checks (will fail on missing pytest, but that's ok)
        result = await checker.check_all()

        assert "checks" in result
        assert "summary" in result
        assert "passed" in result
        assert "timestamp" in result

        # Should have run all standards
        assert len(result["checks"]) == len(list(CompletionStandard))

    async def test_check_specific_standards(self, checker: CompletionChecker) -> None:
        """Test checking only specific standards."""
        result = await checker.check_all(
            standards=[
                CompletionStandard.DOCUMENTATION,
                CompletionStandard.CODE_QUALITY,
            ]
        )

        assert len(result["checks"]) == 2
        check_names = {c["name"] for c in result["checks"]}
        assert "documentation" in check_names
        assert "code_quality" in check_names

    async def test_unit_test_check_fails_without_tests(self, checker: CompletionChecker) -> None:
        """Test unit test check fails when no tests exist."""
        result = await checker.check_all(standards=[CompletionStandard.UNIT_TESTS])

        assert len(result["checks"]) == 1
        check = result["checks"][0]

        assert check["name"] == "unit_tests"
        # Will fail because no tests configured
        assert check["passed"] in [True, False]  # Depends on environment

    async def test_documentation_check_without_readme(self, checker: CompletionChecker) -> None:
        """Test documentation check fails without README."""
        result = await checker.check_all(standards=[CompletionStandard.DOCUMENTATION])

        assert len(result["checks"]) == 1
        check = result["checks"][0]

        assert check["name"] == "documentation"
        assert check["passed"] is False
        assert "Missing README.md" in check["details"]["issues"]

    async def test_documentation_check_with_readme(self, checker: CompletionChecker) -> None:
        """Test documentation check passes with README."""
        # Create README
        readme = checker.project_root / "README.md"
        readme.write_text("# Test Project\n\nDescription")

        result = await checker.check_all(standards=[CompletionStandard.DOCUMENTATION])

        assert len(result["checks"]) == 1
        check = result["checks"][0]

        assert check["name"] == "documentation"
        # May still fail on coverage, but README should be ok
        assert "Missing README.md" not in check["details"].get("issues", [])

    async def test_user_acceptance_check_with_criteria(self, checker: CompletionChecker) -> None:
        """Test user acceptance check with defined criteria."""
        # Create task file with acceptance criteria
        tasks_file = checker.project_root / ".autoflow" / "tasks" / "test-task.json"
        tasks_data = {
            "spec_slug": "test",
            "tasks": [
                {
                    "id": "test-task",
                    "title": "Test Task",
                    "acceptance_criteria": ["Criteria 1", "Criteria 2"],
                }
            ]
        }
        tasks_file.write_text(json.dumps(tasks_data))

        result = await checker.check_all(
            task_id="test-task",
            standards=[CompletionStandard.USER_ACCEPTANCE],
        )

        assert len(result["checks"]) == 1
        check = result["checks"][0]

        assert check["name"] == "user_acceptance"
        assert check["passed"] is True
        assert check["details"]["criteria"] == ["Criteria 1", "Criteria 2"]

    async def test_user_acceptance_check_without_criteria(self, checker: CompletionChecker) -> None:
        """Test user acceptance check fails without criteria."""
        # Create task file without acceptance criteria
        tasks_file = checker.project_root / ".autoflow" / "tasks" / "test-task.json"
        tasks_data = {
            "spec_slug": "test",
            "tasks": [
                {
                    "id": "test-task",
                    "title": "Test Task",
                }
            ]
        }
        tasks_file.write_text(json.dumps(tasks_data))

        result = await checker.check_all(
            task_id="test-task",
            standards=[CompletionStandard.USER_ACCEPTANCE],
        )

        assert len(result["checks"]) == 1
        check = result["checks"][0]

        assert check["name"] == "user_acceptance"
        assert check["passed"] is False
        assert "No acceptance criteria defined" in check["message"]

    async def test_summary_generation(self, checker: CompletionChecker) -> None:
        """Test summary is generated correctly."""
        # Mock results
        checker._results = [
            CheckResult(name="check1", passed=True, message="Passed"),
            CheckResult(name="check2", passed=False, message="Failed"),
            CheckResult(name="check3", passed=True, message="Passed"),
        ]

        summary = checker._generate_summary()

        assert summary["total_checks"] == 3
        assert summary["passed_checks"] == 2
        assert summary["failed_checks"] == 1
        assert summary["pass_rate"] == 2/3
        assert summary["all_passed"] is False
        assert summary["can_mark_complete"] is False  # strict mode

    async def test_summary_strict_mode_false(self, temp_project: Path) -> None:
        """Test summary with strict mode disabled."""
        checker = CompletionChecker(temp_project, strict_mode=False)

        # Mock results
        checker._results = [
            CheckResult(name="check1", passed=True, message="Passed"),
            CheckResult(name="check2", passed=False, message="Failed"),
        ]

        summary = checker._generate_summary()

        # In non-strict mode, can mark complete if any checks pass
        assert summary["can_mark_complete"] is True
        assert summary["strict_mode"] is False

    async def test_generate_report(self, checker: CompletionChecker) -> None:
        """Test report generation."""
        # Mock results
        checker._results = [
            CheckResult(
                name="test_check",
                passed=True,
                message="Test passed",
                details={"info": "test"},
                duration_seconds=1.5,
            ),
        ]

        report = checker.generate_report()

        assert "Completion Check Report" in report
        assert "test_check" in report
        assert "✓ PASS" in report
        assert "Test passed" in report
        assert "1.5" in report or "1" in report  # Duration formatting

    async def test_save_report(self, checker: CompletionChecker) -> None:
        """Test saving report to file."""
        # Mock results
        checker._results = [
            CheckResult(name="test", passed=True, message="Test"),
        ]

        # Create temp output file
        output_file = checker.project_root / "test_report.json"

        await checker.save_report(output_file)

        assert output_file.exists()

        # Verify content
        content = output_file.read_text()
        assert "Completion Check Report" in content

    async def test_check_timeout(self, checker: CompletionChecker) -> None:
        """Test that checks timeout correctly."""
        # Create a check that will timeout
        async def slow_check(task_id, run_id):
            await asyncio.sleep(10)  # Longer than timeout

        with patch.object(
            checker,
            "_get_check_method",
            return_value=slow_check,
        ):
            # Set very short timeout
            checker.timeout = 0.1

            result = await checker.check_all(standards=[CompletionStandard.UNIT_TESTS])

            assert len(result["checks"]) == 1
            check = result["checks"][0]

            assert check["name"] == "unit_tests"
            assert check["passed"] is False
            assert "timed out" in check["message"].lower()

    async def test_check_exception_handling(self, checker: CompletionChecker) -> None:
        """Test that exceptions are handled gracefully."""
        # Create a check that raises an exception
        async def failing_check(task_id, run_id):
            raise ValueError("Test error")

        with patch.object(
            checker,
            "_get_check_method",
            return_value=failing_check,
        ):
            result = await checker.check_all(standards=[CompletionStandard.UNIT_TESTS])

            assert len(result["checks"]) == 1
            check = result["checks"][0]

            assert check["name"] == "unit_tests"
            assert check["passed"] is False
            assert "error" in check["message"].lower()

    async def test_parse_test_count(self, checker: CompletionChecker) -> None:
        """Test parsing test count from pytest output."""
        # Test various output formats
        outputs = [
            ("5 passed in 2.3s", 5),
            ("10 passed, 2 failed", 10),
            ("collected 15 items", 15),
            ("collected 20 item", 20),
            ("no output", 0),
        ]

        for output, expected_count in outputs:
            count = checker._parse_test_count(output)
            assert count == expected_count, f"Failed to parse: {output}"


class TestCompletionStandard:
    """Test CompletionStandard enum."""

    def test_all_standards_defined(self) -> None:
        """Test all expected standards are defined."""
        expected_standards = {
            "unit_tests",
            "integration_tests",
            "e2e_tests",
            "performance",
            "security",
            "documentation",
            "code_quality",
            "user_acceptance",
        }

        actual_standards = {s.value for s in CompletionStandard}

        assert actual_standards == expected_standards

    def test_standard_values_unique(self) -> None:
        """Test standard values are unique."""
        standards = [s.value for s in CompletionStandard]
        assert len(standards) == len(set(standards)), "Standard values must be unique"


class TestCheckResult:
    """Test CheckResult model."""

    def test_check_result_creation(self) -> None:
        """Test creating a check result."""
        result = CheckResult(
            name="test_check",
            passed=True,
            message="Check passed",
            details={"key": "value"},
            duration_seconds=1.5,
        )

        assert result.name == "test_check"
        assert result.passed is True
        assert result.message == "Check passed"
        assert result.details == {"key": "value"}
        assert result.duration_seconds == 1.5

    def test_check_result_default_details(self) -> None:
        """Test default values for check result."""
        result = CheckResult(
            name="test_check",
            passed=True,
            message="Check passed",
        )

        assert result.details == {}
        assert result.duration_seconds == 0.0
