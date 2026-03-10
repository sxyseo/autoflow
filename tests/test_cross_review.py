"""
Unit Tests for Cross-Review System

Tests the CrossReviewer, ReviewFinding, ReviewerResult, and CrossReviewResult
classes for multi-agent code review capabilities.

These tests mock agent adapters to avoid requiring actual AI services
in the test environment.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from autoflow.review import (
    CodeChange,
    CrossReviewer,
    CrossReviewerError,
    CrossReviewerStats,
    CrossReviewResult,
    ReviewerConfig,
    ReviewerResult,
    ReviewFinding,
    ReviewRequest,
    ReviewSeverity,
    ReviewStatus,
    ReviewStrategy,
    create_cross_reviewer,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_adapter() -> MagicMock:
    """Create a mock agent adapter."""
    adapter = MagicMock()
    adapter.execute = AsyncMock(return_value=MagicMock(output="Review complete"))
    return adapter


@pytest.fixture
def sample_code_change() -> dict[str, Any]:
    """Return a sample code change dict."""
    return {
        "file_path": "app.py",
        "diff": """@@ -1,5 +1,7 @@
 def hello():
-    print("Hello")
+    name = "World"
+    print(f"Hello {name}")
     return True
""",
        "change_type": "modify",
    }


@pytest.fixture
def sample_code_change_model() -> CodeChange:
    """Return a sample CodeChange model."""
    return CodeChange(
        file_path="app.py",
        diff="""@@ -1,3 +1,4 @@
 def hello():
     print("Hello")
+    return True
""",
        change_type="modify",
    )


@pytest.fixture
def sample_finding() -> ReviewFinding:
    """Return a sample review finding."""
    return ReviewFinding(
        file_path="app.py",
        line_start=10,
        line_end=12,
        severity=ReviewSeverity.WARNING,
        category="style",
        message="Line too long",
        suggestion="Break into multiple lines",
        reviewer="claude-code",
        confidence=0.85,
    )


@pytest.fixture
def reviewer() -> CrossReviewer:
    """Create a basic CrossReviewer instance for testing."""
    return CrossReviewer()


@pytest.fixture
def configured_reviewer(mock_adapter: MagicMock) -> CrossReviewer:
    """Create a CrossReviewer with registered reviewers."""
    reviewer = CrossReviewer(min_reviewers=1)
    reviewer.register_reviewer("claude-code", mock_adapter)
    reviewer.register_reviewer("codex", mock_adapter)
    return reviewer


# ============================================================================
# ReviewFinding Tests
# ============================================================================


class TestReviewFinding:
    """Tests for ReviewFinding dataclass."""

    def test_finding_init_defaults(self) -> None:
        """Test finding initialization with defaults."""
        finding = ReviewFinding(file_path="test.py")

        assert finding.file_path == "test.py"
        assert finding.line_start is None
        assert finding.line_end is None
        assert finding.severity == ReviewSeverity.INFO
        assert finding.category == "general"
        assert finding.message == ""
        assert finding.confidence == 0.8

    def test_finding_init_full(self) -> None:
        """Test finding initialization with all fields."""
        finding = ReviewFinding(
            file_path="test.py",
            line_start=10,
            line_end=20,
            severity=ReviewSeverity.ERROR,
            category="security",
            message="Potential SQL injection",
            suggestion="Use parameterized queries",
            reviewer="claude-code",
            confidence=0.95,
        )

        assert finding.file_path == "test.py"
        assert finding.line_start == 10
        assert finding.line_end == 20
        assert finding.severity == ReviewSeverity.ERROR
        assert finding.category == "security"
        assert finding.message == "Potential SQL injection"
        assert finding.suggestion == "Use parameterized queries"
        assert finding.reviewer == "claude-code"
        assert finding.confidence == 0.95

    def test_finding_to_dict(self) -> None:
        """Test finding to_dict method."""
        finding = ReviewFinding(
            file_path="test.py",
            line_start=5,
            severity=ReviewSeverity.WARNING,
            category="style",
            message="Test message",
            reviewer="test-reviewer",
        )
        data = finding.to_dict()

        assert data["file_path"] == "test.py"
        assert data["line_start"] == 5
        assert data["severity"] == "warning"
        assert data["category"] == "style"
        assert data["message"] == "Test message"
        assert data["reviewer"] == "test-reviewer"


# ============================================================================
# ReviewerResult Tests
# ============================================================================


class TestReviewerResult:
    """Tests for ReviewerResult dataclass."""

    def test_result_init_defaults(self) -> None:
        """Test result initialization with defaults."""
        result = ReviewerResult(
            reviewer_id="reviewer-123",
            reviewer_type="claude-code",
        )

        assert result.reviewer_id == "reviewer-123"
        assert result.reviewer_type == "claude-code"
        assert result.status == ReviewStatus.PENDING
        assert result.findings == []
        assert result.approved is False
        assert result.confidence == 0.8

    def test_result_blocking_issues(self) -> None:
        """Test blocking_issues property."""
        result = ReviewerResult(
            reviewer_id="test",
            reviewer_type="test",
            findings=[
                ReviewFinding(file_path="a.py", severity=ReviewSeverity.INFO),
                ReviewFinding(file_path="b.py", severity=ReviewSeverity.WARNING),
                ReviewFinding(file_path="c.py", severity=ReviewSeverity.ERROR),
                ReviewFinding(file_path="d.py", severity=ReviewSeverity.CRITICAL),
            ],
        )

        blocking = result.blocking_issues
        assert len(blocking) == 2
        severities = {f.severity for f in blocking}
        assert ReviewSeverity.ERROR in severities
        assert ReviewSeverity.CRITICAL in severities

    def test_result_to_dict(self) -> None:
        """Test result to_dict method."""
        result = ReviewerResult(
            reviewer_id="reviewer-1",
            reviewer_type="claude-code",
            status=ReviewStatus.APPROVED,
            approved=True,
            confidence=0.9,
            comments="Looks good",
        )
        data = result.to_dict()

        assert data["reviewer_id"] == "reviewer-1"
        assert data["reviewer_type"] == "claude-code"
        assert data["status"] == "approved"
        assert data["approved"] is True
        assert data["confidence"] == 0.9
        assert data["comments"] == "Looks good"


# ============================================================================
# CodeChange Tests
# ============================================================================


class TestCodeChange:
    """Tests for CodeChange Pydantic model."""

    def test_change_init_defaults(self) -> None:
        """Test change initialization with defaults."""
        change = CodeChange(file_path="test.py")

        assert change.file_path == "test.py"
        assert change.diff == ""
        assert change.old_content is None
        assert change.new_content is None
        assert change.change_type == "modify"

    def test_change_init_full(self) -> None:
        """Test change initialization with all fields."""
        change = CodeChange(
            file_path="test.py",
            diff="@@ -1 +1 @@",
            old_content="old",
            new_content="new",
            change_type="add",
        )

        assert change.file_path == "test.py"
        assert change.diff == "@@ -1 +1 @@"
        assert change.old_content == "old"
        assert change.new_content == "new"
        assert change.change_type == "add"

    def test_change_from_dict(self) -> None:
        """Test creating change from dict."""
        change = CodeChange(**{
            "file_path": "app.py",
            "diff": "test diff",
            "change_type": "modify",
        })

        assert change.file_path == "app.py"
        assert change.diff == "test diff"


# ============================================================================
# ReviewRequest Tests
# ============================================================================


class TestReviewRequest:
    """Tests for ReviewRequest Pydantic model."""

    def test_request_init_defaults(self) -> None:
        """Test request initialization with defaults."""
        request = ReviewRequest()

        assert request.changes == []
        assert request.author_agent == "unknown"
        assert request.target_branch == "main"
        assert request.review_strategy == ReviewStrategy.MAJORITY
        assert request.timeout_seconds == 300

    def test_request_with_changes(self) -> None:
        """Test request with code changes."""
        request = ReviewRequest(
            changes=[
                CodeChange(file_path="a.py", diff="diff a"),
                CodeChange(file_path="b.py", diff="diff b"),
            ],
            author_agent="implementer",
            review_strategy=ReviewStrategy.CONSENSUS,
        )

        assert len(request.changes) == 2
        assert request.author_agent == "implementer"
        assert request.review_strategy == ReviewStrategy.CONSENSUS


# ============================================================================
# CrossReviewResult Tests
# ============================================================================


class TestCrossReviewResult:
    """Tests for CrossReviewResult dataclass."""

    def test_result_init_defaults(self) -> None:
        """Test result initialization with defaults."""
        result = CrossReviewResult()

        assert result.status == ReviewStatus.PENDING
        assert result.approved is False
        assert result.reviewer_results == []
        assert result.aggregated_findings == []
        assert result.consensus_score == 0.0

    def test_result_blocking_issues(self) -> None:
        """Test blocking_issues property."""
        result = CrossReviewResult()
        result.aggregated_findings = [
            ReviewFinding(file_path="a.py", severity=ReviewSeverity.INFO),
            ReviewFinding(file_path="b.py", severity=ReviewSeverity.ERROR),
            ReviewFinding(file_path="c.py", severity=ReviewSeverity.CRITICAL),
        ]

        assert len(result.blocking_issues) == 2

    def test_result_warnings(self) -> None:
        """Test warnings property."""
        result = CrossReviewResult()
        result.aggregated_findings = [
            ReviewFinding(file_path="a.py", severity=ReviewSeverity.INFO),
            ReviewFinding(file_path="b.py", severity=ReviewSeverity.WARNING),
            ReviewFinding(file_path="c.py", severity=ReviewSeverity.WARNING),
        ]

        assert len(result.warnings) == 2

    def test_result_reviewer_count(self) -> None:
        """Test reviewer_count property."""
        result = CrossReviewResult()
        result.reviewer_results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="claude-code"),
            ReviewerResult(reviewer_id="r2", reviewer_type="codex"),
        ]

        assert result.reviewer_count == 2

    def test_result_approval_count(self) -> None:
        """Test approval_count property."""
        result = CrossReviewResult()
        result.reviewer_results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="a", approved=True),
            ReviewerResult(reviewer_id="r2", reviewer_type="b", approved=True),
            ReviewerResult(reviewer_id="r3", reviewer_type="c", approved=False),
        ]

        assert result.approval_count == 2

    def test_result_mark_complete(self) -> None:
        """Test mark_complete method."""
        result = CrossReviewResult()
        result.mark_complete(
            status=ReviewStatus.APPROVED,
            approved=True,
        )

        assert result.status == ReviewStatus.APPROVED
        assert result.approved is True
        assert result.completed_at is not None
        assert result.duration_seconds is not None

    def test_result_to_dict(self) -> None:
        """Test to_dict method."""
        result = CrossReviewResult(
            review_id="review-123",
            status=ReviewStatus.APPROVED,
            approved=True,
            consensus_score=0.85,
        )
        data = result.to_dict()

        assert data["review_id"] == "review-123"
        assert data["status"] == "approved"
        assert data["approved"] is True
        assert data["consensus_score"] == 0.85


# ============================================================================
# ReviewerConfig Tests
# ============================================================================


class TestReviewerConfig:
    """Tests for ReviewerConfig Pydantic model."""

    def test_config_init_defaults(self) -> None:
        """Test config initialization with defaults."""
        config = ReviewerConfig(agent_type="claude-code")

        assert config.agent_type == "claude-code"
        assert config.enabled is True
        assert config.weight == 1.0
        assert config.timeout_seconds == 120
        assert config.focus_areas == []
        assert config.exclude_patterns == []

    def test_config_custom(self) -> None:
        """Test config with custom values."""
        config = ReviewerConfig(
            agent_type="codex",
            enabled=False,
            weight=2.0,
            timeout_seconds=300,
            focus_areas=["security", "performance"],
            exclude_patterns=["tests/", "docs/"],
        )

        assert config.agent_type == "codex"
        assert config.enabled is False
        assert config.weight == 2.0
        assert config.focus_areas == ["security", "performance"]
        assert config.exclude_patterns == ["tests/", "docs/"]


# ============================================================================
# CrossReviewerStats Tests
# ============================================================================


class TestCrossReviewerStats:
    """Tests for CrossReviewerStats Pydantic model."""

    def test_stats_init_defaults(self) -> None:
        """Test stats initialization with defaults."""
        stats = CrossReviewerStats()

        assert stats.total_reviews == 0
        assert stats.approved_reviews == 0
        assert stats.rejected_reviews == 0
        assert stats.failed_reviews == 0
        assert stats.total_findings == 0
        assert stats.blocking_findings == 0


# ============================================================================
# CrossReviewer Initialization Tests
# ============================================================================


class TestCrossReviewerInit:
    """Tests for CrossReviewer initialization."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        reviewer = CrossReviewer()

        assert reviewer.default_strategy == ReviewStrategy.MAJORITY
        assert reviewer.min_reviewers == 2
        assert len(reviewer.list_reviewers()) == 0

    def test_init_custom_strategy(self) -> None:
        """Test initialization with custom strategy."""
        reviewer = CrossReviewer(default_strategy=ReviewStrategy.CONSENSUS)

        assert reviewer.default_strategy == ReviewStrategy.CONSENSUS

    def test_init_custom_min_reviewers(self) -> None:
        """Test initialization with custom min_reviewers."""
        reviewer = CrossReviewer(min_reviewers=1)

        assert reviewer.min_reviewers == 1

    def test_init_with_reviewer_configs(self) -> None:
        """Test initialization with reviewer configs."""
        configs = {
            "claude-code": ReviewerConfig(
                agent_type="claude-code",
                focus_areas=["security"],
            ),
        }
        reviewer = CrossReviewer(reviewer_configs=configs)

        config = reviewer.get_reviewer_config("claude-code")
        assert config.focus_areas == ["security"]


# ============================================================================
# CrossReviewer Registration Tests
# ============================================================================


class TestCrossReviewerRegistration:
    """Tests for CrossReviewer registration methods."""

    def test_register_reviewer(self, reviewer: CrossReviewer, mock_adapter: MagicMock) -> None:
        """Test registering a reviewer."""
        reviewer.register_reviewer("claude-code", mock_adapter)

        assert "claude-code" in reviewer.list_reviewers()

    def test_register_reviewer_with_config(
        self,
        reviewer: CrossReviewer,
        mock_adapter: MagicMock,
    ) -> None:
        """Test registering a reviewer with config."""
        config = ReviewerConfig(
            agent_type="claude-code",
            focus_areas=["security"],
        )
        reviewer.register_reviewer("claude-code", mock_adapter, config=config)

        stored_config = reviewer.get_reviewer_config("claude-code")
        assert stored_config.focus_areas == ["security"]

    def test_unregister_reviewer(self, reviewer: CrossReviewer, mock_adapter: MagicMock) -> None:
        """Test unregistering a reviewer."""
        reviewer.register_reviewer("claude-code", mock_adapter)
        result = reviewer.unregister_reviewer("claude-code")

        assert result is True
        assert "claude-code" not in reviewer.list_reviewers()

    def test_unregister_reviewer_not_found(self, reviewer: CrossReviewer) -> None:
        """Test unregistering a non-existent reviewer."""
        result = reviewer.unregister_reviewer("nonexistent")
        assert result is False

    def test_list_reviewers(self, reviewer: CrossReviewer, mock_adapter: MagicMock) -> None:
        """Test listing reviewers."""
        reviewer.register_reviewer("claude-code", mock_adapter)
        reviewer.register_reviewer("codex", mock_adapter)

        reviewers = reviewer.list_reviewers()
        assert len(reviewers) == 2
        assert "claude-code" in reviewers
        assert "codex" in reviewers

    def test_get_reviewer_config_default(self, reviewer: CrossReviewer) -> None:
        """Test getting config for unconfigured reviewer."""
        config = reviewer.get_reviewer_config("unknown-reviewer")

        assert config.agent_type == "unknown-reviewer"
        assert config.enabled is True  # Default values


# ============================================================================
# CrossReviewer Available Reviewers Tests
# ============================================================================


class TestCrossReviewerAvailableReviewers:
    """Tests for CrossReviewer get_available_reviewers method."""

    def test_get_available_reviewers(
        self,
        configured_reviewer: CrossReviewer,
    ) -> None:
        """Test getting available reviewers."""
        available = configured_reviewer.get_available_reviewers()

        assert len(available) == 2
        assert "claude-code" in available
        assert "codex" in available

    def test_get_available_reviewers_exclude_author(
        self,
        configured_reviewer: CrossReviewer,
    ) -> None:
        """Test getting available reviewers excluding author."""
        available = configured_reviewer.get_available_reviewers(
            exclude_agents=["claude-code"]
        )

        assert len(available) == 1
        assert "codex" in available
        assert "claude-code" not in available

    def test_get_available_reviewers_exclude_disabled(
        self,
        reviewer: CrossReviewer,
        mock_adapter: MagicMock,
    ) -> None:
        """Test that disabled reviewers are excluded."""
        reviewer.register_reviewer(
            "claude-code",
            mock_adapter,
            config=ReviewerConfig(agent_type="claude-code", enabled=True),
        )
        reviewer.register_reviewer(
            "codex",
            mock_adapter,
            config=ReviewerConfig(agent_type="codex", enabled=False),
        )

        available = reviewer.get_available_reviewers()
        assert len(available) == 1
        assert "claude-code" in available


# ============================================================================
# CrossReviewer Review Code Tests
# ============================================================================


class TestCrossReviewerReviewCode:
    """Tests for CrossReviewer.review_code method."""

    @pytest.mark.asyncio
    async def test_review_code_insufficient_reviewers(
        self,
        reviewer: CrossReviewer,
        sample_code_change: dict[str, Any],
    ) -> None:
        """Test review with insufficient reviewers."""
        with pytest.raises(CrossReviewerError) as exc_info:
            await reviewer.review_code(
                changes=[sample_code_change],
                author_agent="implementer",
            )

        assert "Insufficient reviewers" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_review_code_with_dict_changes(
        self,
        configured_reviewer: CrossReviewer,
        sample_code_change: dict[str, Any],
    ) -> None:
        """Test review with dict changes."""
        result = await configured_reviewer.review_code(
            changes=[sample_code_change],
            author_agent="implementer",
            strategy=ReviewStrategy.SINGLE,
        )

        assert result.status in (ReviewStatus.APPROVED, ReviewStatus.CHANGES_REQUESTED)
        assert result.reviewer_count >= 1

    @pytest.mark.asyncio
    async def test_review_code_with_model_changes(
        self,
        configured_reviewer: CrossReviewer,
        sample_code_change_model: CodeChange,
    ) -> None:
        """Test review with CodeChange model."""
        result = await configured_reviewer.review_code(
            changes=[sample_code_change_model],
            author_agent="implementer",
            strategy=ReviewStrategy.SINGLE,
        )

        assert result.status in (ReviewStatus.APPROVED, ReviewStatus.CHANGES_REQUESTED)

    @pytest.mark.asyncio
    async def test_review_code_invalid_change_type(
        self,
        configured_reviewer: CrossReviewer,
    ) -> None:
        """Test review with invalid change type."""
        with pytest.raises(CrossReviewerError) as exc_info:
            await configured_reviewer.review_code(
                changes=["not a valid change"],  # type: ignore
                author_agent="implementer",
            )

        assert "Invalid change type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_review_code_timeout(
        self,
        configured_reviewer: CrossReviewer,
        sample_code_change: dict[str, Any],
    ) -> None:
        """Test review that times out."""
        # Very short timeout
        result = await configured_reviewer.review_code(
            changes=[sample_code_change],
            author_agent="implementer",
            strategy=ReviewStrategy.SINGLE,
            timeout_seconds=0,  # Immediate timeout
        )

        assert result.status == ReviewStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_review_code_strategy_override(
        self,
        configured_reviewer: CrossReviewer,
        sample_code_change: dict[str, Any],
    ) -> None:
        """Test review with strategy override."""
        result = await configured_reviewer.review_code(
            changes=[sample_code_change],
            author_agent="implementer",
            strategy=ReviewStrategy.CONSENSUS,
        )

        assert result.strategy_used == ReviewStrategy.CONSENSUS


# ============================================================================
# CrossReviewer Approval Strategy Tests
# ============================================================================


class TestCrossReviewerApprovalStrategies:
    """Tests for approval strategy logic."""

    def test_determine_approval_consensus(self, reviewer: CrossReviewer) -> None:
        """Test consensus strategy."""
        # All approved
        results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="a", approved=True),
            ReviewerResult(reviewer_id="r2", reviewer_type="b", approved=True),
        ]
        approved = reviewer._determine_approval(
            results,
            ReviewStrategy.CONSENSUS,
            [],
        )
        assert approved is True

        # One disapproved
        results[1].approved = False
        approved = reviewer._determine_approval(
            results,
            ReviewStrategy.CONSENSUS,
            [],
        )
        assert approved is False

    def test_determine_approval_majority(self, reviewer: CrossReviewer) -> None:
        """Test majority strategy."""
        results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="a", approved=True),
            ReviewerResult(reviewer_id="r2", reviewer_type="b", approved=True),
            ReviewerResult(reviewer_id="r3", reviewer_type="c", approved=False),
        ]
        approved = reviewer._determine_approval(
            results,
            ReviewStrategy.MAJORITY,
            [],
        )
        assert approved is True

    def test_determine_approval_single(self, reviewer: CrossReviewer) -> None:
        """Test single strategy."""
        results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="a", approved=True),
            ReviewerResult(reviewer_id="r2", reviewer_type="b", approved=False),
        ]
        approved = reviewer._determine_approval(
            results,
            ReviewStrategy.SINGLE,
            [],
        )
        assert approved is True

        # No approvals
        results[0].approved = False
        approved = reviewer._determine_approval(
            results,
            ReviewStrategy.SINGLE,
            [],
        )
        assert approved is False

    def test_determine_approval_weighted(self, reviewer: CrossReviewer) -> None:
        """Test weighted strategy."""
        results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="a", approved=True, confidence=0.9),
            ReviewerResult(reviewer_id="r2", reviewer_type="b", approved=False, confidence=0.5),
        ]
        approved = reviewer._determine_approval(
            results,
            ReviewStrategy.WEIGHTED,
            [],
        )
        # 0.9 > 0.5/2, so should be approved
        assert approved is True

    def test_determine_approval_with_blocking_findings(self, reviewer: CrossReviewer) -> None:
        """Test that blocking findings prevent approval."""
        results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="a", approved=True),
        ]
        findings = [
            ReviewFinding(file_path="a.py", severity=ReviewSeverity.ERROR),
        ]
        approved = reviewer._determine_approval(
            results,
            ReviewStrategy.CONSENSUS,
            findings,
        )
        assert approved is False


# ============================================================================
# CrossReviewer Finding Aggregation Tests
# ============================================================================


class TestCrossReviewerFindingAggregation:
    """Tests for finding aggregation logic."""

    def test_aggregate_findings(self, reviewer: CrossReviewer) -> None:
        """Test aggregating findings from multiple reviewers."""
        results = [
            ReviewerResult(
                reviewer_id="r1",
                reviewer_type="a",
                findings=[
                    ReviewFinding(file_path="a.py", line_start=10, message="Issue 1"),
                    ReviewFinding(file_path="b.py", line_start=5, message="Issue 2"),
                ],
            ),
            ReviewerResult(
                reviewer_id="r2",
                reviewer_type="b",
                findings=[
                    ReviewFinding(file_path="a.py", line_start=10, message="Issue 1"),  # Duplicate
                    ReviewFinding(file_path="c.py", line_start=1, message="Issue 3"),
                ],
            ),
        ]

        aggregated = reviewer._aggregate_findings(results)

        # Should have 3 unique findings (Issue 1 deduplicated)
        assert len(aggregated) == 3

    def test_aggregate_findings_confidence_boost(self, reviewer: CrossReviewer) -> None:
        """Test that corroborating findings boost confidence."""
        results = [
            ReviewerResult(
                reviewer_id="r1",
                reviewer_type="a",
                findings=[
                    ReviewFinding(
                        file_path="a.py",
                        line_start=10,
                        message="Same issue",
                        confidence=0.7,
                    ),
                ],
            ),
            ReviewerResult(
                reviewer_id="r2",
                reviewer_type="b",
                findings=[
                    ReviewFinding(
                        file_path="a.py",
                        line_start=10,
                        message="Same issue",
                        confidence=0.7,
                    ),
                ],
            ),
        ]

        aggregated = reviewer._aggregate_findings(results)

        # Confidence should be boosted due to corroboration
        assert len(aggregated) == 1
        assert aggregated[0].confidence > 0.7

    def test_aggregate_findings_sorted_by_severity(self, reviewer: CrossReviewer) -> None:
        """Test that findings are sorted by severity."""
        results = [
            ReviewerResult(
                reviewer_id="r1",
                reviewer_type="a",
                findings=[
                    ReviewFinding(file_path="a.py", severity=ReviewSeverity.INFO),
                    ReviewFinding(file_path="b.py", severity=ReviewSeverity.CRITICAL),
                    ReviewFinding(file_path="c.py", severity=ReviewSeverity.WARNING),
                ],
            ),
        ]

        aggregated = reviewer._aggregate_findings(results)

        assert aggregated[0].severity == ReviewSeverity.CRITICAL
        assert aggregated[1].severity == ReviewSeverity.WARNING
        assert aggregated[2].severity == ReviewSeverity.INFO


# ============================================================================
# CrossReviewer Consensus Calculation Tests
# ============================================================================


class TestCrossReviewerConsensusCalculation:
    """Tests for consensus calculation logic."""

    def test_calculate_consensus_unanimous(self, reviewer: CrossReviewer) -> None:
        """Test consensus with unanimous approval."""
        results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="a", approved=True, confidence=0.9),
            ReviewerResult(reviewer_id="r2", reviewer_type="b", approved=True, confidence=0.9),
        ]

        consensus = reviewer._calculate_consensus(results)

        # 100% approval * 0.9 avg confidence
        assert consensus == pytest.approx(0.9, rel=0.01)

    def test_calculate_consensus_split(self, reviewer: CrossReviewer) -> None:
        """Test consensus with split decision."""
        results = [
            ReviewerResult(reviewer_id="r1", reviewer_type="a", approved=True, confidence=0.8),
            ReviewerResult(reviewer_id="r2", reviewer_type="b", approved=False, confidence=0.8),
        ]

        consensus = reviewer._calculate_consensus(results)

        # 50% approval * 0.8 avg confidence
        assert consensus == pytest.approx(0.4, rel=0.01)

    def test_calculate_consensus_empty(self, reviewer: CrossReviewer) -> None:
        """Test consensus with no results."""
        consensus = reviewer._calculate_consensus([])

        assert consensus == 0.0


# ============================================================================
# CrossReviewer Security Checks Tests
# ============================================================================


class TestCrossReviewerSecurityChecks:
    """Tests for security issue detection."""

    def test_check_security_issues_password(self, reviewer: CrossReviewer) -> None:
        """Test detection of hardcoded password."""
        content = '''
password = "secret123"
api_key = "abc123"
'''
        findings = reviewer._check_security_issues(
            content,
            "config.py",
            "reviewer",
        )

        # Should find potential issues
        assert len(findings) > 0
        assert any("password" in f.message.lower() or "api_key" in f.message.lower() for f in findings)

    def test_check_security_issues_eval(self, reviewer: CrossReviewer) -> None:
        """Test detection of eval() usage."""
        content = "result = eval(user_input)"
        findings = reviewer._check_security_issues(
            content,
            "dangerous.py",
            "reviewer",
        )

        assert any("eval" in f.message.lower() for f in findings)

    def test_check_security_issues_safe_code(self, reviewer: CrossReviewer) -> None:
        """Test no findings for safe code."""
        content = '''
def greet(name):
    return f"Hello, {name}"
'''
        findings = reviewer._check_security_issues(
            content,
            "safe.py",
            "reviewer",
        )

        # Should have no security findings
        assert len(findings) == 0


# ============================================================================
# CrossReviewer Code Quality Checks Tests
# ============================================================================


class TestCrossReviewerCodeQualityChecks:
    """Tests for code quality issue detection."""

    def test_check_code_quality_long_lines(self, reviewer: CrossReviewer) -> None:
        """Test detection of long lines."""
        content = "x = " + "a" * 150  # Very long line
        findings = reviewer._check_code_quality(
            content,
            "long.py",
            "reviewer",
        )

        assert any("120" in f.message for f in findings)

    def test_check_code_quality_todo_without_issue(self, reviewer: CrossReviewer) -> None:
        """Test detection of TODO without issue reference."""
        content = "# TODO fix this later"
        findings = reviewer._check_code_quality(
            content,
            "todo.py",
            "reviewer",
        )

        assert any("TODO" in f.message for f in findings)

    def test_check_code_quality_todo_with_issue(self, reviewer: CrossReviewer) -> None:
        """Test no findings for TODO with issue reference."""
        content = "# TODO #123 fix this later"
        findings = reviewer._check_code_quality(
            content,
            "todo.py",
            "reviewer",
        )

        # Should not flag TODO with issue reference
        assert not any("TODO" in f.message for f in findings)


# ============================================================================
# CrossReviewer Statistics Tests
# ============================================================================


class TestCrossReviewerStatistics:
    """Tests for review statistics tracking."""

    def test_stats_initial(self, reviewer: CrossReviewer) -> None:
        """Test initial statistics."""
        stats = reviewer.stats

        assert stats.total_reviews == 0
        assert stats.approved_reviews == 0

    def test_stats_updated_on_review(
        self,
        configured_reviewer: CrossReviewer,
        sample_code_change: dict[str, Any],
    ) -> None:
        """Test statistics updated after review."""

        async def run_review() -> CrossReviewResult:
            return await configured_reviewer.review_code(
                changes=[sample_code_change],
                author_agent="implementer",
                strategy=ReviewStrategy.SINGLE,
            )

        # Run review
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_review())
        finally:
            loop.close()

        stats = configured_reviewer.stats
        assert stats.total_reviews == 1
        assert stats.last_review_at is not None


# ============================================================================
# CrossReviewer Active Reviews Tests
# ============================================================================


class TestCrossReviewerActiveReviews:
    """Tests for active review management."""

    def test_get_active_reviews_empty(self, reviewer: CrossReviewer) -> None:
        """Test getting active reviews when none are active."""
        active = reviewer.get_active_reviews()

        assert active == []

    def test_get_review_not_found(self, reviewer: CrossReviewer) -> None:
        """Test getting a non-existent review."""
        result = reviewer.get_review("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_review_not_found(self, reviewer: CrossReviewer) -> None:
        """Test cancelling a non-existent review."""
        result = await reviewer.cancel_review("nonexistent")
        assert result is False


# ============================================================================
# CrossReviewer Representation Tests
# ============================================================================


class TestCrossReviewerRepr:
    """Tests for CrossReviewer string representation."""

    def test_repr_empty(self, reviewer: CrossReviewer) -> None:
        """Test repr of empty reviewer."""
        repr_str = repr(reviewer)

        assert "CrossReviewer" in repr_str
        assert "reviewers=0" in repr_str
        assert "majority" in repr_str

    def test_repr_with_reviewers(
        self,
        configured_reviewer: CrossReviewer,
    ) -> None:
        """Test repr with registered reviewers."""
        repr_str = repr(configured_reviewer)

        assert "reviewers=2" in repr_str


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestCreateCrossReviewer:
    """Tests for create_cross_reviewer factory function."""

    def test_create_empty(self) -> None:
        """Test creating empty reviewer."""
        reviewer = create_cross_reviewer()

        assert isinstance(reviewer, CrossReviewer)
        assert len(reviewer.list_reviewers()) == 0

    def test_create_with_reviewers(self, mock_adapter: MagicMock) -> None:
        """Test creating reviewer with pre-registered reviewers."""
        reviewer = create_cross_reviewer(
            reviewers={
                "claude-code": mock_adapter,
                "codex": mock_adapter,
            },
        )

        assert len(reviewer.list_reviewers()) == 2

    def test_create_with_strategy(self) -> None:
        """Test creating reviewer with custom strategy."""
        reviewer = create_cross_reviewer(
            strategy=ReviewStrategy.CONSENSUS,
        )

        assert reviewer.default_strategy == ReviewStrategy.CONSENSUS

    def test_create_with_min_reviewers(self) -> None:
        """Test creating reviewer with custom min_reviewers."""
        reviewer = create_cross_reviewer(min_reviewers=1)

        assert reviewer.min_reviewers == 1


# ============================================================================
# ReviewSeverity Tests
# ============================================================================


class TestReviewSeverity:
    """Tests for ReviewSeverity enum."""

    def test_severity_values(self) -> None:
        """Test severity enum values."""
        assert ReviewSeverity.INFO.value == "info"
        assert ReviewSeverity.WARNING.value == "warning"
        assert ReviewSeverity.ERROR.value == "error"
        assert ReviewSeverity.CRITICAL.value == "critical"

    def test_severity_ordering(self) -> None:
        """Test severity ordering for sorting."""
        # Lower value = more severe (for sorting)
        severities = [
            ReviewSeverity.INFO,
            ReviewSeverity.WARNING,
            ReviewSeverity.ERROR,
            ReviewSeverity.CRITICAL,
        ]
        # Just verify they exist and are distinct
        assert len(set(severities)) == 4


# ============================================================================
# ReviewStatus Tests
# ============================================================================


class TestReviewStatus:
    """Tests for ReviewStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert ReviewStatus.PENDING.value == "pending"
        assert ReviewStatus.IN_PROGRESS.value == "in_progress"
        assert ReviewStatus.APPROVED.value == "approved"
        assert ReviewStatus.CHANGES_REQUESTED.value == "changes_requested"
        assert ReviewStatus.FAILED.value == "failed"
        assert ReviewStatus.TIMEOUT.value == "timeout"


# ============================================================================
# ReviewStrategy Tests
# ============================================================================


class TestReviewStrategy:
    """Tests for ReviewStrategy enum."""

    def test_strategy_values(self) -> None:
        """Test strategy enum values."""
        assert ReviewStrategy.CONSENSUS.value == "consensus"
        assert ReviewStrategy.MAJORITY.value == "majority"
        assert ReviewStrategy.SINGLE.value == "single"
        assert ReviewStrategy.WEIGHTED.value == "weighted"


# ============================================================================
# Edge Cases Tests
# ============================================================================


class TestCrossReviewerEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_review_empty_changes(
        self,
        configured_reviewer: CrossReviewer,
    ) -> None:
        """Test review with no changes."""
        result = await configured_reviewer.review_code(
            changes=[],
            author_agent="implementer",
            strategy=ReviewStrategy.SINGLE,
        )

        # Should complete without error
        assert result.status in (ReviewStatus.APPROVED, ReviewStatus.CHANGES_REQUESTED)

    @pytest.mark.asyncio
    async def test_review_large_diff(
        self,
        configured_reviewer: CrossReviewer,
    ) -> None:
        """Test review with large diff."""
        large_change = {
            "file_path": "large.py",
            "diff": "+" + "\n".join([f"line {i}" for i in range(1000)]),
        }

        result = await configured_reviewer.review_code(
            changes=[large_change],
            author_agent="implementer",
            strategy=ReviewStrategy.SINGLE,
        )

        # Should handle large diffs
        assert result.status in (ReviewStatus.APPROVED, ReviewStatus.CHANGES_REQUESTED)

    def test_build_review_prompt_with_focus_areas(
        self,
        reviewer: CrossReviewer,
        sample_code_change_model: CodeChange,
    ) -> None:
        """Test review prompt includes focus areas."""
        config = ReviewerConfig(
            agent_type="test",
            focus_areas=["security", "performance"],
        )
        prompt = reviewer._build_review_prompt(
            [sample_code_change_model],
            config,
        )

        assert "security" in prompt
        assert "performance" in prompt

    def test_generate_review_summary_no_findings(self, reviewer: CrossReviewer) -> None:
        """Test summary generation with no findings."""
        summary = reviewer._generate_review_summary([])

        assert "No issues found" in summary

    def test_generate_review_summary_with_findings(self, reviewer: CrossReviewer) -> None:
        """Test summary generation with findings."""
        findings = [
            ReviewFinding(file_path="a.py", severity=ReviewSeverity.ERROR),
            ReviewFinding(file_path="b.py", severity=ReviewSeverity.WARNING),
            ReviewFinding(file_path="c.py", severity=ReviewSeverity.INFO),
        ]
        summary = reviewer._generate_review_summary(findings)

        assert "3" in summary
        assert "error" in summary
        assert "warning" in summary
        assert "info" in summary

    def test_analyze_changes_excluded_patterns(
        self,
        reviewer: CrossReviewer,
    ) -> None:
        """Test that excluded patterns are skipped."""

        config = ReviewerConfig(
            agent_type="test",
            exclude_patterns=["tests/"],
        )

        changes = [
            CodeChange(file_path="app/main.py", diff="x = 1"),
            CodeChange(file_path="tests/test_main.py", diff="x = 1"),
        ]

        async def run_analyze() -> list[ReviewFinding]:
            return await reviewer._analyze_changes(changes, config, "test")

        findings = asyncio.new_event_loop().run_until_complete(run_analyze())

        # tests/ should be excluded
        for f in findings:
            assert not f.file_path.startswith("tests/")
