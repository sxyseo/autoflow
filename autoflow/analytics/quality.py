"""Quality trends tracking for test pass rates and review outcomes.

This module provides comprehensive quality tracking for development workflows,
tracking metrics such as test pass rates, review outcomes, defect trends,
and quality forecasting. It follows the patterns from the analytics system
to provide consistent quality measurements.

The quality tracker helps answer questions like:
- What is our current test pass rate?
- How often are code reviews passing on the first try?
- Is our code quality improving or declining over time?
- Which areas have the most quality issues?
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class TestStatus(str, Enum):
    """Status of a test execution.

    Attributes:
        PASSED: Test executed successfully
        FAILED: Test execution failed
        SKIPPED: Test was skipped
        ERROR: Test had an error during execution
    """

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class ReviewOutcome(str, Enum):
    """Outcome of a code review.

    Attributes:
        APPROVED: Review passed without requiring changes
        NEEDS_CHANGES: Review requires changes before approval
        FAILED: Review failed critically
        PENDING: Review awaiting completion
    """

    APPROVED = "approved"
    NEEDS_CHANGES = "needs_changes"
    FAILED = "failed"
    PENDING = "pending"


class QualityTrend(str, Enum):
    """Quality trend direction.

    Attributes:
        IMPROVING: Quality metrics are improving
        STABLE: Quality metrics are stable
        DECLINING: Quality metrics are declining
        UNKNOWN: Unable to determine trend
    """

    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    UNKNOWN = "unknown"


@dataclass
class TestResult:
    """A record of a test execution result.

    Attributes:
        test_id: Unique identifier for the test or test suite
        status: Status of the test execution
        passed: Number of tests passed
        failed: Number of tests failed
        skipped: Number of tests skipped
        errors: Number of test errors
        total: Total number of tests
        duration: Test execution duration in seconds
        timestamp: When the test was executed (ISO format)
        module: Module or component being tested
        metadata: Additional context about the test
    """

    test_id: str
    status: TestStatus
    passed: int
    failed: int
    skipped: int
    errors: int
    total: int
    duration: float
    timestamp: str
    module: str | None = None
    metadata: dict | None = None

    @property
    def pass_rate(self) -> float:
        """Calculate test pass rate.

        Returns:
            Pass rate as percentage (0-100)
        """
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "test_id": self.test_id,
            "status": self.status.value,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "total": self.total,
            "duration": self.duration,
            "timestamp": self.timestamp,
            "module": self.module,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestResult":
        """Create from dictionary for JSON deserialization."""
        return cls(
            test_id=data["test_id"],
            status=TestStatus(data["status"]),
            passed=data["passed"],
            failed=data["failed"],
            skipped=data["skipped"],
            errors=data["errors"],
            total=data["total"],
            duration=data["duration"],
            timestamp=data["timestamp"],
            module=data.get("module"),
            metadata=data.get("metadata"),
        )


@dataclass
class ReviewRecord:
    """A record of a code review.

    Attributes:
        review_id: Unique identifier for the review
        outcome: Outcome of the review
        attempts: Number of review attempts (1 = first try success)
        files_changed: Number of files in the review
        lines_changed: Number of lines changed
        timestamp: When the review was completed (ISO format)
        reviewer: Reviewer identifier (agent or human)
        module: Module or component being reviewed
        metadata: Additional context about the review
    """

    review_id: str
    outcome: ReviewOutcome
    attempts: int
    files_changed: int
    lines_changed: int
    timestamp: str
    reviewer: str | None = None
    module: str | None = None
    metadata: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "review_id": self.review_id,
            "outcome": self.outcome.value,
            "attempts": self.attempts,
            "files_changed": self.files_changed,
            "lines_changed": self.lines_changed,
            "timestamp": self.timestamp,
            "reviewer": self.reviewer,
            "module": self.module,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewRecord":
        """Create from dictionary for JSON deserialization."""
        return cls(
            review_id=data["review_id"],
            outcome=ReviewOutcome(data["outcome"]),
            attempts=data["attempts"],
            files_changed=data["files_changed"],
            lines_changed=data["lines_changed"],
            timestamp=data["timestamp"],
            reviewer=data.get("reviewer"),
            module=data.get("module"),
            metadata=data.get("metadata"),
        )


@dataclass
class QualityMetrics:
    """Quality metrics for a time period.

    Attributes:
        period_start: Start of the time period (ISO format)
        period_end: End of the time period (ISO format)
        test_pass_rate: Overall test pass rate percentage
        test_total: Total number of tests executed
        review_approval_rate: Review approval rate percentage
        review_first_try_rate: First-try approval rate percentage
        review_total: Total number of reviews
        defect_density: Defects per lines of code
        trend: Overall quality trend direction
        quality_score: Composite quality score (0-100)
    """

    period_start: str
    period_end: str
    test_pass_rate: float
    test_total: int
    review_approval_rate: float
    review_first_try_rate: float
    review_total: int
    defect_density: float
    trend: QualityTrend
    quality_score: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "test_pass_rate": self.test_pass_rate,
            "test_total": self.test_total,
            "review_approval_rate": self.review_approval_rate,
            "review_first_try_rate": self.review_first_try_rate,
            "review_total": self.review_total,
            "defect_density": self.defect_density,
            "trend": self.trend.value,
            "quality_score": self.quality_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityMetrics":
        """Create from dictionary for JSON deserialization."""
        return cls(
            period_start=data["period_start"],
            period_end=data["period_end"],
            test_pass_rate=data["test_pass_rate"],
            test_total=data["test_total"],
            review_approval_rate=data["review_approval_rate"],
            review_first_try_rate=data["review_first_try_rate"],
            review_total=data["review_total"],
            defect_density=data["defect_density"],
            trend=QualityTrend(data["trend"]),
            quality_score=data["quality_score"],
        )


@dataclass
class QualitySummary:
    """Summary statistics for quality data.

    Attributes:
        total_tests: Total number of test executions
        total_reviews: Total number of reviews
        avg_test_pass_rate: Average test pass rate
        avg_review_approval_rate: Average review approval rate
        avg_first_try_rate: Average first-try approval rate
        total_defects: Total number of defects found
        trend: Current quality trend
        quality_score: Current composite quality score
    """

    total_tests: int
    total_reviews: int
    avg_test_pass_rate: float
    avg_review_approval_rate: float
    avg_first_try_rate: float
    total_defects: int
    trend: QualityTrend
    quality_score: float


class QualityTrends:
    """Tracks and analyzes quality trends for test and review metrics.

    This class handles:
    - Recording test results with timestamps
    - Recording review outcomes
    - Calculating quality metrics over time
    - Tracking quality trends and forecasting
    - Persisting quality data to disk

    Quality data is stored in .autoflow/quality_trends.json following
    the strategy memory pattern with atomic writes and proper locking.

    Attributes:
        quality_path: Path to the quality trends JSON file
        test_results: Deque of test results (max 1000 by default)
        review_records: Deque of review records (max 1000 by default)
    """

    # Default quality data file path
    DEFAULT_QUALITY_PATH = Path(".autoflow/quality_trends.json")

    def __init__(
        self,
        quality_path: Path | None = None,
        max_results: int = 1000,
        max_reviews: int = 1000,
        root_dir: Path | None = None,
    ) -> None:
        """Initialize the quality trends tracker.

        Args:
            quality_path: Path to quality trends JSON file.
                If None, uses DEFAULT_QUALITY_PATH
            max_results: Maximum number of test results to keep in memory
            max_reviews: Maximum number of review records to keep in memory
            root_dir: Root directory of the project. Defaults to current directory.
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if quality_path is None:
            quality_path = self.DEFAULT_QUALITY_PATH

        self.quality_path = Path(quality_path)
        self.max_results = max_results
        self.max_reviews = max_reviews

        # Ensure parent directory exists
        self.quality_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data or initialize empty
        self.test_results: deque[TestResult] = deque(maxlen=max_results)
        self.review_records: deque[ReviewRecord] = deque(maxlen=max_reviews)
        self._load_quality_data()

    def record_test_result(self, result: TestResult) -> None:
        """Record a test result.

        Args:
            result: TestResult to record

        Raises:
            IOError: If unable to write quality data to disk
        """
        self.test_results.append(result)
        self._save_quality_data()

    def record_review_outcome(self, review: ReviewRecord) -> None:
        """Record a review outcome.

        Args:
            review: ReviewRecord to record

        Raises:
            IOError: If unable to write quality data to disk
        """
        self.review_records.append(review)
        self._save_quality_data()

    def calculate_test_pass_rate(
        self,
        module: str | None = None,
        since: datetime | None = None,
    ) -> float:
        """Calculate test pass rate.

        Args:
            module: Filter by module name (optional)
            since: Only include tests after this timestamp (optional)

        Returns:
            Pass rate as percentage (0-100), or 0.0 if no tests
        """
        if not self.test_results:
            return 0.0

        total_passed = 0
        total_tests = 0

        for result in self.test_results:
            # Filter by module if specified
            if module and result.module != module:
                continue

            # Filter by timestamp if specified
            if since:
                result_time = datetime.fromisoformat(result.timestamp)
                if result_time < since:
                    continue

            total_passed += result.passed
            total_tests += result.total

        if total_tests == 0:
            return 0.0

        return (total_passed / total_tests) * 100

    def calculate_review_approval_rate(
        self,
        module: str | None = None,
        since: datetime | None = None,
    ) -> float:
        """Calculate review approval rate.

        Args:
            module: Filter by module name (optional)
            since: Only include reviews after this timestamp (optional)

        Returns:
            Approval rate as percentage (0-100), or 0.0 if no reviews
        """
        if not self.review_records:
            return 0.0

        approved = 0
        total = 0

        for review in self.review_records:
            # Filter by module if specified
            if module and review.module != module:
                continue

            # Filter by timestamp if specified
            if since:
                review_time = datetime.fromisoformat(review.timestamp)
                if review_time < since:
                    continue

            if review.outcome == ReviewOutcome.APPROVED:
                approved += 1
            total += 1

        if total == 0:
            return 0.0

        return (approved / total) * 100

    def calculate_first_try_rate(
        self,
        module: str | None = None,
        since: datetime | None = None,
    ) -> float:
        """Calculate first-try approval rate.

        Args:
            module: Filter by module name (optional)
            since: Only include reviews after this timestamp (optional)

        Returns:
            First-try rate as percentage (0-100), or 0.0 if no reviews
        """
        if not self.review_records:
            return 0.0

        first_try = 0
        total = 0

        for review in self.review_records:
            # Filter by module if specified
            if module and review.module != module:
                continue

            # Filter by timestamp if specified
            if since:
                review_time = datetime.fromisoformat(review.timestamp)
                if review_time < since:
                    continue

            if review.outcome == ReviewOutcome.APPROVED and review.attempts == 1:
                first_try += 1
            total += 1

        if total == 0:
            return 0.0

        return (first_try / total) * 100

    def calculate_quality_trend(
        self,
        window_days: int = 7,
    ) -> QualityTrend:
        """Calculate quality trend direction.

        Compares quality metrics from two time windows to determine
        if quality is improving, stable, or declining.

        Args:
            window_days: Size of time windows in days (default 7)

        Returns:
            QualityTrend indicating direction
        """
        if not self.test_results and not self.review_records:
            return QualityTrend.UNKNOWN

        # Calculate timestamps for windows
        now = datetime.now(UTC)
        recent_start = now - timedelta(days=window_days)
        older_start = recent_start - timedelta(days=window_days)

        # Calculate metrics for recent window
        recent_pass_rate = self.calculate_test_pass_rate(since=recent_start)
        recent_approval_rate = self.calculate_review_approval_rate(since=recent_start)
        recent_score = (recent_pass_rate + recent_approval_rate) / 2

        # Calculate metrics for older window
        older_pass_rate = self.calculate_test_pass_rate(since=older_start)
        older_approval_rate = self.calculate_review_approval_rate(since=older_start)
        older_score = (older_pass_rate + older_approval_rate) / 2

        # Determine trend
        diff = recent_score - older_score
        if diff > 5:
            return QualityTrend.IMPROVING
        elif diff < -5:
            return QualityTrend.DECLINING
        else:
            return QualityTrend.STABLE

    def calculate_quality_score(
        self,
        since: datetime | None = None,
    ) -> float:
        """Calculate composite quality score.

        Combines test pass rate and review approval rate into a
        single quality score from 0 to 100.

        Args:
            since: Only include data after this timestamp (optional)

        Returns:
            Quality score from 0 to 100, or 0.0 if no data
        """
        test_pass_rate = self.calculate_test_pass_rate(since=since)
        review_approval_rate = self.calculate_review_approval_rate(since=since)

        # Weighted average (tests are slightly more important)
        return test_pass_rate * 0.6 + review_approval_rate * 0.4

    def get_quality_metrics(
        self,
        period_days: int = 7,
    ) -> QualityMetrics:
        """Get quality metrics for a time period.

        Args:
            period_days: Number of days to look back (default 7)

        Returns:
            QualityMetrics with calculated metrics

        Raises:
            IOError: If unable to read quality data
        """
        # Calculate time window
        now = datetime.now(UTC)
        period_end = now
        period_start = now - timedelta(days=period_days)

        # Calculate metrics
        test_pass_rate = self.calculate_test_pass_rate(since=period_start)
        review_approval_rate = self.calculate_review_approval_rate(since=period_start)
        first_try_rate = self.calculate_first_try_rate(since=period_start)
        trend = self.calculate_quality_trend(window_days=period_days)
        quality_score = self.calculate_quality_score(since=period_start)

        # Count total tests and reviews
        test_total = sum(
            1
            for r in self.test_results
            if datetime.fromisoformat(r.timestamp) >= period_start
        )
        review_total = sum(
            1
            for r in self.review_records
            if datetime.fromisoformat(r.timestamp) >= period_start
        )

        # Calculate defect density (failed tests + needed changes reviews)
        # This is a simplified metric
        failed_tests = sum(
            r.failed
            for r in self.test_results
            if datetime.fromisoformat(r.timestamp) >= period_start
        )
        needed_changes = sum(
            1
            for r in self.review_records
            if datetime.fromisoformat(r.timestamp) >= period_start
            and r.outcome == ReviewOutcome.NEEDS_CHANGES
        )
        total_lines = sum(
            r.lines_changed
            for r in self.review_records
            if datetime.fromisoformat(r.timestamp) >= period_start
        )
        defect_density = (
            (failed_tests + needed_changes) / total_lines if total_lines > 0 else 0.0
        )

        return QualityMetrics(
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            test_pass_rate=test_pass_rate,
            test_total=test_total,
            review_approval_rate=review_approval_rate,
            review_first_try_rate=first_try_rate,
            review_total=review_total,
            defect_density=defect_density,
            trend=trend,
            quality_score=quality_score,
        )

    def get_summary(self) -> QualitySummary:
        """Get comprehensive summary of quality statistics.

        Returns:
            QualitySummary with all statistics

        Raises:
            IOError: If unable to read quality data
        """
        # Count totals
        total_tests = len(self.test_results)
        total_reviews = len(self.review_records)

        # Calculate averages
        avg_test_pass_rate = self.calculate_test_pass_rate()
        avg_review_approval_rate = self.calculate_review_approval_rate()
        avg_first_try_rate = self.calculate_first_try_rate()

        # Count total defects
        total_defects = sum(r.failed for r in self.test_results) + sum(
            1 for r in self.review_records if r.outcome == ReviewOutcome.NEEDS_CHANGES
        )

        # Get current trend and score
        trend = self.calculate_quality_trend()
        quality_score = self.calculate_quality_score()

        return QualitySummary(
            total_tests=total_tests,
            total_reviews=total_reviews,
            avg_test_pass_rate=avg_test_pass_rate,
            avg_review_approval_rate=avg_review_approval_rate,
            avg_first_try_rate=avg_first_try_rate,
            total_defects=total_defects,
            trend=trend,
            quality_score=quality_score,
        )

    def get_module_quality_breakdown(self) -> dict[str, dict[str, float]]:
        """Get quality metrics broken down by module.

        Returns:
            Dictionary mapping module names to quality metrics

        Raises:
            IOError: If unable to read quality data
        """
        modules: dict[str, dict[str, float]] = {}

        # Collect unique modules
        module_names = set()
        for result in self.test_results:
            if result.module:
                module_names.add(result.module)
        for review in self.review_records:
            if review.module:
                module_names.add(review.module)

        # Calculate metrics for each module
        for module in sorted(module_names):
            test_pass_rate = self.calculate_test_pass_rate(module=module)
            review_approval_rate = self.calculate_review_approval_rate(module=module)
            first_try_rate = self.calculate_first_try_rate(module=module)

            modules[module] = {
                "test_pass_rate": test_pass_rate,
                "review_approval_rate": review_approval_rate,
                "first_try_rate": first_try_rate,
                "quality_score": (test_pass_rate * 0.6 + review_approval_rate * 0.4),
            }

        return modules

    def _load_quality_data(self) -> None:
        """Load quality data from disk.

        Reads the quality JSON file and populates the test results
        and review records. Creates an empty file if none exists.
        """
        if not self.quality_path.exists():
            # Create empty quality data file
            self._save_quality_data()
            return

        try:
            data = json.loads(self.quality_path.read_text(encoding="utf-8"))

            # Load test results
            test_results_data = data.get("test_results", [])
            for result_data in test_results_data:
                result = TestResult.from_dict(result_data)
                self.test_results.append(result)

            # Load review records
            review_records_data = data.get("review_records", [])
            for review_data in review_records_data:
                review = ReviewRecord.from_dict(review_data)
                self.review_records.append(review)

        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            # If file is corrupted, start fresh
            self.test_results.clear()
            self.review_records.clear()

    def _save_quality_data(self) -> None:
        """Save quality data to disk.

        Writes the test results and review records to the quality JSON file.
        Uses atomic write to prevent data loss.

        Raises:
            IOError: If unable to write to the quality file
        """
        # Convert records to dictionaries
        test_results_data = [r.to_dict() for r in self.test_results]
        review_records_data = [r.to_dict() for r in self.review_records]

        # Build quality data structure
        quality_data = {
            "test_results": test_results_data,
            "review_records": review_records_data,
            "metadata": {
                "total_test_results": len(self.test_results),
                "total_review_records": len(self.review_records),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }

        # Write to file with atomic update
        temp_path = self.quality_path.with_suffix(".tmp")
        try:
            temp_path.write_text(
                json.dumps(quality_data, indent=2) + "\n", encoding="utf-8"
            )
            temp_path.replace(self.quality_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(
                f"Failed to write quality data to {self.quality_path}: {e}"
            ) from e

    def clear_old_data(self, keep_days: int = 30) -> int:
        """Remove old quality data to manage storage.

        Keeps data from the last N days and removes older data.

        Args:
            keep_days: Number of days of data to keep (default 30)

        Returns:
            Number of records removed

        Raises:
            IOError: If unable to write quality data to disk
        """
        cutoff = datetime.now(UTC) - timedelta(days=keep_days)

        # Filter test results
        initial_tests = len(self.test_results)
        filtered_tests = deque(
            (
                r
                for r in self.test_results
                if datetime.fromisoformat(r.timestamp) >= cutoff
            ),
            maxlen=self.max_results,
        )
        self.test_results = filtered_tests
        removed_tests = initial_tests - len(self.test_results)

        # Filter review records
        initial_reviews = len(self.review_records)
        filtered_reviews = deque(
            (
                r
                for r in self.review_records
                if datetime.fromisoformat(r.timestamp) >= cutoff
            ),
            maxlen=self.max_reviews,
        )
        self.review_records = filtered_reviews
        removed_reviews = initial_reviews - len(self.review_records)

        # Persist changes
        if removed_tests > 0 or removed_reviews > 0:
            self._save_quality_data()

        return removed_tests + removed_reviews

    def export_metrics(self, output_path: Path) -> None:
        """Export quality metrics to a JSON file.

        Args:
            output_path: Path to output file

        Raises:
            IOError: If unable to write metrics to disk
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get current metrics
        summary = self.get_summary()
        metrics = self.get_quality_metrics()
        module_breakdown = self.get_module_quality_breakdown()

        # Build export data
        export_data = {
            "summary": {
                "total_tests": summary.total_tests,
                "total_reviews": summary.total_reviews,
                "avg_test_pass_rate": summary.avg_test_pass_rate,
                "avg_review_approval_rate": summary.avg_review_approval_rate,
                "avg_first_try_rate": summary.avg_first_try_rate,
                "total_defects": summary.total_defects,
                "trend": summary.trend.value,
                "quality_score": summary.quality_score,
            },
            "current_metrics": metrics.to_dict(),
            "module_breakdown": module_breakdown,
            "metadata": {
                "exported_at": datetime.now(UTC).isoformat(),
                "data_period_days": 7,
            },
        }

        # Write to file
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)
