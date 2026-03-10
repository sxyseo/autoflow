#!/usr/bin/env python3
"""
Autoflow QA Findings Module

Provides structured QA findings with severity levels and fix suggestions.
Integrates with the verification system to track issues and generate fix tasks.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SeverityLevel(Enum):
    """
    Severity levels for QA findings.

    Levels:
        CRITICAL: Must fix before commit (blocks)
        HIGH: Should fix before commit (blocks)
        MEDIUM: Warning (doesn't block)
        LOW: Info only (doesn't block)
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def blocks_commit(self) -> bool:
        """
        Check if this severity level blocks commits.

        Returns:
            True if this severity blocks commits
        """
        return self in [SeverityLevel.CRITICAL, SeverityLevel.HIGH]

    @classmethod
    def from_string(cls, value: str) -> "SeverityLevel":
        """
        Parse severity level from string.

        Args:
            value: String representation of severity

        Returns:
            SeverityLevel enum value

        Raises:
            ValueError: If string is not a valid severity level
        """
        try:
            return cls(value.lower())
        except ValueError:
            valid = [s.value for s in cls]
            raise ValueError(
                f"Invalid severity level '{value}'. "
                f"Must be one of: {', '.join(valid)}"
            ) from None


@dataclass
class QAFinding:
    """
    A single QA finding.

    Args:
        file: File path where issue was found
        line: Line number where issue occurs
        column: Column number (optional)
        severity: Severity level of the finding
        category: Category of issue (e.g., "test", "coverage", "style")
        message: Human-readable description of the issue
        suggested_fix: Suggested fix for the issue
        context: Additional context or code snippet
        rule_id: Identifier for the rule that triggered this finding
    """

    file: str
    line: int
    severity: SeverityLevel
    message: str
    category: str
    suggested_fix: str | None = None
    column: int | None = None
    context: str | None = None
    rule_id: str | None = None

    def to_dict(self) -> dict:
        """Convert finding to dictionary for JSON serialization."""
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "context": self.context,
            "rule_id": self.rule_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QAFinding":
        """
        Create finding from dictionary.

        Args:
            data: Dictionary with finding data

        Returns:
            QAFinding instance
        """
        return cls(
            file=data["file"],
            line=data["line"],
            column=data.get("column"),
            severity=SeverityLevel.from_string(data["severity"]),
            category=data["category"],
            message=data["message"],
            suggested_fix=data.get("suggested_fix"),
            context=data.get("context"),
            rule_id=data.get("rule_id"),
        )

    def __str__(self) -> str:
        """Return string representation of finding."""
        location = f"{self.file}:{self.line}"
        if self.column:
            location += f":{self.column}"

        return f"[{self.severity.value.upper()}] {location}: {self.message}"


@dataclass
class QAFindingReport:
    """
    Collection of QA findings.

    Args:
        findings: List of QA findings
        timestamp: Report generation timestamp
        source: Source of the findings (e.g., "test", "coverage", "lint")
    """

    findings: list[QAFinding] = field(default_factory=list)
    timestamp: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        """Convert report to dictionary for JSON serialization."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "timestamp": self.timestamp,
            "source": self.source,
            "summary": self.get_summary(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QAFindingReport":
        """
        Create report from dictionary.

        Args:
            data: Dictionary with report data

        Returns:
            QAFindingReport instance
        """
        return cls(
            findings=[QAFinding.from_dict(f) for f in data.get("findings", [])],
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
        )

    def add_finding(self, finding: QAFinding) -> None:
        """
        Add a finding to the report.

        Args:
            finding: QAFinding to add
        """
        self.findings.append(finding)

    def get_findings_by_severity(self, severity: SeverityLevel) -> list[QAFinding]:
        """
        Get all findings of a specific severity level.

        Args:
            severity: Severity level to filter by

        Returns:
            List of findings with the specified severity
        """
        return [f for f in self.findings if f.severity == severity]

    def get_blocking_findings(self) -> list[QAFinding]:
        """
        Get all findings that block commits.

        Returns:
            List of CRITICAL and HIGH severity findings
        """
        return [f for f in self.findings if f.severity.blocks_commit()]

    def get_findings_by_file(self, file_path: str) -> list[QAFinding]:
        """
        Get all findings for a specific file.

        Args:
            file_path: File path to filter by

        Returns:
            List of findings for the specified file
        """
        return [f for f in self.findings if f.file == file_path]

    def get_summary(self) -> dict[str, int]:
        """
        Get summary statistics of findings.

        Returns:
            Dictionary with count of findings per severity level
        """
        summary = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": len(self.findings),
        }

        for finding in self.findings:
            summary[finding.severity.value] += 1

        return summary

    def has_blocking_findings(self) -> bool:
        """
        Check if report contains any blocking findings.

        Returns:
            True if there are CRITICAL or HIGH severity findings
        """
        return any(f.severity.blocks_commit() for f in self.findings)

    def get_unique_files(self) -> list[str]:
        """
        Get list of unique files with findings.

        Returns:
            Sorted list of unique file paths
        """
        return sorted({f.file for f in self.findings})


class QAFindingsManager:
    """
    Manager for QA findings collection and persistence.

    Provides functionality to create, store, and load QA findings reports.
    """

    def __init__(self, work_dir: str = "."):
        """
        Initialize QA findings manager.

        Args:
            work_dir: Working directory for findings storage
        """
        self.work_dir = Path(work_dir)

    def create_report(self, source: str = "") -> QAFindingReport:
        """
        Create a new QA findings report.

        Args:
            source: Source of the findings

        Returns:
            New QAFindingReport instance
        """
        return QAFindingReport(source=source)

    def save_report(self, report: QAFindingReport, output_path: str) -> None:
        """
        Save QA findings report to file.

        Args:
            report: QAFindingReport to save
            output_path: Path to output file
        """
        output_file = self.work_dir / output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

    def load_report(self, input_path: str) -> QAFindingReport:
        """
        Load QA findings report from file.

        Args:
            input_path: Path to input file

        Returns:
            QAFindingReport with loaded data
        """
        input_file = self.work_dir / input_path

        with open(input_file) as f:
            data = json.load(f)

        return QAFindingReport.from_dict(data)

    def parse_test_failure(
        self,
        test_name: str,
        error_message: str,
        file_path: str,
        line_number: int | None = None,
    ) -> QAFinding:
        """
        Parse test failure into QA finding.

        Args:
            test_name: Name of the failing test
            error_message: Error message from test failure
            file_path: Path to the test file
            line_number: Line number where failure occurred

        Returns:
            QAFinding representing the test failure
        """
        # Test failures are typically HIGH severity
        return QAFinding(
            file=file_path,
            line=line_number or 0,
            severity=SeverityLevel.HIGH,
            category="test",
            message=f"Test failure: {test_name}",
            suggested_fix=error_message,
            context=test_name,
            rule_id="test-failure",
        )

    def parse_coverage_gap(
        self, file_path: str, coverage_percent: float, threshold: float
    ) -> QAFinding:
        """
        Parse coverage gap into QA finding.

        Args:
            file_path: Path to the file with low coverage
            coverage_percent: Actual coverage percentage
            threshold: Required coverage threshold

        Returns:
            QAFinding representing the coverage gap
        """
        # Coverage gaps are HIGH severity if below threshold
        return QAFinding(
            file=file_path,
            line=0,
            severity=SeverityLevel.HIGH,
            category="coverage",
            message=f"Coverage below threshold: {coverage_percent:.1f}% < {threshold:.1f}%",
            suggested_fix=f"Add tests to increase coverage to at least {threshold:.1f}%",
            context=f"Current: {coverage_percent:.1f}%, Required: {threshold:.1f}%",
            rule_id="coverage-threshold",
        )

    def merge_reports(
        self, reports: list[QAFindingReport], source: str = "merged"
    ) -> QAFindingReport:
        """
        Merge multiple QA findings reports into one.

        Args:
            reports: List of reports to merge
            source: Source name for merged report

        Returns:
            Merged QAFindingReport
        """
        merged = QAFindingReport(source=source)

        for report in reports:
            merged.findings.extend(report.findings)

        # Sort findings by severity and file
        severity_order = {
            SeverityLevel.CRITICAL: 0,
            SeverityLevel.HIGH: 1,
            SeverityLevel.MEDIUM: 2,
            SeverityLevel.LOW: 3,
        }

        merged.findings.sort(key=lambda f: (severity_order[f.severity], f.file, f.line))

        return merged
