"""
Autoflow Cross-Review Module

Provides multi-agent code review capabilities where AI agents review
each other's code before merging. This implements a peer review system
for autonomous development, ensuring code quality through automated
cross-validation.

Usage:
    from autoflow.review.cross_review import CrossReviewer

    reviewer = CrossReviewer()
    result = await reviewer.review_code(
        changes=[{"file": "app.py", "diff": "..."}],
        author_agent="claude-code"
    )

    if result.approved:
        print("Code approved for merge")
    else:
        print(f"Issues found: {result.issues}")
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ReviewStatus(StrEnum):
    """Status of a code review."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ReviewSeverity(StrEnum):
    """Severity levels for review findings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReviewStrategy(StrEnum):
    """
    Strategy for cross-review execution.

    - CONSENSUS: All reviewers must approve
    - MAJORITY: Majority of reviewers must approve
    - SINGLE: Any single approval is sufficient
    - WEIGHTED: Weighted voting based on reviewer confidence
    """

    CONSENSUS = "consensus"
    MAJORITY = "majority"
    SINGLE = "single"
    WEIGHTED = "weighted"


@dataclass
class ReviewFinding:
    """
    A single finding from a code review.

    Attributes:
        file_path: Path to the file with the issue
        line_start: Starting line number
        line_end: Ending line number
        severity: Severity level of the finding
        category: Category (e.g., "security", "style", "logic")
        message: Description of the issue
        suggestion: Optional suggested fix
        reviewer: Agent that found this issue
        confidence: Confidence level (0.0 to 1.0)
    """

    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    severity: ReviewSeverity = ReviewSeverity.INFO
    category: str = "general"
    message: str = ""
    suggestion: str | None = None
    reviewer: str = ""
    confidence: float = 0.8

    def to_dict(self) -> dict[str, Any]:
        """Convert finding to dictionary."""
        return {
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "suggestion": self.suggestion,
            "reviewer": self.reviewer,
            "confidence": self.confidence,
        }


@dataclass
class ReviewerResult:
    """
    Result from a single reviewer agent.

    Attributes:
        reviewer_id: ID of the reviewer agent
        reviewer_type: Type of agent (e.g., "claude-code", "codex")
        status: Review status from this reviewer
        findings: List of findings from this reviewer
        approved: Whether this reviewer approved the changes
        confidence: Overall confidence in the review (0.0 to 1.0)
        comments: General comments from the reviewer
        duration_seconds: Time taken for review
        error: Error message if review failed
    """

    reviewer_id: str
    reviewer_type: str
    status: ReviewStatus = ReviewStatus.PENDING
    findings: list[ReviewFinding] = field(default_factory=list)
    approved: bool = False
    confidence: float = 0.8
    comments: str | None = None
    duration_seconds: float | None = None
    error: str | None = None

    @property
    def blocking_issues(self) -> list[ReviewFinding]:
        """Get findings that block approval."""
        return [
            f
            for f in self.findings
            if f.severity in (ReviewSeverity.ERROR, ReviewSeverity.CRITICAL)
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "reviewer_id": self.reviewer_id,
            "reviewer_type": self.reviewer_type,
            "status": self.status.value,
            "findings": [f.to_dict() for f in self.findings],
            "approved": self.approved,
            "confidence": self.confidence,
            "comments": self.comments,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


class CodeChange(BaseModel):
    """
    Model representing a code change to be reviewed.

    Attributes:
        file_path: Path to the changed file
        diff: The diff content (unified diff format)
        old_content: Previous content (for context)
        new_content: New content (for context)
        change_type: Type of change (add, modify, delete, rename)
    """

    file_path: str
    diff: str = ""
    old_content: str | None = None
    new_content: str | None = None
    change_type: str = "modify"


class ReviewRequest(BaseModel):
    """
    Request model for initiating a code review.

    Attributes:
        changes: List of code changes to review
        author_agent: Agent that authored the changes
        target_branch: Branch to merge into
        review_strategy: Strategy for approval
        timeout_seconds: Maximum time for review
        metadata: Additional metadata
    """

    changes: list[CodeChange] = Field(default_factory=list)
    author_agent: str = "unknown"
    target_branch: str = "main"
    review_strategy: ReviewStrategy = ReviewStrategy.MAJORITY
    timeout_seconds: int = 300
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class CrossReviewResult:
    """
    Aggregated result from cross-review by multiple agents.

    Attributes:
        review_id: Unique identifier for this review
        status: Overall review status
        approved: Whether changes are approved for merge
        reviewer_results: Individual results from each reviewer
        aggregated_findings: All findings merged and deduplicated
        consensus_score: Score based on reviewer agreement (0.0 to 1.0)
        strategy_used: Strategy used for approval decision
        started_at: When review started
        completed_at: When review completed
        duration_seconds: Total review duration
        error: Error message if review failed
        metadata: Additional metadata
    """

    review_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: ReviewStatus = ReviewStatus.PENDING
    approved: bool = False
    reviewer_results: list[ReviewerResult] = field(default_factory=list)
    aggregated_findings: list[ReviewFinding] = field(default_factory=list)
    consensus_score: float = 0.0
    strategy_used: ReviewStrategy = ReviewStrategy.MAJORITY
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking_issues(self) -> list[ReviewFinding]:
        """Get all findings that block approval."""
        return [
            f
            for f in self.aggregated_findings
            if f.severity in (ReviewSeverity.ERROR, ReviewSeverity.CRITICAL)
        ]

    @property
    def warnings(self) -> list[ReviewFinding]:
        """Get all warning-level findings."""
        return [
            f for f in self.aggregated_findings if f.severity == ReviewSeverity.WARNING
        ]

    @property
    def reviewer_count(self) -> int:
        """Get number of reviewers."""
        return len(self.reviewer_results)

    @property
    def approval_count(self) -> int:
        """Get number of approving reviewers."""
        return sum(1 for r in self.reviewer_results if r.approved)

    def mark_complete(
        self,
        status: ReviewStatus,
        approved: bool = False,
        error: str | None = None,
    ) -> None:
        """
        Mark the review as complete.

        Args:
            status: Final review status
            approved: Whether changes are approved
            error: Error message if any
        """
        self.status = status
        self.approved = approved
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "review_id": self.review_id,
            "status": self.status.value,
            "approved": self.approved,
            "reviewer_count": self.reviewer_count,
            "approval_count": self.approval_count,
            "consensus_score": self.consensus_score,
            "strategy_used": self.strategy_used.value,
            "blocking_issues": len(self.blocking_issues),
            "warnings": len(self.warnings),
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "reviewer_results": [r.to_dict() for r in self.reviewer_results],
            "aggregated_findings": [f.to_dict() for f in self.aggregated_findings],
            "metadata": self.metadata,
        }


class CrossReviewerError(Exception):
    """Exception raised for cross-review errors."""

    def __init__(
        self,
        message: str,
        review_id: str | None = None,
        reviewer: str | None = None,
    ):
        self.review_id = review_id
        self.reviewer = reviewer
        super().__init__(message)


class ReviewerConfig(BaseModel):
    """
    Configuration for a reviewer agent.

    Attributes:
        agent_type: Type of agent (e.g., "claude-code", "codex")
        enabled: Whether this reviewer is active
        weight: Weight for weighted voting strategy
        timeout_seconds: Timeout for this reviewer
        focus_areas: Areas this reviewer should focus on
        exclude_patterns: File patterns to exclude from review
    """

    agent_type: str
    enabled: bool = True
    weight: float = 1.0
    timeout_seconds: int = 120
    focus_areas: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)


class CrossReviewerStats(BaseModel):
    """Statistics about cross-review operations."""

    total_reviews: int = 0
    approved_reviews: int = 0
    rejected_reviews: int = 0
    failed_reviews: int = 0
    total_findings: int = 0
    blocking_findings: int = 0
    average_review_duration: float = 0.0
    average_reviewers_per_review: float = 0.0
    last_review_at: datetime | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)


class CrossReviewer:
    """
    Multi-agent code review orchestrator.

    The CrossReviewer coordinates code review by multiple AI agents,
    implementing a peer review system for autonomous development.
    Each agent reviews the code changes independently, and results
    are aggregated based on the configured strategy.

    Key features:
    - Multiple reviewer agents review code in parallel
    - Configurable approval strategies (consensus, majority, etc.)
    - Finding aggregation and deduplication
    - Confidence-weighted voting
    - Review history tracking

    Example:
        >>> from autoflow.review.cross_review import CrossReviewer
        >>> from autoflow.agents.claude_code import ClaudeCodeAdapter
        >>> from autoflow.agents.codex import CodexAdapter
        >>>
        >>> reviewer = CrossReviewer()
        >>> reviewer.register_reviewer("claude-code", ClaudeCodeAdapter())
        >>> reviewer.register_reviewer("codex", CodexAdapter())
        >>>
        >>> result = await reviewer.review_code(
        ...     changes=[{"file_path": "app.py", "diff": "..."}],
        ...     author_agent="implementer"
        ... )
        >>>
        >>> if result.approved:
        ...     print("Ready to merge!")
        ... else:
        ...     print(f"Blocking issues: {len(result.blocking_issues)}")

    Attributes:
        default_strategy: Default review strategy
        default_timeout: Default timeout for reviews
        min_reviewers: Minimum number of reviewers required
        stats: Review statistics
    """

    DEFAULT_STRATEGY = ReviewStrategy.MAJORITY
    DEFAULT_TIMEOUT = 300
    DEFAULT_MIN_REVIEWERS = 2
    DEFAULT_REVIEWER_TIMEOUT = 120

    def __init__(
        self,
        default_strategy: ReviewStrategy | None = None,
        default_timeout: int | None = None,
        min_reviewers: int | None = None,
        reviewer_configs: dict[str, ReviewerConfig] | None = None,
    ):
        """
        Initialize the cross-reviewer.

        Args:
            default_strategy: Default approval strategy
            default_timeout: Default total review timeout
            min_reviewers: Minimum reviewers required
            reviewer_configs: Configurations for specific reviewers
        """
        self._default_strategy = default_strategy or self.DEFAULT_STRATEGY
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT
        self._min_reviewers = min_reviewers or self.DEFAULT_MIN_REVIEWERS
        self._reviewer_configs = reviewer_configs or {}
        self._reviewers: dict[str, Any] = {}  # agent_type -> adapter
        self._stats = CrossReviewerStats()
        self._active_reviews: dict[str, CrossReviewResult] = {}

    @property
    def stats(self) -> CrossReviewerStats:
        """Get review statistics."""
        return self._stats

    @property
    def default_strategy(self) -> ReviewStrategy:
        """Get default strategy."""
        return self._default_strategy

    @property
    def min_reviewers(self) -> int:
        """Get minimum reviewers required."""
        return self._min_reviewers

    def register_reviewer(
        self,
        agent_type: str,
        adapter: Any,
        config: ReviewerConfig | None = None,
    ) -> None:
        """
        Register a reviewer agent.

        Args:
            agent_type: Type identifier for this reviewer
            adapter: Agent adapter instance
            config: Optional reviewer configuration
        """
        self._reviewers[agent_type] = adapter
        if config:
            self._reviewer_configs[agent_type] = config

    def unregister_reviewer(self, agent_type: str) -> bool:
        """
        Unregister a reviewer agent.

        Args:
            agent_type: Type identifier to unregister

        Returns:
            True if reviewer was removed, False if not found
        """
        if agent_type in self._reviewers:
            del self._reviewers[agent_type]
            self._reviewer_configs.pop(agent_type, None)
            return True
        return False

    def get_reviewer_config(self, agent_type: str) -> ReviewerConfig:
        """
        Get configuration for a reviewer.

        Args:
            agent_type: Reviewer type

        Returns:
            ReviewerConfig (default if not configured)
        """
        return self._reviewer_configs.get(
            agent_type,
            ReviewerConfig(agent_type=agent_type),
        )

    def list_reviewers(self) -> list[str]:
        """
        List all registered reviewer types.

        Returns:
            List of reviewer type identifiers
        """
        return list(self._reviewers.keys())

    def get_available_reviewers(
        self,
        exclude_agents: list[str] | None = None,
    ) -> list[str]:
        """
        Get available reviewers, optionally excluding some.

        Args:
            exclude_agents: Agents to exclude (e.g., author)

        Returns:
            List of available reviewer types
        """
        exclude = set(exclude_agents or [])
        return [
            agent_type
            for agent_type in self._reviewers
            if agent_type not in exclude
            and self.get_reviewer_config(agent_type).enabled
        ]

    async def review_code(
        self,
        changes: list[CodeChange | dict[str, Any]],
        author_agent: str = "unknown",
        target_branch: str = "main",
        strategy: ReviewStrategy | None = None,
        timeout_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CrossReviewResult:
        """
        Review code changes with multiple agents.

        This is the main entry point for code review. It dispatches
        the changes to multiple reviewer agents and aggregates results.

        Args:
            changes: List of code changes to review
            author_agent: Agent that authored the changes (excluded from review)
            target_branch: Target branch for merge
            strategy: Approval strategy override
            timeout_seconds: Timeout override
            metadata: Additional metadata

        Returns:
            CrossReviewResult with aggregated review results

        Raises:
            CrossReviewerError: If review fails or insufficient reviewers

        Example:
            >>> result = await reviewer.review_code(
            ...     changes=[{"file_path": "app.py", "diff": diff_content}],
            ...     author_agent="implementer",
            ...     strategy=ReviewStrategy.CONSENSUS
            ... )
        """
        # Normalize changes to CodeChange models
        normalized_changes: list[CodeChange] = []
        for change in changes:
            if isinstance(change, CodeChange):
                normalized_changes.append(change)
            elif isinstance(change, dict):
                normalized_changes.append(CodeChange(**change))
            else:
                raise CrossReviewerError(f"Invalid change type: {type(change)}")

        # Create result object
        result = CrossReviewResult(
            strategy_used=strategy or self._default_strategy,
            metadata=metadata or {},
        )
        result.status = ReviewStatus.IN_PROGRESS

        # Track active review
        self._active_reviews[result.review_id] = result

        try:
            # Get available reviewers (excluding author)
            available_reviewers = self.get_available_reviewers(
                exclude_agents=[author_agent]
            )

            if len(available_reviewers) < self._min_reviewers:
                raise CrossReviewerError(
                    f"Insufficient reviewers: {len(available_reviewers)} available, "
                    f"{self._min_reviewers} required",
                    review_id=result.review_id,
                )

            # Run reviews in parallel
            timeout = timeout_seconds or self._default_timeout

            review_tasks = [
                self._run_single_review(
                    reviewer_type=reviewer_type,
                    changes=normalized_changes,
                    result=result,
                )
                for reviewer_type in available_reviewers
            ]

            try:
                reviewer_results = await asyncio.wait_for(
                    asyncio.gather(*review_tasks, return_exceptions=True),
                    timeout=timeout,
                )
            except TimeoutError:
                result.mark_complete(
                    status=ReviewStatus.TIMEOUT,
                    error=f"Review timed out after {timeout}s",
                )
                self._update_stats(result)
                return result

            # Process results
            for reviewer_result in reviewer_results:
                if isinstance(reviewer_result, Exception):
                    # Log but continue with other reviewers
                    continue
                if isinstance(reviewer_result, ReviewerResult):
                    result.reviewer_results.append(reviewer_result)

            # Aggregate findings
            result.aggregated_findings = self._aggregate_findings(
                result.reviewer_results
            )

            # Calculate consensus
            result.consensus_score = self._calculate_consensus(
                result.reviewer_results
            )

            # Determine approval based on strategy
            approved = self._determine_approval(
                result.reviewer_results,
                result.strategy_used,
                result.aggregated_findings,
            )

            # Mark complete
            final_status = ReviewStatus.APPROVED if approved else ReviewStatus.CHANGES_REQUESTED
            result.mark_complete(status=final_status, approved=approved)

        except CrossReviewerError:
            raise
        except Exception as e:
            result.mark_complete(
                status=ReviewStatus.FAILED,
                error=f"Review failed: {str(e)}",
            )
            raise CrossReviewerError(
                f"Review failed: {e}",
                review_id=result.review_id,
            ) from e
        finally:
            # Remove from active reviews
            self._active_reviews.pop(result.review_id, None)
            self._update_stats(result)

        return result

    async def _run_single_review(
        self,
        reviewer_type: str,
        changes: list[CodeChange],
        result: CrossReviewResult,
    ) -> ReviewerResult:
        """
        Run review with a single reviewer agent.

        Args:
            reviewer_type: Type of reviewer
            changes: Code changes to review
            result: Parent result for context

        Returns:
            ReviewerResult from this reviewer
        """
        reviewer_id = f"{reviewer_type}-{str(uuid.uuid4())[:4]}"
        config = self.get_reviewer_config(reviewer_type)

        reviewer_result = ReviewerResult(
            reviewer_id=reviewer_id,
            reviewer_type=reviewer_type,
        )

        start_time = datetime.utcnow()

        try:
            # Build review prompt
            self._build_review_prompt(changes, config)

            # Get the adapter
            adapter = self._reviewers.get(reviewer_type)
            if adapter is None:
                raise CrossReviewerError(
                    f"Reviewer not found: {reviewer_type}",
                    review_id=result.review_id,
                    reviewer=reviewer_type,
                )

            # Execute review (would use agent adapter in real implementation)
            # For now, we simulate with basic analysis
            findings = await self._analyze_changes(changes, config, reviewer_type)

            reviewer_result.findings = findings
            reviewer_result.approved = len(findings) == 0 or all(
                f.severity in (ReviewSeverity.INFO, ReviewSeverity.WARNING)
                for f in findings
            )
            reviewer_result.status = ReviewStatus.APPROVED if reviewer_result.approved else ReviewStatus.CHANGES_REQUESTED
            reviewer_result.comments = self._generate_review_summary(findings)

        except Exception as e:
            reviewer_result.status = ReviewStatus.FAILED
            reviewer_result.error = str(e)

        finally:
            end_time = datetime.utcnow()
            reviewer_result.duration_seconds = (
                end_time - start_time
            ).total_seconds()

        return reviewer_result

    def _build_review_prompt(
        self,
        changes: list[CodeChange],
        config: ReviewerConfig,
    ) -> str:
        """
        Build the review prompt for an agent.

        Args:
            changes: Code changes to review
            config: Reviewer configuration

        Returns:
            Prompt string
        """
        parts = [
            "# Code Review Request",
            "",
            "Please review the following code changes for:",
            "- Correctness and logic errors",
            "- Security vulnerabilities",
            "- Code style and best practices",
            "- Performance issues",
            "- Documentation completeness",
            "",
        ]

        if config.focus_areas:
            parts.append("Focus especially on:")
            for area in config.focus_areas:
                parts.append(f"- {area}")
            parts.append("")

        parts.append("## Changes to Review")
        parts.append("")

        for change in changes:
            parts.append(f"### File: {change.file_path}")
            parts.append(f"Type: {change.change_type}")
            parts.append("")
            if change.diff:
                parts.append("```diff")
                parts.append(change.diff)
                parts.append("```")
            parts.append("")

        parts.extend([
            "## Review Output Format",
            "",
            "Provide your review as:",
            "1. APPROVED or CHANGES_REQUESTED",
            "2. List of findings with severity (info/warning/error/critical)",
            "3. Specific line numbers and suggestions for issues",
            "4. Overall confidence in your review (0.0 to 1.0)",
        ])

        return "\n".join(parts)

    async def _analyze_changes(
        self,
        changes: list[CodeChange],
        config: ReviewerConfig,
        reviewer_type: str,
    ) -> list[ReviewFinding]:
        """
        Analyze code changes for issues.

        This is a simplified analysis. In production, this would
        use the actual agent adapter to perform the review.

        Args:
            changes: Code changes to analyze
            config: Reviewer configuration
            reviewer_type: Type of reviewer

        Returns:
            List of findings
        """
        findings: list[ReviewFinding] = []

        for change in changes:
            # Check exclude patterns
            excluded = False
            for pattern in config.exclude_patterns:
                if pattern in change.file_path:
                    excluded = True
                    break

            if excluded:
                continue

            content = change.new_content or change.diff

            if content:
                # Basic static analysis checks
                findings.extend(
                    self._check_security_issues(
                        content, change.file_path, reviewer_type
                    )
                )
                findings.extend(
                    self._check_code_quality(
                        content, change.file_path, reviewer_type
                    )
                )

        return findings

    def _check_security_issues(
        self,
        content: str,
        file_path: str,
        reviewer: str,
    ) -> list[ReviewFinding]:
        """
        Check for common security issues.

        Args:
            content: Code content
            file_path: File path
            reviewer: Reviewer name

        Returns:
            List of security findings
        """
        findings: list[ReviewFinding] = []
        lines = content.split("\n")

        security_patterns = [
            ("password", "Potential hardcoded password"),
            ("api_key", "Potential hardcoded API key"),
            ("secret", "Potential hardcoded secret"),
            ("token", "Potential hardcoded token"),
            ("eval(", "Use of eval() is a security risk"),
            ("exec(", "Use of exec() is a security risk"),
            ("subprocess.call(", "Use shell=False with subprocess"),
        ]

        for i, line in enumerate(lines, 1):
            line_lower = line.lower()
            for pattern, message in security_patterns:
                if pattern.lower() in line_lower:
                    # Avoid false positives for variable names
                    if "=" in line and '"' in line or "'" in line:
                        findings.append(
                            ReviewFinding(
                                file_path=file_path,
                                line_start=i,
                                line_end=i,
                                severity=ReviewSeverity.WARNING,
                                category="security",
                                message=message,
                                suggestion="Use environment variables or secure storage for sensitive data",
                                reviewer=reviewer,
                                confidence=0.6,
                            )
                        )

        return findings

    def _check_code_quality(
        self,
        content: str,
        file_path: str,
        reviewer: str,
    ) -> list[ReviewFinding]:
        """
        Check for code quality issues.

        Args:
            content: Code content
            file_path: File path
            reviewer: Reviewer name

        Returns:
            List of quality findings
        """
        findings: list[ReviewFinding] = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # Check for very long lines
            if len(line) > 120:
                findings.append(
                    ReviewFinding(
                        file_path=file_path,
                        line_start=i,
                        line_end=i,
                        severity=ReviewSeverity.INFO,
                        category="style",
                        message=f"Line exceeds 120 characters ({len(line)} chars)",
                        suggestion="Consider breaking into multiple lines",
                        reviewer=reviewer,
                        confidence=0.8,
                    )
                )

            # Check for TODO/FIXME without issue reference
            if "TODO" in line or "FIXME" in line:
                if "#" not in line and "issue" not in line.lower():
                    findings.append(
                        ReviewFinding(
                            file_path=file_path,
                            line_start=i,
                            line_end=i,
                            severity=ReviewSeverity.INFO,
                            category="maintenance",
                            message="TODO/FIXME without issue reference",
                            suggestion="Add issue reference (e.g., TODO #123)",
                            reviewer=reviewer,
                            confidence=0.7,
                        )
                    )

        return findings

    def _generate_review_summary(
        self,
        findings: list[ReviewFinding],
    ) -> str:
        """
        Generate a summary of review findings.

        Args:
            findings: List of findings

        Returns:
            Summary string
        """
        if not findings:
            return "No issues found. Code looks good!"

        by_severity: dict[ReviewSeverity, int] = {}
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

        parts = [f"Found {len(findings)} issue(s):"]
        for severity in [
            ReviewSeverity.CRITICAL,
            ReviewSeverity.ERROR,
            ReviewSeverity.WARNING,
            ReviewSeverity.INFO,
        ]:
            count = by_severity.get(severity, 0)
            if count > 0:
                parts.append(f"  - {severity.value}: {count}")

        return "\n".join(parts)

    def _aggregate_findings(
        self,
        reviewer_results: list[ReviewerResult],
    ) -> list[ReviewFinding]:
        """
        Aggregate findings from multiple reviewers.

        Deduplicates similar findings and merges confidence scores.

        Args:
            reviewer_results: Results from all reviewers

        Returns:
            Aggregated and deduplicated findings
        """
        all_findings: list[ReviewFinding] = []
        for result in reviewer_results:
            all_findings.extend(result.findings)

        # Group similar findings
        finding_groups: dict[str, list[ReviewFinding]] = {}
        for finding in all_findings:
            # Create a key based on file, line, and message
            key = f"{finding.file_path}:{finding.line_start or 0}:{finding.message[:50]}"
            if key not in finding_groups:
                finding_groups[key] = []
            finding_groups[key].append(finding)

        # Merge similar findings
        aggregated: list[ReviewFinding] = []
        for group in finding_groups.values():
            if len(group) == 1:
                aggregated.append(group[0])
            else:
                # Merge findings, using highest severity and average confidence
                best = max(group, key=lambda f: f.severity.value)
                avg_confidence = sum(f.confidence for f in group) / len(group)
                best.confidence = min(avg_confidence * 1.1, 1.0)  # Boost for corroboration
                aggregated.append(best)

        # Sort by severity
        severity_order = {
            ReviewSeverity.CRITICAL: 0,
            ReviewSeverity.ERROR: 1,
            ReviewSeverity.WARNING: 2,
            ReviewSeverity.INFO: 3,
        }
        aggregated.sort(key=lambda f: severity_order.get(f.severity, 99))

        return aggregated

    def _calculate_consensus(
        self,
        reviewer_results: list[ReviewerResult],
    ) -> float:
        """
        Calculate consensus score among reviewers.

        Args:
            reviewer_results: Results from all reviewers

        Returns:
            Consensus score (0.0 to 1.0)
        """
        if not reviewer_results:
            return 0.0

        approvals = sum(1 for r in reviewer_results if r.approved)
        total = len(reviewer_results)

        if total == 0:
            return 0.0

        # Simple ratio-based consensus
        ratio = approvals / total

        # Weight by average confidence
        avg_confidence = sum(r.confidence for r in reviewer_results) / total

        return ratio * avg_confidence

    def _determine_approval(
        self,
        reviewer_results: list[ReviewerResult],
        strategy: ReviewStrategy,
        findings: list[ReviewFinding],
    ) -> bool:
        """
        Determine if changes should be approved based on strategy.

        Args:
            reviewer_results: Results from all reviewers
            strategy: Approval strategy
            findings: Aggregated findings

        Returns:
            True if approved, False otherwise
        """
        # Check for blocking issues first
        blocking = [
            f
            for f in findings
            if f.severity in (ReviewSeverity.ERROR, ReviewSeverity.CRITICAL)
        ]
        if blocking:
            return False

        approvals = sum(1 for r in reviewer_results if r.approved)
        total = len(reviewer_results)

        if total == 0:
            return False

        if strategy == ReviewStrategy.CONSENSUS:
            return approvals == total

        if strategy == ReviewStrategy.MAJORITY:
            return approvals > total / 2

        if strategy == ReviewStrategy.SINGLE:
            return approvals >= 1

        if strategy == ReviewStrategy.WEIGHTED:
            # Weight by reviewer confidence
            weighted_approvals = sum(
                r.confidence for r in reviewer_results if r.approved
            )
            weighted_total = sum(r.confidence for r in reviewer_results)
            return weighted_approvals > weighted_total / 2 if weighted_total > 0 else False

        return False

    def _update_stats(self, result: CrossReviewResult) -> None:
        """
        Update review statistics.

        Args:
            result: Completed review result
        """
        self._stats.total_reviews += 1
        self._stats.total_findings += len(result.aggregated_findings)
        self._stats.blocking_findings += len(result.blocking_issues)
        self._stats.last_review_at = datetime.utcnow()

        if result.approved:
            self._stats.approved_reviews += 1
        elif result.status == ReviewStatus.FAILED:
            self._stats.failed_reviews += 1
        else:
            self._stats.rejected_reviews += 1

        # Update averages
        if result.duration_seconds:
            total = self._stats.total_reviews
            current_avg = self._stats.average_review_duration
            self._stats.average_review_duration = (
                (current_avg * (total - 1) + result.duration_seconds) / total
            )

        if result.reviewer_count:
            total = self._stats.total_reviews
            current_avg = self._stats.average_reviewers_per_review
            self._stats.average_reviewers_per_review = (
                (current_avg * (total - 1) + result.reviewer_count) / total
            )

    def get_active_reviews(self) -> list[CrossReviewResult]:
        """
        Get all currently active reviews.

        Returns:
            List of active review results
        """
        return list(self._active_reviews.values())

    def get_review(self, review_id: str) -> CrossReviewResult | None:
        """
        Get a review by ID.

        Args:
            review_id: Review ID to look up

        Returns:
            CrossReviewResult if found, None otherwise
        """
        return self._active_reviews.get(review_id)

    async def cancel_review(self, review_id: str) -> bool:
        """
        Cancel an active review.

        Args:
            review_id: Review ID to cancel

        Returns:
            True if review was cancelled, False if not found
        """
        result = self._active_reviews.get(review_id)
        if result is None:
            return False

        result.mark_complete(
            status=ReviewStatus.FAILED,
            error="Review cancelled by user",
        )
        self._active_reviews.pop(review_id, None)
        return True

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"CrossReviewer("
            f"reviewers={len(self._reviewers)}, "
            f"strategy={self._default_strategy.value}, "
            f"min_reviewers={self._min_reviewers})"
        )


def create_cross_reviewer(
    reviewers: dict[str, Any] | None = None,
    strategy: ReviewStrategy | None = None,
    min_reviewers: int | None = None,
) -> CrossReviewer:
    """
    Factory function to create a configured cross-reviewer.

    Args:
        reviewers: Optional dict of pre-registered reviewers
        strategy: Default approval strategy
        min_reviewers: Minimum reviewers required

    Returns:
        Configured CrossReviewer instance

    Example:
        >>> from autoflow.agents.claude_code import ClaudeCodeAdapter
        >>> reviewer = create_cross_reviewer(
        ...     reviewers={"claude-code": ClaudeCodeAdapter()},
        ...     strategy=ReviewStrategy.CONSENSUS
        ... )
    """
    cross_reviewer = CrossReviewer(
        default_strategy=strategy,
        min_reviewers=min_reviewers,
    )

    if reviewers:
        for agent_type, adapter in reviewers.items():
            cross_reviewer.register_reviewer(agent_type, adapter)

    return cross_reviewer
