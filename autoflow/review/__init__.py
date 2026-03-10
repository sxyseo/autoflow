"""
Autoflow Review Module

This module provides comprehensive review functionality including:
- Review Gates: Verification and quality gates for automatic test execution
- Cross Review: Multi-agent code review capabilities
- Coverage analysis and QA findings management

Review Gates Components:
    - CoverageTracker, CoverageThreshold, CoverageReport
    - ApprovalToken, ApprovalGate, create_git_commit_message_with_approval
    - VerificationOrchestrator, VerificationResult, create_verification_report

Cross Review Components:
    - CrossReviewer: Orchestrates multi-agent review process
    - Review artifacts: Structured output for review results
    - Multiple approval strategies: consensus, majority, weighted voting

Usage:
    # Review Gates
    from autoflow.review import ApprovalGate, VerificationOrchestrator

    # Cross Review
    from autoflow.review import CrossReviewer, ReviewStrategy

    reviewer = CrossReviewer()
    result = await reviewer.review_code(
        changes=[{"file_path": "app.py", "diff": "..."}],
        author_agent="implementer"
    )
"""

from autoflow.review.approval import (
    ApprovalGate,
    ApprovalGateConfig,
    ApprovalToken,
    create_git_commit_message_with_approval,
    extract_approval_hash_from_commit,
)
from autoflow.review.coverage import CoverageReport, CoverageThreshold, CoverageTracker
from autoflow.review.cross_review import (
    CodeChange,
    CrossReviewer,
    CrossReviewerError,
    CrossReviewerStats,
    CrossReviewResult,
    ReviewerConfig,
    ReviewerResult,
    ReviewFinding,
    ReviewSeverity,
    ReviewStatus,
    ReviewStrategy,
    create_cross_reviewer,
)
from autoflow.review.verification import (
    VerificationConfig,
    VerificationOrchestrator,
    VerificationResult,
    create_verification_report,
)

__all__ = [
    # Review Gates
    "CoverageTracker",
    "CoverageThreshold",
    "CoverageReport",
    "ApprovalToken",
    "ApprovalGateConfig",
    "ApprovalGate",
    "create_git_commit_message_with_approval",
    "extract_approval_hash_from_commit",
    "VerificationOrchestrator",
    "VerificationResult",
    "VerificationConfig",
    "create_verification_report",
    # Cross Review
    "CrossReviewer",
    "CrossReviewerError",
    "CrossReviewerStats",
    "create_cross_reviewer",
    "CrossReviewResult",
    "ReviewerResult",
    "ReviewFinding",
    "CodeChange",
    "ReviewerConfig",
    "ReviewStatus",
    "ReviewSeverity",
    "ReviewStrategy",
]
