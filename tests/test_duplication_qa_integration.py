"""
Integration Tests for Duplication Detection QA Findings

Tests the integration between the duplication detection system
and the QA findings system. Verifies that duplication findings
can be converted to QA findings format and reported correctly.

These tests ensure the duplication detector integrates properly
with the existing QA infrastructure for unified issue tracking.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoflow.analysis.duplication_detector import (
    DuplicationFinding,
    DuplicationReport,
    DuplicationThreshold,
)
from autoflow.review.qa_findings import (
    QAFinding,
    QAFindingReport,
    QAFindingsManager,
    SeverityLevel,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_finding() -> DuplicationFinding:
    """Create a sample duplication finding for testing."""
    return DuplicationFinding(
        file="src/module.py",
        line_start=10,
        line_end=20,
        similarity=0.85,
        duplicated_in="src/other.py",
        duplicated_line_start=30,
        duplicated_line_end=40,
        snippet="def example():\n    pass",
        category="structural",
    )


@pytest.fixture
def sample_report() -> DuplicationReport:
    """Create a sample duplication report with multiple findings."""
    return DuplicationReport(
        findings=[
            DuplicationFinding(
                file="src/module.py",
                line_start=10,
                line_end=20,
                similarity=0.95,
                duplicated_in="src/other.py",
                duplicated_line_start=30,
                duplicated_line_end=40,
                snippet="def example():\n    pass",
                category="structural",
            ),
            DuplicationFinding(
                file="src/utils.py",
                line_start=5,
                line_end=15,
                similarity=0.75,
                duplicated_in="src/helpers.py",
                duplicated_line_start=20,
                duplicated_line_end=30,
                snippet="def helper():\n    return True",
                category="token",
            ),
        ],
        total_duplication=0.85,
        files_analyzed=4,
    )


@pytest.fixture
def temp_workdir(tmp_path: Path) -> Path:
    """Create a temporary working directory."""
    workdir = tmp_path / "project"
    workdir.mkdir()
    return workdir


@pytest.fixture
def qa_manager(temp_workdir: Path) -> QAFindingsManager:
    """Create a QA findings manager for testing."""
    return QAFindingsManager(work_dir=str(temp_workdir))


# ============================================================================
# DuplicationFinding to QAFinding Tests
# ============================================================================


class TestDuplicationFindingToQAFinding:
    """Tests for DuplicationFinding.to_qa_finding() method."""

    def test_convert_to_qa_finding_success(self, sample_finding: DuplicationFinding) -> None:
        """Test successful conversion of duplication finding to QA finding."""
        qa_finding = sample_finding.to_qa_finding()

        assert qa_finding is not None
        assert isinstance(qa_finding, QAFinding)
        assert qa_finding.file == "src/module.py"
        assert qa_finding.line == 10
        assert qa_finding.category == "duplication-structural"

    def test_severity_mapping_critical(self) -> None:
        """Test that similarity >= 0.9 maps to CRITICAL severity."""
        finding = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.95,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None
        assert qa_finding.severity == SeverityLevel.CRITICAL
        assert qa_finding.severity.blocks_commit() is True

    def test_severity_mapping_high(self) -> None:
        """Test that similarity >= 0.8 maps to HIGH severity."""
        finding = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.85,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None
        assert qa_finding.severity == SeverityLevel.HIGH
        assert qa_finding.severity.blocks_commit() is True

    def test_severity_mapping_medium(self) -> None:
        """Test that similarity >= 0.7 maps to MEDIUM severity."""
        finding = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.75,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None
        assert qa_finding.severity == SeverityLevel.MEDIUM
        assert qa_finding.severity.blocks_commit() is False

    def test_severity_mapping_low(self) -> None:
        """Test that similarity < 0.7 maps to LOW severity."""
        finding = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.65,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None
        assert qa_finding.severity == SeverityLevel.LOW
        assert qa_finding.severity.blocks_commit() is False

    def test_message_formatting(self, sample_finding: DuplicationFinding) -> None:
        """Test that the QA finding message is formatted correctly."""
        qa_finding = sample_finding.to_qa_finding()

        assert qa_finding is not None
        assert "85.0% similar" in qa_finding.message
        assert "src/other.py:30-40" in qa_finding.message
        assert "Code duplication detected" in qa_finding.message

    def test_suggested_fix_formatting(self, sample_finding: DuplicationFinding) -> None:
        """Test that the suggested fix is formatted correctly."""
        qa_finding = sample_finding.to_qa_finding()

        assert qa_finding is not None
        assert "Extract duplicated code" in qa_finding.suggested_fix
        assert "src/module.py:10-20" in qa_finding.suggested_fix
        assert "85.0% similar" in qa_finding.suggested_fix

    def test_context_preserved(self, sample_finding: DuplicationFinding) -> None:
        """Test that the code snippet is preserved as context."""
        qa_finding = sample_finding.to_qa_finding()

        assert qa_finding is not None
        assert qa_finding.context == "def example():\n    pass"

    def test_rule_id(self, sample_finding: DuplicationFinding) -> None:
        """Test that the rule ID is set correctly."""
        qa_finding = sample_finding.to_qa_finding()

        assert qa_finding is not None
        assert qa_finding.rule_id == "duplication-detector"

    def test_category_includes_duplication_prefix(self, sample_finding: DuplicationFinding) -> None:
        """Test that category is prefixed with 'duplication-'."""
        qa_finding = sample_finding.to_qa_finding()

        assert qa_finding is not None
        assert qa_finding.category.startswith("duplication-")

    def test_column_is_none(self, sample_finding: DuplicationFinding) -> None:
        """Test that column is None (not used in duplication findings)."""
        qa_finding = sample_finding.to_qa_finding()

        assert qa_finding is not None
        assert qa_finding.column is None


# ============================================================================
# DuplicationReport to QAFindingReport Tests
# ============================================================================


class TestDuplicationReportToQAFindingReport:
    """Tests for DuplicationReport.to_qa_report() method."""

    def test_convert_to_qa_report_success(self, sample_report: DuplicationReport) -> None:
        """Test successful conversion of duplication report to QA report."""
        qa_report = sample_report.to_qa_report()

        assert qa_report is not None
        assert isinstance(qa_report, QAFindingReport)
        assert qa_report.source == "duplication-detection"

    def test_qa_report_contains_all_findings(self, sample_report: DuplicationReport) -> None:
        """Test that all findings are converted to QA findings."""
        qa_report = sample_report.to_qa_report()

        assert qa_report is not None
        assert len(qa_report.findings) == 2

    def test_qa_report_timestamp_preserved(self, sample_report: DuplicationReport) -> None:
        """Test that timestamp is preserved in QA report."""
        qa_report = sample_report.to_qa_report()

        assert qa_report is not None
        assert qa_report.timestamp == sample_report.timestamp

    def test_qa_report_empty_findings(self) -> None:
        """Test conversion of report with no findings."""
        report = DuplicationReport(
            findings=[],
            total_duplication=0.0,
            files_analyzed=0,
        )

        qa_report = report.to_qa_report()

        assert qa_report is not None
        assert len(qa_report.findings) == 0

    def test_qa_report_summary(self, sample_report: DuplicationReport) -> None:
        """Test that QA report summary is calculated correctly."""
        qa_report = sample_report.to_qa_report()

        assert qa_report is not None
        summary = qa_report.get_summary()

        # One critical (95%), one medium (75%)
        assert summary["critical"] == 1
        assert summary["high"] == 0
        assert summary["medium"] == 1
        assert summary["low"] == 0
        assert summary["total"] == 2

    def test_qa_report_has_blocking_findings(self, sample_report: DuplicationReport) -> None:
        """Test that blocking findings are detected correctly."""
        qa_report = sample_report.to_qa_report()

        assert qa_report is not None
        assert qa_report.has_blocking_findings() is True

    def test_qa_report_get_blocking_findings(self, sample_report: DuplicationReport) -> None:
        """Test getting only blocking findings from QA report."""
        qa_report = sample_report.to_qa_report()

        assert qa_report is not None
        blocking = qa_report.get_blocking_findings()

        # Should have 1 critical finding
        assert len(blocking) == 1
        assert blocking[0].severity == SeverityLevel.CRITICAL

    def test_qa_report_get_unique_files(self, sample_report: DuplicationReport) -> None:
        """Test getting unique files from QA report."""
        qa_report = sample_report.to_qa_report()

        assert qa_report is not None
        files = qa_report.get_unique_files()

        # QA findings only track source files where duplications are found
        # not the files they're duplicated in
        assert len(files) == 2
        assert "src/module.py" in files
        assert "src/utils.py" in files


# ============================================================================
# QAFindingsManager Integration Tests
# ============================================================================


class TestQAFindingsManagerIntegration:
    """Tests for QAFindingsManager with duplication findings."""

    def test_save_duplication_qa_report(
        self, temp_workdir: Path, qa_manager: QAFindingsManager
    ) -> None:
        """Test saving a duplication QA report to file."""
        report = DuplicationReport(
            findings=[
                DuplicationFinding(
                    file="test.py",
                    line_start=1,
                    line_end=10,
                    similarity=0.85,
                    duplicated_in="other.py",
                    duplicated_line_start=20,
                    duplicated_line_end=30,
                    snippet="code",
                )
            ],
            total_duplication=0.85,
            files_analyzed=2,
        )

        qa_report = report.to_qa_report()
        assert qa_report is not None

        qa_manager.save_report(qa_report, "reports/duplication.json")

        # Verify file was created
        output_file = temp_workdir / "reports" / "duplication.json"
        assert output_file.exists()

    def test_load_duplication_qa_report(
        self, temp_workdir: Path, qa_manager: QAFindingsManager
    ) -> None:
        """Test loading a duplication QA report from file."""
        # First, save a report
        report = DuplicationReport(
            findings=[
                DuplicationFinding(
                    file="test.py",
                    line_start=1,
                    line_end=10,
                    similarity=0.85,
                    duplicated_in="other.py",
                    duplicated_line_start=20,
                    duplicated_line_end=30,
                    snippet="code",
                )
            ],
            total_duplication=0.85,
            files_analyzed=2,
        )

        qa_report = report.to_qa_report()
        assert qa_report is not None

        qa_manager.save_report(qa_report, "reports/duplication.json")

        # Now load it back
        loaded_report = qa_manager.load_report("reports/duplication.json")

        assert loaded_report.source == "duplication-detection"
        assert len(loaded_report.findings) == 1
        assert loaded_report.findings[0].file == "test.py"

    def test_merge_duplication_reports(
        self, qa_manager: QAFindingsManager
    ) -> None:
        """Test merging multiple duplication QA reports."""
        report1 = DuplicationReport(
            findings=[
                DuplicationFinding(
                    file="test1.py",
                    line_start=1,
                    line_end=10,
                    similarity=0.85,
                    duplicated_in="other1.py",
                    duplicated_line_start=20,
                    duplicated_line_end=30,
                    snippet="code1",
                )
            ],
            total_duplication=0.85,
            files_analyzed=2,
        )

        report2 = DuplicationReport(
            findings=[
                DuplicationFinding(
                    file="test2.py",
                    line_start=5,
                    line_end=15,
                    similarity=0.75,
                    duplicated_in="other2.py",
                    duplicated_line_start=25,
                    duplicated_line_end=35,
                    snippet="code2",
                )
            ],
            total_duplication=0.75,
            files_analyzed=2,
        )

        qa_report1 = report1.to_qa_report()
        qa_report2 = report2.to_qa_report()

        assert qa_report1 is not None and qa_report2 is not None

        merged = qa_manager.merge_reports([qa_report1, qa_report2])

        assert len(merged.findings) == 2
        assert merged.source == "merged"


# ============================================================================
# End-to-End Integration Tests
# ============================================================================


class TestEndToEndIntegration:
    """End-to-end tests for duplication detection QA integration."""

    def test_full_workflow_duplication_to_qa(self) -> None:
        """Test full workflow from duplication detection to QA report."""
        # Create duplication findings
        findings = [
            DuplicationFinding(
                file="src/auth.py",
                line_start=15,
                line_end=25,
                similarity=0.92,
                duplicated_in="src/user.py",
                duplicated_line_start=40,
                duplicated_line_end=50,
                snippet="def validate_token(token):\n    return token.startswith('Bearer')",
                category="structural",
            ),
            DuplicationFinding(
                file="src/utils.py",
                line_start=8,
                line_end=18,
                similarity=0.78,
                duplicated_in="src/helpers.py",
                duplicated_line_start=12,
                duplicated_line_end=22,
                snippet="def format_date(date):\n    return date.strftime('%Y-%m-%d')",
                category="token",
            ),
        ]

        # Create duplication report
        dup_report = DuplicationReport(
            findings=findings,
            total_duplication=0.85,
            files_analyzed=4,
        )

        # Convert to QA report
        qa_report = dup_report.to_qa_report()
        assert qa_report is not None

        # Verify QA report properties
        assert qa_report.source == "duplication-detection"
        assert len(qa_report.findings) == 2

        # Verify severity mapping
        critical_findings = qa_report.get_findings_by_severity(SeverityLevel.CRITICAL)
        medium_findings = qa_report.get_findings_by_severity(SeverityLevel.MEDIUM)

        assert len(critical_findings) == 1
        assert len(medium_findings) == 1

        # Verify blocking findings
        assert qa_report.has_blocking_findings() is True
        blocking = qa_report.get_blocking_findings()
        assert len(blocking) == 1

        # Verify file tracking (QA findings only track source files)
        files = qa_report.get_unique_files()
        assert len(files) == 2
        assert "src/auth.py" in files
        assert "src/utils.py" in files

    def test_duplicate_findings_with_different_categories(
        self, qa_manager: QAFindingsManager
    ) -> None:
        """Test that different duplication categories are preserved."""
        findings = [
            DuplicationFinding(
                file="test.py",
                line_start=1,
                line_end=10,
                similarity=0.85,
                duplicated_in="other.py",
                duplicated_line_start=20,
                duplicated_line_end=30,
                snippet="code",
                category="structural",
            ),
            DuplicationFinding(
                file="test2.py",
                line_start=5,
                line_end=15,
                similarity=0.80,
                duplicated_in="other2.py",
                duplicated_line_start=25,
                duplicated_line_end=35,
                snippet="code2",
                category="token",
            ),
        ]

        report = DuplicationReport(
            findings=findings,
            total_duplication=0.825,
            files_analyzed=4,
        )

        qa_report = report.to_qa_report()
        assert qa_report is not None

        # Check that categories are preserved
        categories = {f.category for f in qa_report.findings}
        assert "duplication-structural" in categories
        assert "duplication-token" in categories

    def test_qa_finding_serialization_roundtrip(
        self, temp_workdir: Path, qa_manager: QAFindingsManager
    ) -> None:
        """Test that QA findings from duplication can be serialized and deserialized."""
        finding = DuplicationFinding(
            file="src/module.py",
            line_start=10,
            line_end=20,
            similarity=0.88,
            duplicated_in="src/other.py",
            duplicated_line_start=30,
            duplicated_line_end=40,
            snippet="def example():\n    pass",
            category="structural",
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None

        # Convert to dict
        finding_dict = qa_finding.to_dict()

        # Verify dict structure
        assert finding_dict["file"] == "src/module.py"
        assert finding_dict["line"] == 10
        assert finding_dict["severity"] == "high"
        assert finding_dict["category"] == "duplication-structural"

        # Create report and save
        report = QAFindingReport(
            findings=[qa_finding],
            source="duplication-detection",
        )

        qa_manager.save_report(report, "test.json")

        # Load and verify
        loaded = qa_manager.load_report("test.json")
        assert len(loaded.findings) == 1
        assert loaded.findings[0].file == "src/module.py"
        assert loaded.findings[0].severity == SeverityLevel.HIGH


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and error handling in QA integration."""

    def test_exact_similarity_threshold_boundary(self) -> None:
        """Test severity mapping at exact threshold boundaries."""
        # Test 0.9 boundary (should be CRITICAL)
        finding1 = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.90,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )
        qa_finding1 = finding1.to_qa_finding()
        assert qa_finding1 is not None
        assert qa_finding1.severity == SeverityLevel.CRITICAL

        # Test 0.8 boundary (should be HIGH)
        finding2 = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.80,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )
        qa_finding2 = finding2.to_qa_finding()
        assert qa_finding2 is not None
        assert qa_finding2.severity == SeverityLevel.HIGH

        # Test 0.7 boundary (should be MEDIUM)
        finding3 = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.70,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )
        qa_finding3 = finding3.to_qa_finding()
        assert qa_finding3 is not None
        assert qa_finding3.severity == SeverityLevel.MEDIUM

    def test_very_high_similarity(self) -> None:
        """Test finding with very high similarity (near 1.0)."""
        finding = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.99,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None
        assert qa_finding.severity == SeverityLevel.CRITICAL
        assert "99.0% similar" in qa_finding.message

    def test_very_low_similarity(self) -> None:
        """Test finding with very low similarity (near 0.0)."""
        finding = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.51,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None
        assert qa_finding.severity == SeverityLevel.LOW
        assert qa_finding.severity.blocks_commit() is False

    def test_multiline_snippet_preservation(self) -> None:
        """Test that multiline code snippets are preserved correctly."""
        snippet = """def complex_function(arg1, arg2):
    result = arg1 + arg2
    if result > 0:
        return True
    return False"""

        finding = DuplicationFinding(
            file="test.py",
            line_start=1,
            line_end=10,
            similarity=0.85,
            duplicated_in="other.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet=snippet,
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None
        assert qa_finding.context == snippet

    def test_special_characters_in_message(self) -> None:
        """Test handling of special characters in file paths."""
        finding = DuplicationFinding(
            file="src/module-name.py",
            line_start=1,
            line_end=10,
            similarity=0.85,
            duplicated_in="src/other-module.py",
            duplicated_line_start=20,
            duplicated_line_end=30,
            snippet="code",
        )

        qa_finding = finding.to_qa_finding()
        assert qa_finding is not None
        # The message includes the duplicated_in location
        assert "other-module.py" in qa_finding.message
        # The suggested fix includes the source file
        assert "module-name.py" in qa_finding.suggested_fix
