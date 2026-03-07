"""
Autoflow Review - Multi-Agent Code Review

This module provides cross-review capabilities where agents
review each other's code before merging:

- CrossReviewer: Orchestrates multi-agent review process
- Review artifacts: Structured output for review results
- Multiple approval strategies: consensus, majority, weighted voting

Ensures code quality through automated peer review.

Usage:
    from autoflow.review import CrossReviewer, ReviewStrategy

    reviewer = CrossReviewer()
    result = await reviewer.review_code(
        changes=[{"file_path": "app.py", "diff": "..."}],
        author_agent="implementer"
    )
"""

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

__all__ = [
    # Main class
    "CrossReviewer",
    "CrossReviewerError",
    "CrossReviewerStats",
    "create_cross_reviewer",
    # Results
    "CrossReviewResult",
    "ReviewerResult",
    "ReviewFinding",
    # Models
    "CodeChange",
    "ReviewerConfig",
    # Enums
    "ReviewStatus",
    "ReviewSeverity",
    "ReviewStrategy",
]
