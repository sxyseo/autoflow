"""
Autoflow Collaborative Review Module

Provides team-oriented code review capabilities where multiple human reviewers
collaborate on reviewing code changes. Extends the cross-review system to support
team collaboration with role-based permissions and workflow tracking.

Usage:
    from autflow.collaboration.review import CollaborativeReview

    review = CollaborativeReview()
    result = await review.create_review(
        changes=[{"file": "app.py", "diff": "..."}],
        author_id="user-001",
        workspace_id="workspace-001"
    )

    # Add reviewers
    await review.add_reviewer(result.review_id, reviewer_id="user-002")
    await review.add_reviewer(result.review_id, reviewer_id="user-003")

    # Submit reviews
    await review.submit_review(result.review_id, reviewer_id="user-002", approved=True)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

# Import base classes from cross-review
from autoflow.review.cross_review import (
    CodeChange,
    ReviewFinding,
    ReviewSeverity,
    ReviewStatus,
    ReviewStrategy,
)

# Import collaboration models
from autoflow.collaboration.models import NotificationType, RoleType, User
from autoflow.collaboration.notifications import NotificationManager


class CollaborativeReviewStatus(str, Enum):
    """Status of a collaborative review."""

    DRAFT = "draft"  # Review is being prepared
    REQUESTED = "requested"  # Review has been requested
    IN_PROGRESS = "in_progress"  # Reviewers are actively reviewing
    APPROVED = "approved"  # Changes approved for merge
    REJECTED = "rejected"  # Changes rejected
    CHANGES_REQUESTED = "changes_requested"  # Changes needed before approval
    CANCELLED = "cancelled"  # Review cancelled
    EXPIRED = "expired"  # Review expired without completion


class ReviewerRole(str, Enum):
    """Role of a reviewer in a collaborative review."""

    PRIMARY_REVIEWER = "primary_reviewer"  # Main reviewer
    SECONDARY_REVIEWER = "secondary_reviewer"  # Additional reviewer
    APPROVER = "approver"  # Final approver
    OBSERVER = "observer"  # Can comment but not approve


@dataclass
class ReviewerAssignment:
    """
    Assignment of a reviewer to a collaborative review.

    Attributes:
        reviewer_id: ID of the assigned reviewer
        role: Role of this reviewer in the review
        status: Current status of this reviewer's work
        assigned_at: When this reviewer was assigned
        responded_at: When this reviewer responded
        findings: List of findings from this reviewer
        approved: Whether this reviewer approved
        comments: Comments from this reviewer
        confidence: Confidence level in the review (0.0 to 1.0)
    """

    reviewer_id: str
    role: ReviewerRole = ReviewerRole.SECONDARY_REVIEWER
    status: CollaborativeReviewStatus = CollaborativeReviewStatus.REQUESTED
    assigned_at: datetime = field(default_factory=datetime.utcnow)
    responded_at: Optional[datetime] = None
    findings: list[ReviewFinding] = field(default_factory=list)
    approved: bool = False
    comments: Optional[str] = None
    confidence: float = 0.8

    @property
    def is_complete(self) -> bool:
        """Check if this reviewer has completed their review."""
        return self.status in (
            CollaborativeReviewStatus.APPROVED,
            CollaborativeReviewStatus.REJECTED,
            CollaborativeReviewStatus.CHANGES_REQUESTED,
        )

    @property
    def has_approved(self) -> bool:
        """Check if this reviewer has approved."""
        return self.status == CollaborativeReviewStatus.APPROVED and self.approved

    def to_dict(self) -> dict[str, Any]:
        """Convert assignment to dictionary."""
        return {
            "reviewer_id": self.reviewer_id,
            "role": self.role.value,
            "status": self.status.value,
            "assigned_at": self.assigned_at.isoformat(),
            "responded_at": self.responded_at.isoformat()
            if self.responded_at
            else None,
            "findings": [f.to_dict() for f in self.findings],
            "approved": self.approved,
            "comments": self.comments,
            "confidence": self.confidence,
        }


class CollaborativeReviewRequest(BaseModel):
    """
    Request to initiate a collaborative review.

    Attributes:
        changes: List of code changes to review
        author_id: User ID who authored the changes
        workspace_id: Workspace ID for the review
        title: Review title
        description: Review description
        target_branch: Target branch for merge
        strategy: Approval strategy
        required_role: Minimum role required to approve
        auto_assign: Whether to auto-assign reviewers
        timeout_hours: Timeout in hours before review expires
        metadata: Additional metadata
    """

    changes: list[CodeChange] = Field(default_factory=list)
    author_id: str = ""
    workspace_id: str = ""
    title: str = ""
    description: str = ""
    target_branch: str = "main"
    strategy: ReviewStrategy = ReviewStrategy.MAJORITY
    required_role: RoleType = RoleType.REVIEWER
    auto_assign: bool = False
    timeout_hours: int = 72
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class CollaborativeReviewResult:
    """
    Result from a collaborative review.

    Attributes:
        review_id: Unique identifier for this review
        status: Overall review status
        request: Original review request
        author_id: User who authored the changes
        workspace_id: Workspace for this review
        assignments: List of reviewer assignments
        aggregated_findings: All findings from all reviewers
        consensus_score: Score based on reviewer agreement (0.0 to 1.0)
        strategy_used: Strategy used for approval decision
        created_at: When review was created
        started_at: When review started (first assignment)
        completed_at: When review completed
        expires_at: When review expires
        duration_hours: Total review duration in hours
        metadata: Additional metadata
    """

    review_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: CollaborativeReviewStatus = CollaborativeReviewStatus.DRAFT
    request: Optional[CollaborativeReviewRequest] = None
    author_id: str = ""
    workspace_id: str = ""
    assignments: list[ReviewerAssignment] = field(default_factory=list)
    aggregated_findings: list[ReviewFinding] = field(default_factory=list)
    consensus_score: float = 0.0
    strategy_used: ReviewStrategy = ReviewStrategy.MAJORITY
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    duration_hours: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def reviewer_count(self) -> int:
        """Get number of assigned reviewers."""
        return len(self.assignments)

    @property
    def completed_reviewer_count(self) -> int:
        """Get number of reviewers who have completed their review."""
        return sum(1 for a in self.assignments if a.is_complete)

    @property
    def approval_count(self) -> int:
        """Get number of approving reviewers."""
        return sum(1 for a in self.assignments if a.has_approved)

    @property
    def blocking_issues(self) -> list[ReviewFinding]:
        """Get all findings that block approval."""
        return [
            f
            for f in self.aggregated_findings
            if f.severity in (ReviewSeverity.ERROR, ReviewSeverity.CRITICAL)
        ]

    @property
    def is_expired(self) -> bool:
        """Check if review has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def can_complete(self) -> bool:
        """Check if review can be completed (all reviewers finished)."""
        if not self.assignments:
            return False
        return all(a.is_complete for a in self.assignments)

    def mark_complete(
        self,
        status: CollaborativeReviewStatus,
    ) -> None:
        """
        Mark the review as complete.

        Args:
            status: Final review status
        """
        self.status = status
        self.completed_at = datetime.utcnow()
        if self.started_at:
            duration = self.completed_at - self.started_at
            self.duration_hours = duration.total_seconds() / 3600

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "review_id": self.review_id,
            "status": self.status.value,
            "author_id": self.author_id,
            "workspace_id": self.workspace_id,
            "title": self.request.title if self.request else "",
            "description": self.request.description if self.request else "",
            "reviewer_count": self.reviewer_count,
            "completed_reviewer_count": self.completed_reviewer_count,
            "approval_count": self.approval_count,
            "consensus_score": self.consensus_score,
            "strategy_used": self.strategy_used.value,
            "blocking_issues": len(self.blocking_issues),
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "duration_hours": self.duration_hours,
            "assignments": [a.to_dict() for a in self.assignments],
            "aggregated_findings": [f.to_dict() for f in self.aggregated_findings],
            "metadata": self.metadata,
        }


class CollaborativeReviewError(Exception):
    """Exception raised for collaborative review errors."""

    def __init__(
        self,
        message: str,
        review_id: Optional[str] = None,
        reviewer_id: Optional[str] = None,
    ):
        self.review_id = review_id
        self.reviewer_id = reviewer_id
        super().__init__(message)


class CollaborativeReview:
    """
    Team-oriented collaborative review orchestrator.

    The CollaborativeReview class manages code review workflows where multiple
    human reviewers collaborate on reviewing code changes. It extends the
    cross-review system to support team collaboration with role-based
    permissions and workflow tracking.

    Key features:
    - Multiple human reviewers with different roles
    - Role-based approval workflows
    - Flexible approval strategies (consensus, majority, etc.)
    - Review assignment and tracking
    - Finding aggregation and deduplication
    - Activity tracking integration
    - Notification support for review requests and completions

    Example:
        >>> from autoflow.collaboration.notifications import NotificationManager
        >>> notification_mgr = NotificationManager(".autoflow")
        >>> notification_mgr.initialize()
        >>>
        >>> review = CollaborativeReview(notification_manager=notification_mgr)
        >>>
        >>> # Create a new review
        >>> result = await review.create_review(
        ...     changes=[{"file_path": "app.py", "diff": "..."}],
        ...     author_id="user-001",
        ...     workspace_id="workspace-001",
        ...     title="Feature X implementation"
        ... )
        >>>
        >>> # Assign reviewers (notifications sent automatically)
        >>> await review.add_reviewer(result.review_id, "user-002", ReviewerRole.PRIMARY_REVIEWER)
        >>> await review.add_reviewer(result.review_id, "user-003", ReviewerRole.SECONDARY_REVIEWER)
        >>>
        >>> # Reviewers submit their reviews
        >>> await review.submit_review(
        ...     result.review_id,
        ...     "user-002",
        ...     approved=True,
        ...     comments="Looks good!"
        ... )

    Attributes:
        default_strategy: Default review strategy
        default_timeout_hours: Default timeout for reviews
        min_reviewers: Minimum number of reviewers required
        notification_manager: Optional notification manager for sending notifications
    """

    DEFAULT_STRATEGY = ReviewStrategy.MAJORITY
    DEFAULT_TIMEOUT_HOURS = 72
    DEFAULT_MIN_REVIEWERS = 1

    # Default role weights for voting
    DEFAULT_ROLE_WEIGHTS: dict[ReviewerRole, float] = {
        ReviewerRole.APPROVER: 3.0,
        ReviewerRole.PRIMARY_REVIEWER: 2.0,
        ReviewerRole.SECONDARY_REVIEWER: 1.0,
        ReviewerRole.OBSERVER: 0.0,  # Cannot vote
    }

    def __init__(
        self,
        default_strategy: Optional[ReviewStrategy] = None,
        default_timeout_hours: Optional[int] = None,
        min_reviewers: Optional[int] = None,
        role_weights: Optional[dict[ReviewerRole, float]] = None,
        notification_manager: Optional[NotificationManager] = None,
        state_dir: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize the collaborative review system.

        Args:
            default_strategy: Default approval strategy
            default_timeout_hours: Default timeout in hours
            min_reviewers: Minimum reviewers required
            role_weights: Custom weights for reviewer roles in voting
            notification_manager: Optional notification manager for sending notifications
            state_dir: Optional state directory for notification manager
        """
        self._default_strategy = default_strategy or self.DEFAULT_STRATEGY
        self._default_timeout_hours = (
            default_timeout_hours or self.DEFAULT_TIMEOUT_HOURS
        )
        self._min_reviewers = min_reviewers or self.DEFAULT_MIN_REVIEWERS
        self._role_weights = role_weights or self.DEFAULT_ROLE_WEIGHTS.copy()
        self._active_reviews: dict[str, CollaborativeReviewResult] = {}

        # Initialize notification manager
        self._notification_manager = notification_manager
        if notification_manager is None and state_dir is not None:
            self._notification_manager = NotificationManager(state_dir)
            self._notification_manager.initialize()

    @property
    def default_strategy(self) -> ReviewStrategy:
        """Get default strategy."""
        return self._default_strategy

    @property
    def min_reviewers(self) -> int:
        """Get minimum reviewers required."""
        return self._min_reviewers

    @property
    def notification_manager(self) -> Optional[NotificationManager]:
        """Get notification manager."""
        return self._notification_manager

    def set_notification_manager(
        self,
        notification_manager: NotificationManager,
    ) -> None:
        """
        Set or update the notification manager.

        Args:
            notification_manager: Notification manager to use

        Example:
            >>> from autoflow.collaboration.notifications import NotificationManager
            >>> notification_mgr = NotificationManager(".autoflow")
            >>> notification_mgr.initialize()
            >>> review.set_notification_manager(notification_mgr)
        """
        self._notification_manager = notification_manager

    def get_role_weight(self, role: ReviewerRole) -> float:
        """
        Get the voting weight for a reviewer role.

        Args:
            role: The reviewer role

        Returns:
            Voting weight (0.0 to 3.0+)
        """
        return self._role_weights.get(role, 1.0)

    def set_role_weight(self, role: ReviewerRole, weight: float) -> None:
        """
        Set the voting weight for a reviewer role.

        Args:
            role: The reviewer role
            weight: Voting weight (0.0 to disable voting, higher for more influence)
        """
        if weight < 0:
            raise ValueError("Role weight must be non-negative")
        self._role_weights[role] = weight

    def get_review(self, review_id: str) -> Optional[CollaborativeReviewResult]:
        """
        Get a review by ID.

        Args:
            review_id: Review ID to look up

        Returns:
            CollaborativeReviewResult if found, None otherwise
        """
        return self._active_reviews.get(review_id)

    def list_reviews(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[CollaborativeReviewStatus] = None,
    ) -> list[CollaborativeReviewResult]:
        """
        List reviews with optional filtering.

        Args:
            workspace_id: Filter by workspace ID
            status: Filter by status

        Returns:
            List of matching reviews
        """
        reviews = list(self._active_reviews.values())

        if workspace_id:
            reviews = [r for r in reviews if r.workspace_id == workspace_id]

        if status:
            reviews = [r for r in reviews if r.status == status]

        return reviews

    async def create_review(
        self,
        changes: list[Union[CodeChange, dict[str, Any]]],
        author_id: str,
        workspace_id: str,
        title: str = "",
        description: str = "",
        target_branch: str = "main",
        strategy: Optional[ReviewStrategy] = None,
        required_role: RoleType = RoleType.REVIEWER,
        timeout_hours: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CollaborativeReviewResult:
        """
        Create a new collaborative review.

        Args:
            changes: List of code changes to review
            author_id: User ID who authored the changes
            workspace_id: Workspace ID for the review
            title: Review title
            description: Review description
            target_branch: Target branch for merge
            strategy: Approval strategy override
            required_role: Minimum role required to approve
            timeout_hours: Timeout override
            metadata: Additional metadata

        Returns:
            Created CollaborativeReviewResult

        Raises:
            CollaborativeReviewError: If creation fails
        """
        # Normalize changes to CodeChange models
        normalized_changes: list[CodeChange] = []
        for change in changes:
            if isinstance(change, CodeChange):
                normalized_changes.append(change)
            elif isinstance(change, dict):
                normalized_changes.append(CodeChange(**change))
            else:
                raise CollaborativeReviewError(f"Invalid change type: {type(change)}")

        # Create request
        request = CollaborativeReviewRequest(
            changes=normalized_changes,
            author_id=author_id,
            workspace_id=workspace_id,
            title=title,
            description=description,
            target_branch=target_branch,
            strategy=strategy or self._default_strategy,
            required_role=required_role,
            timeout_hours=timeout_hours or self._default_timeout_hours,
            metadata=metadata or {},
        )

        # Create result
        result = CollaborativeReviewResult(
            request=request,
            author_id=author_id,
            workspace_id=workspace_id,
            strategy_used=request.strategy,
            metadata=request.metadata,
        )

        # Set expiration
        from datetime import timedelta

        result.expires_at = datetime.utcnow() + timedelta(hours=request.timeout_hours)

        # Store and return
        self._active_reviews[result.review_id] = result

        return result

    async def start_review(
        self,
        review_id: str,
    ) -> CollaborativeReviewResult:
        """
        Start a review (transitions from DRAFT to REQUESTED).

        Args:
            review_id: Review ID to start

        Returns:
            Updated CollaborativeReviewResult

        Raises:
            CollaborativeReviewError: If review not found or invalid state
        """
        result = self._active_reviews.get(review_id)
        if not result:
            raise CollaborativeReviewError(
                f"Review not found: {review_id}",
                review_id=review_id,
            )

        if result.status != CollaborativeReviewStatus.DRAFT:
            raise CollaborativeReviewError(
                f"Review is not in DRAFT status: {result.status.value}",
                review_id=review_id,
            )

        result.status = CollaborativeReviewStatus.REQUESTED
        result.started_at = datetime.utcnow()

        return result

    async def add_reviewer(
        self,
        review_id: str,
        reviewer_id: str,
        role: ReviewerRole = ReviewerRole.SECONDARY_REVIEWER,
        notify: bool = True,
    ) -> CollaborativeReviewResult:
        """
        Add a reviewer to a collaborative review.

        Args:
            review_id: Review ID
            reviewer_id: User ID of the reviewer
            role: Role of the reviewer
            notify: Whether to send notification to reviewer

        Returns:
            Updated CollaborativeReviewResult

        Raises:
            CollaborativeReviewError: If review not found or invalid
        """
        result = self._active_reviews.get(review_id)
        if not result:
            raise CollaborativeReviewError(
                f"Review not found: {review_id}",
                review_id=review_id,
            )

        # Check if reviewer is already assigned
        if any(a.reviewer_id == reviewer_id for a in result.assignments):
            raise CollaborativeReviewError(
                f"Reviewer already assigned: {reviewer_id}",
                review_id=review_id,
                reviewer_id=reviewer_id,
            )

        # Cannot assign author as reviewer
        if reviewer_id == result.author_id:
            raise CollaborativeReviewError(
                "Cannot assign author as reviewer",
                review_id=review_id,
                reviewer_id=reviewer_id,
            )

        # Add assignment
        assignment = ReviewerAssignment(
            reviewer_id=reviewer_id,
            role=role,
            status=CollaborativeReviewStatus.REQUESTED,
        )
        result.assignments.append(assignment)

        # Update status if first reviewer added
        if (
            result.status == CollaborativeReviewStatus.DRAFT
            or result.status == CollaborativeReviewStatus.REQUESTED
        ):
            if len(result.assignments) >= self._min_reviewers:
                result.status = CollaborativeReviewStatus.IN_PROGRESS
                if not result.started_at:
                    result.started_at = datetime.utcnow()

        # Send notification to reviewer
        if notify and self._notification_manager:
            try:
                self._notification_manager.notify_review_request(
                    user_id=result.author_id,
                    reviewer_id=reviewer_id,
                    task_id=review_id,
                    task_title=result.request.title if result.request else review_id,
                    workspace_id=result.workspace_id,
                    team_id=result.metadata.get("team_id"),
                )
            except Exception:
                # Don't fail review if notification fails
                pass

        return result

    async def remove_reviewer(
        self,
        review_id: str,
        reviewer_id: str,
    ) -> CollaborativeReviewResult:
        """
        Remove a reviewer from a collaborative review.

        Args:
            review_id: Review ID
            reviewer_id: User ID of the reviewer to remove

        Returns:
            Updated CollaborativeReviewResult

        Raises:
            CollaborativeReviewError: If review not found or reviewer not assigned
        """
        result = self._active_reviews.get(review_id)
        if not result:
            raise CollaborativeReviewError(
                f"Review not found: {review_id}",
                review_id=review_id,
            )

        # Find and remove assignment
        original_count = len(result.assignments)
        result.assignments = [
            a for a in result.assignments if a.reviewer_id != reviewer_id
        ]

        if len(result.assignments) == original_count:
            raise CollaborativeReviewError(
                f"Reviewer not assigned: {reviewer_id}",
                review_id=review_id,
                reviewer_id=reviewer_id,
            )

        return result

    async def submit_review(
        self,
        review_id: str,
        reviewer_id: str,
        approved: bool,
        findings: Optional[list[ReviewFinding]] = None,
        comments: Optional[str] = None,
        confidence: float = 0.8,
    ) -> CollaborativeReviewResult:
        """
        Submit a review from a reviewer.

        Args:
            review_id: Review ID
            reviewer_id: User ID of the reviewer
            approved: Whether the reviewer approves
            findings: List of findings from this reviewer
            comments: Additional comments
            confidence: Confidence level (0.0 to 1.0)

        Returns:
            Updated CollaborativeReviewResult

        Raises:
            CollaborativeReviewError: If review not found or reviewer not assigned
        """
        result = self._active_reviews.get(review_id)
        if not result:
            raise CollaborativeReviewError(
                f"Review not found: {review_id}",
                review_id=review_id,
            )

        # Find assignment
        assignment = None
        for a in result.assignments:
            if a.reviewer_id == reviewer_id:
                assignment = a
                break

        if not assignment:
            raise CollaborativeReviewError(
                f"Reviewer not assigned: {reviewer_id}",
                review_id=review_id,
                reviewer_id=reviewer_id,
            )

        # Update assignment
        assignment.findings = findings or []
        assignment.approved = approved
        assignment.comments = comments
        assignment.confidence = confidence
        assignment.responded_at = datetime.utcnow()

        # Update status based on approval
        if approved:
            assignment.status = CollaborativeReviewStatus.APPROVED
        else:
            # Check if there are blocking issues
            has_blocking = any(
                f.severity in (ReviewSeverity.ERROR, ReviewSeverity.CRITICAL)
                for f in assignment.findings
            )
            if has_blocking:
                assignment.status = CollaborativeReviewStatus.REJECTED
            else:
                assignment.status = CollaborativeReviewStatus.CHANGES_REQUESTED

        # Aggregate findings from all reviewers
        result.aggregated_findings = self._aggregate_findings(result.assignments)

        # Calculate consensus
        result.consensus_score = self._calculate_consensus(result.assignments)

        # Check if review can be completed
        if result.can_complete:
            await self._complete_review(result)

        return result

    async def _complete_review(
        self,
        result: CollaborativeReviewResult,
    ) -> None:
        """
        Complete a review and determine final status.

        Args:
            result: Review result to complete
        """
        # Check for blocking issues
        if result.blocking_issues:
            result.mark_complete(CollaborativeReviewStatus.CHANGES_REQUESTED)
            await self._notify_review_completed(
                result, approved=False, changes_needed=True
            )
            return

        # Determine approval based on strategy
        approved = self._determine_approval(
            result.assignments,
            result.strategy_used,
            result.aggregated_findings,
        )

        if approved:
            result.mark_complete(CollaborativeReviewStatus.APPROVED)
            await self._notify_review_completed(result, approved=True)
        else:
            result.mark_complete(CollaborativeReviewStatus.REJECTED)
            await self._notify_review_completed(result, approved=False)

    async def _notify_review_completed(
        self,
        result: CollaborativeReviewResult,
        approved: bool,
        changes_needed: bool = False,
    ) -> None:
        """
        Notify the author that the review has been completed.

        Args:
            result: Review result
            approved: Whether the review was approved
            changes_needed: Whether changes are needed
        """
        if not self._notification_manager:
            return

        try:
            # Get reviewers who submitted feedback
            completed_reviewers = [
                a.reviewer_id for a in result.assignments if a.is_complete
            ]

            # Create a summary of feedback
            if approved and not changes_needed:
                # Notify author of approval
                for reviewer_id in completed_reviewers:
                    self._notification_manager.notify_review_approved(
                        user_id=result.author_id,
                        reviewer_id=reviewer_id,
                        task_id=result.review_id,
                        task_title=result.request.title
                        if result.request
                        else result.review_id,
                        workspace_id=result.workspace_id,
                        team_id=result.metadata.get("team_id"),
                    )
            else:
                # Notify author of rejection/changes requested
                reason = None
                if result.blocking_issues:
                    blocking_count = len(result.blocking_issues)
                    reason = f"{blocking_count} blocking issue(s) found"

                self._notification_manager.notify_review_rejected(
                    user_id=result.author_id,
                    reviewer_id=completed_reviewers[0]
                    if completed_reviewers
                    else "system",
                    task_id=result.review_id,
                    task_title=result.request.title
                    if result.request
                    else result.review_id,
                    reason=reason,
                    workspace_id=result.workspace_id,
                    team_id=result.metadata.get("team_id"),
                )
        except Exception:
            # Don't fail review if notification fails
            pass

    def _aggregate_findings(
        self,
        assignments: list[ReviewerAssignment],
    ) -> list[ReviewFinding]:
        """
        Aggregate findings from multiple reviewers.

        Deduplicates similar findings and merges confidence scores.

        Args:
            assignments: List of reviewer assignments

        Returns:
            Aggregated and deduplicated findings
        """
        all_findings: list[ReviewFinding] = []
        for assignment in assignments:
            all_findings.extend(assignment.findings)

        # Group similar findings
        finding_groups: dict[str, list[ReviewFinding]] = {}
        for finding in all_findings:
            # Create a key based on file, line, and message
            key = (
                f"{finding.file_path}:{finding.line_start or 0}:{finding.message[:50]}"
            )
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
                best.confidence = min(
                    avg_confidence * 1.1, 1.0
                )  # Boost for corroboration
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
        assignments: list[ReviewerAssignment],
    ) -> float:
        """
        Calculate consensus score among reviewers.

        Uses role-based weighting to calculate a weighted consensus score.

        Args:
            assignments: List of reviewer assignments

        Returns:
            Consensus score (0.0 to 1.0)
        """
        if not assignments:
            return 0.0

        # Only count completed reviews with non-zero weight
        completed = [
            a for a in assignments if a.is_complete and self.get_role_weight(a.role) > 0
        ]
        if not completed:
            return 0.0

        # Calculate weighted approvals
        weighted_approvals = sum(
            self.get_role_weight(a.role) * a.confidence
            for a in completed
            if a.has_approved
        )
        weighted_total = sum(
            self.get_role_weight(a.role) * a.confidence for a in completed
        )

        if weighted_total == 0:
            return 0.0

        # Weighted ratio-based consensus
        return weighted_approvals / weighted_total

    def _determine_approval(
        self,
        assignments: list[ReviewerAssignment],
        strategy: ReviewStrategy,
        findings: list[ReviewFinding],
    ) -> bool:
        """
        Determine if changes should be approved based on strategy and roles.

        This method implements role-based voting where different reviewer roles
        have different weights in the approval decision.

        Args:
            assignments: List of reviewer assignments
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

        # Filter to completed reviews with non-zero weight
        completed = [
            a for a in assignments if a.is_complete and self.get_role_weight(a.role) > 0
        ]
        if not completed:
            return False

        approvals = sum(1 for a in completed if a.has_approved)
        total = len(completed)

        if total == 0:
            return False

        if strategy == ReviewStrategy.CONSENSUS:
            # All voting reviewers must approve
            return approvals == total

        if strategy == ReviewStrategy.MAJORITY:
            # Simple majority (counts each vote equally)
            return approvals > total / 2

        if strategy == ReviewStrategy.SINGLE:
            # Any single approval is sufficient
            return approvals >= 1

        if strategy == ReviewStrategy.WEIGHTED:
            # Role-based and confidence-weighted voting
            # Combines role weight with reviewer confidence
            weighted_approvals = sum(
                self.get_role_weight(a.role) * a.confidence
                for a in completed
                if a.has_approved
            )
            weighted_total = sum(
                self.get_role_weight(a.role) * a.confidence for a in completed
            )
            return (
                weighted_approvals > weighted_total / 2 if weighted_total > 0 else False
            )

        return False

    async def cancel_review(
        self,
        review_id: str,
        notify: bool = True,
    ) -> CollaborativeReviewResult:
        """
        Cancel an active review.

        Args:
            review_id: Review ID to cancel
            notify: Whether to send notification to reviewers

        Returns:
            Updated CollaborativeReviewResult

        Raises:
            CollaborativeReviewError: If review not found
        """
        result = self._active_reviews.get(review_id)
        if not result:
            raise CollaborativeReviewError(
                f"Review not found: {review_id}",
                review_id=review_id,
            )

        result.mark_complete(CollaborativeReviewStatus.CANCELLED)

        # Notify reviewers of cancellation
        if notify and self._notification_manager:
            try:
                for assignment in result.assignments:
                    if not assignment.is_complete:
                        # Notify pending reviewers that review was cancelled
                        self._notification_manager.create_notification(
                            user_id=assignment.reviewer_id,
                            notification_type=NotificationType.WORKSPACE_UPDATE,
                            title="Review Cancelled",
                            message=f"Review '{result.request.title if result.request else review_id}' has been cancelled",
                            workspace_id=result.workspace_id,
                            team_id=result.metadata.get("team_id"),
                            metadata={
                                "review_id": review_id,
                                "cancelled_by": result.author_id,
                            },
                        )
            except Exception:
                # Don't fail review if notification fails
                pass

        return result

    def get_active_reviews(self) -> list[CollaborativeReviewResult]:
        """
        Get all currently active reviews.

        Returns:
            List of active review results
        """
        return [
            r
            for r in self._active_reviews.values()
            if r.status
            not in (
                CollaborativeReviewStatus.APPROVED,
                CollaborativeReviewStatus.REJECTED,
                CollaborativeReviewStatus.CANCELLED,
                CollaborativeReviewStatus.EXPIRED,
            )
        ]

    def get_voting_power(
        self,
        assignment: ReviewerAssignment,
    ) -> float:
        """
        Get the effective voting power of a reviewer assignment.

        Combines role weight with reviewer confidence.

        Args:
            assignment: Reviewer assignment

        Returns:
            Voting power (0.0 to 3.0+)
        """
        role_weight = self.get_role_weight(assignment.role)
        return role_weight * assignment.confidence

    def can_reviewer_vote(
        self,
        assignment: ReviewerAssignment,
    ) -> bool:
        """
        Check if a reviewer can vote (has non-zero role weight).

        Args:
            assignment: Reviewer assignment

        Returns:
            True if reviewer can vote, False otherwise
        """
        return self.get_role_weight(assignment.role) > 0

    def get_approval_breakdown(
        self,
        result: CollaborativeReviewResult,
    ) -> dict[str, Any]:
        """
        Get a breakdown of approval status by role.

        Args:
            result: Collaborative review result

        Returns:
            Dictionary with approval breakdown by role
        """
        breakdown: dict[str, Any] = {
            "total_reviewers": result.reviewer_count,
            "completed_reviewers": result.completed_reviewer_count,
            "by_role": {},
        }

        for role in ReviewerRole:
            role_assignments = [a for a in result.assignments if a.role == role]
            completed = [a for a in role_assignments if a.is_complete]
            approved = [a for a in role_assignments if a.has_approved]

            breakdown["by_role"][role.value] = {
                "total": len(role_assignments),
                "completed": len(completed),
                "approved": len(approved),
                "weight": self.get_role_weight(role),
                "can_vote": self.get_role_weight(role) > 0,
            }

        return breakdown

    def __repr__(self) -> str:
        """Return string representation."""
        active_count = len(self.get_active_reviews())
        return (
            f"CollaborativeReview("
            f"active_reviews={active_count}, "
            f"strategy={self._default_strategy.value}, "
            f"min_reviewers={self._min_reviewers})"
        )


def create_collaborative_review(
    strategy: Optional[ReviewStrategy] = None,
    min_reviewers: Optional[int] = None,
    timeout_hours: Optional[int] = None,
    notification_manager: Optional[NotificationManager] = None,
    state_dir: Optional[Union[str, Path]] = None,
) -> CollaborativeReview:
    """
    Factory function to create a configured collaborative review system.

    Args:
        strategy: Default approval strategy
        min_reviewers: Minimum reviewers required
        timeout_hours: Default timeout in hours
        notification_manager: Optional notification manager for sending notifications
        state_dir: Optional state directory for notification manager

    Returns:
        Configured CollaborativeReview instance

    Example:
        >>> from autoflow.collaboration.review import create_collaborative_review
        >>> review = create_collaborative_review(
        ...     strategy=ReviewStrategy.CONSENSUS,
        ...     min_reviewers=2
        ... )
    """
    return CollaborativeReview(
        default_strategy=strategy,
        min_reviewers=min_reviewers,
        default_timeout_hours=timeout_hours,
        notification_manager=notification_manager,
        state_dir=state_dir,
    )
