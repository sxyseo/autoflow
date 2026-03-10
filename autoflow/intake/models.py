"""
Autoflow Intake Models Module

Provides data models for issue intake from external sources like GitHub,
GitLab, and Linear. Includes models for issue sources and normalized issues.

Usage:
    from autoflow.intake.models import Issue, IssueSource, IssueStatus

    # Create an issue source
    source = IssueSource(
        type="github",
        name="my-repo",
        url="https://github.com/user/repo",
        config={"api_token": "token"}
    )

    # Create a normalized issue
    issue = Issue(
        source_id="gh-123",
        source=source,
        title="Fix bug",
        description="Detailed description",
        status=IssueStatus.OPEN,
        labels=["bug", "high-priority"]
    )
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Type of issue source."""

    GITHUB = "github"
    GITLAB = "gitlab"
    LINEAR = "linear"
    JIRA = "jira"
    CUSTOM = "custom"


class IssueStatus(str, Enum):
    """Status of an issue (normalized across sources)."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class IssuePriority(str, Enum):
    """Priority level of an issue."""

    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NO_PRIORITY = "no_priority"


class IssueSource(BaseModel):
    """
    Represents a source of issues (e.g., GitHub repository, GitLab project).

    Attributes:
        id: Unique identifier for the source
        type: Type of source (github, gitlab, linear, etc.)
        name: Human-readable name of the source
        url: URL to the source
        enabled: Whether this source is active
        config: Source-specific configuration (API tokens, etc.)
        metadata: Additional metadata about the source
        created_at: Timestamp when source was added
        updated_at: Timestamp when source was last updated

    Example:
        >>> source = IssueSource(
        ...     id="github-example",
        ...     type=SourceType.GITHUB,
        ...     name="example/repo",
        ...     url="https://github.com/example/repo",
        ...     enabled=True
        ... )
    """

    id: str
    type: SourceType
    name: str
    url: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


class Issue(BaseModel):
    """
    Represents a normalized issue from any source.

    This model provides a common representation of issues from different
    sources, with fields mapped from source-specific formats to a unified
    schema.

    Attributes:
        source_id: Unique identifier from the source system
        source: Reference to the IssueSource
        title: Issue title
        description: Detailed description/body
        status: Current status
        priority: Priority level
        labels: List of labels/tags
        assignees: List of assignee usernames/IDs
        milestone: Optional milestone name
        due_date: Optional due date
        created_at: Timestamp when issue was created
        updated_at: Timestamp when issue was last updated
        closed_at: Timestamp when issue was closed (if applicable)
        creator: Username/ID of issue creator
        source_url: URL to view the issue in the source system
        comments: List of comment data (simplified)
        metadata: Additional source-specific data
        synced_at: Timestamp of last sync with source

    Example:
        >>> issue = Issue(
        ...     source_id="GH-123",
        ...     source_id="gh-123",
        ...     source=source,
        ...     title="Fix authentication bug",
        ...     status=IssueStatus.IN_PROGRESS,
        ...     priority=IssuePriority.HIGH,
        ...     labels=["bug", "auth"]
        ... )
    """

    source_id: str
    source: IssueSource
    title: str
    description: str = ""
    status: IssueStatus = IssueStatus.TODO
    priority: IssuePriority = IssuePriority.NO_PRIORITY
    labels: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    milestone: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    creator: Optional[str] = None
    source_url: Optional[str] = None
    comments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    synced_at: Optional[datetime] = None

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()

    def close(self) -> None:
        """Mark the issue as closed."""
        self.status = IssueStatus.DONE
        self.closed_at = datetime.utcnow()
        self.touch()

    def is_closed(self) -> bool:
        """Check if the issue is closed."""
        return self.status in (
            IssueStatus.DONE,
            IssueStatus.CANCELLED,
            IssueStatus.ARCHIVED,
        )
