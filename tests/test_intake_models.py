"""
Unit Tests for Autoflow Intake Models

Tests the intake system data models including Issue, IssueSource, and related
enums for normalized issue representation from external sources.

These tests verify proper initialization, defaults, and methods of intake models.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.intake.models import (
    Issue,
    IssuePriority,
    IssueSource,
    IssueStatus,
    SourceType,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_source_data() -> dict[str, Any]:
    """Return sample issue source data for testing."""
    return {
        "id": "github-example",
        "type": SourceType.GITHUB,
        "name": "user/repo",
        "url": "https://github.com/user/repo",
        "enabled": True,
        "config": {"api_token": "test_token"},
    }


@pytest.fixture
def sample_issue_data() -> dict[str, Any]:
    """Return sample issue data for testing."""
    return {
        "source_id": "GH-123",
        "title": "Fix authentication bug",
        "description": "Users cannot log in with SSO",
        "status": IssueStatus.TODO,
        "priority": IssuePriority.HIGH,
        "labels": ["bug", "auth", "high-priority"],
        "assignees": ["alice", "bob"],
        "milestone": "v1.0",
        "creator": "charlie",
        "source_url": "https://github.com/user/repo/issues/123",
    }


@pytest.fixture
def issue_source() -> IssueSource:
    """Create a sample IssueSource for testing."""
    return IssueSource(
        id="github-test",
        type=SourceType.GITHUB,
        name="test/repo",
        url="https://github.com/test/repo",
        enabled=True,
    )


# ============================================================================
# SourceType Enum Tests
# ============================================================================


class TestSourceType:
    """Tests for SourceType enum."""

    def test_source_type_values(self) -> None:
        """Test SourceType enum values."""
        assert SourceType.GITHUB == "github"
        assert SourceType.GITLAB == "gitlab"
        assert SourceType.LINEAR == "linear"
        assert SourceType.JIRA == "jira"
        assert SourceType.CUSTOM == "custom"

    def test_source_type_is_string(self) -> None:
        """Test that SourceType values are strings."""
        assert isinstance(SourceType.GITHUB.value, str)

    def test_source_type_from_string(self) -> None:
        """Test creating SourceType from string."""
        source_type = SourceType("github")
        assert source_type == SourceType.GITHUB


# ============================================================================
# IssueStatus Enum Tests
# ============================================================================


class TestIssueStatus:
    """Tests for IssueStatus enum."""

    def test_issue_status_values(self) -> None:
        """Test IssueStatus enum values."""
        assert IssueStatus.BACKLOG == "backlog"
        assert IssueStatus.TODO == "todo"
        assert IssueStatus.IN_PROGRESS == "in_progress"
        assert IssueStatus.IN_REVIEW == "in_review"
        assert IssueStatus.DONE == "done"
        assert IssueStatus.CANCELLED == "cancelled"
        assert IssueStatus.ARCHIVED == "archived"

    def test_issue_status_is_string(self) -> None:
        """Test that IssueStatus values are strings."""
        assert isinstance(IssueStatus.TODO.value, str)

    def test_issue_status_from_string(self) -> None:
        """Test creating IssueStatus from string."""
        status = IssueStatus("in_progress")
        assert status == IssueStatus.IN_PROGRESS


# ============================================================================
# IssuePriority Enum Tests
# ============================================================================


class TestIssuePriority:
    """Tests for IssuePriority enum."""

    def test_issue_priority_values(self) -> None:
        """Test IssuePriority enum values."""
        assert IssuePriority.URGENT == "urgent"
        assert IssuePriority.HIGH == "high"
        assert IssuePriority.MEDIUM == "medium"
        assert IssuePriority.LOW == "low"
        assert IssuePriority.NO_PRIORITY == "no_priority"

    def test_issue_priority_is_string(self) -> None:
        """Test that IssuePriority values are strings."""
        assert isinstance(IssuePriority.HIGH.value, str)

    def test_issue_priority_from_string(self) -> None:
        """Test creating IssuePriority from string."""
        priority = IssuePriority("high")
        assert priority == IssuePriority.HIGH


# ============================================================================
# IssueSource Model Tests
# ============================================================================


class TestIssueSource:
    """Tests for IssueSource model."""

    def test_issue_source_init_minimal(self) -> None:
        """Test IssueSource initialization with minimal fields."""
        source = IssueSource(
            id="test-source",
            type=SourceType.GITHUB,
            name="test/repo",
            url="https://github.com/test/repo",
        )

        assert source.id == "test-source"
        assert source.type == SourceType.GITHUB
        assert source.name == "test/repo"
        assert source.url == "https://github.com/test/repo"
        assert source.enabled is True
        assert source.config == {}
        assert source.metadata == {}
        assert isinstance(source.created_at, datetime)
        assert isinstance(source.updated_at, datetime)

    def test_issue_source_init_full(self, sample_source_data: dict) -> None:
        """Test IssueSource initialization with all fields."""
        source = IssueSource(**sample_source_data)

        assert source.id == "github-example"
        assert source.type == SourceType.GITHUB
        assert source.enabled is True
        assert source.config == {"api_token": "test_token"}
        assert source.metadata == {}

    def test_issue_source_with_metadata(self) -> None:
        """Test IssueSource with custom metadata."""
        source = IssueSource(
            id="test-source",
            type=SourceType.GITLAB,
            name="test/project",
            url="https://gitlab.com/test/project",
            metadata={"webhook_id": "12345", "sync_enabled": True},
        )

        assert source.metadata == {"webhook_id": "12345", "sync_enabled": True}

    def test_issue_source_touch(self) -> None:
        """Test IssueSource.touch() updates timestamp."""
        source = IssueSource(
            id="test-source",
            type=SourceType.GITHUB,
            name="test/repo",
            url="https://github.com/test/repo",
        )
        original_updated = source.updated_at

        # Small delay to ensure different timestamp
        import time

        time.sleep(0.01)
        source.touch()

        assert source.updated_at > original_updated

    def test_issue_source_disabled(self) -> None:
        """Test IssueSource can be disabled."""
        source = IssueSource(
            id="test-source",
            type=SourceType.LINEAR,
            name="Test Workspace",
            url="https://linear.app/test",
            enabled=False,
        )

        assert source.enabled is False


# ============================================================================
# Issue Model Tests
# ============================================================================


class TestIssue:
    """Tests for Issue model."""

    def test_issue_init_minimal(self, issue_source: IssueSource) -> None:
        """Test Issue initialization with minimal fields."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test Issue",
        )

        assert issue.source_id == "GH-1"
        assert issue.source == issue_source
        assert issue.title == "Test Issue"
        assert issue.description == ""
        assert issue.status == IssueStatus.TODO
        assert issue.priority == IssuePriority.NO_PRIORITY
        assert issue.labels == []
        assert issue.assignees == []
        assert issue.milestone is None
        assert issue.due_date is None
        assert issue.creator is None
        assert issue.source_url is None
        assert issue.comments == []
        assert issue.metadata == {}
        assert issue.synced_at is None

    def test_issue_init_full(self, issue_source: IssueSource, sample_issue_data: dict) -> None:
        """Test Issue initialization with all fields."""
        issue = Issue(source=issue_source, **sample_issue_data)

        assert issue.source_id == "GH-123"
        assert issue.title == "Fix authentication bug"
        assert issue.description == "Users cannot log in with SSO"
        assert issue.status == IssueStatus.TODO
        assert issue.priority == IssuePriority.HIGH
        assert issue.labels == ["bug", "auth", "high-priority"]
        assert issue.assignees == ["alice", "bob"]
        assert issue.milestone == "v1.0"
        assert issue.creator == "charlie"
        assert issue.source_url == "https://github.com/user/repo/issues/123"

    def test_issue_with_due_date(self, issue_source: IssueSource) -> None:
        """Test Issue with due date."""
        due_date = datetime.utcnow() + timedelta(days=7)
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Issue with due date",
            due_date=due_date,
        )

        assert issue.due_date == due_date

    def test_issue_with_comments(self, issue_source: IssueSource) -> None:
        """Test Issue with comments."""
        comments = [
            {
                "author": "alice",
                "body": "First comment",
                "created_at": "2024-01-01T10:00:00Z",
            },
            {
                "author": "bob",
                "body": "Second comment",
                "created_at": "2024-01-02T10:00:00Z",
            },
        ]

        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Issue with comments",
            comments=comments,
        )

        assert len(issue.comments) == 2
        assert issue.comments[0]["author"] == "alice"

    def test_issue_with_metadata(self, issue_source: IssueSource) -> None:
        """Test Issue with custom metadata."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Issue with metadata",
            metadata={
                "category": "bug",
                "number": 123,
                "pull_request": False,
            },
        )

        assert issue.metadata["category"] == "bug"
        assert issue.metadata["number"] == 123

    def test_issue_touch(self, issue_source: IssueSource) -> None:
        """Test Issue.touch() updates timestamp."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test Issue",
        )
        original_updated = issue.updated_at

        import time

        time.sleep(0.01)
        issue.touch()

        assert issue.updated_at > original_updated

    def test_issue_close(self, issue_source: IssueSource) -> None:
        """Test Issue.close() marks issue as closed."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test Issue",
            status=IssueStatus.IN_PROGRESS,
        )

        assert issue.closed_at is None

        issue.close()

        assert issue.status == IssueStatus.DONE
        assert isinstance(issue.closed_at, datetime)

    def test_issue_is_closed_true(self, issue_source: IssueSource) -> None:
        """Test Issue.is_closed() returns True for closed statuses."""
        for status in [IssueStatus.DONE, IssueStatus.CANCELLED, IssueStatus.ARCHIVED]:
            issue = Issue(
                source_id="GH-1",
                source=issue_source,
                title="Test Issue",
                status=status,
            )

            assert issue.is_closed() is True

    def test_issue_is_closed_false(self, issue_source: IssueSource) -> None:
        """Test Issue.is_closed() returns False for open statuses."""
        for status in [IssueStatus.BACKLOG, IssueStatus.TODO, IssueStatus.IN_PROGRESS, IssueStatus.IN_REVIEW]:
            issue = Issue(
                source_id="GH-1",
                source=issue_source,
                title="Test Issue",
                status=status,
            )

            assert issue.is_closed() is False

    def test_issue_synced_at(self, issue_source: IssueSource) -> None:
        """Test Issue with synced_at timestamp."""
        synced_at = datetime.utcnow()
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test Issue",
            synced_at=synced_at,
        )

        assert issue.synced_at == synced_at


# ============================================================================
# Edge Cases and Validation Tests
# ============================================================================


class TestIntakeModelsEdgeCases:
    """Tests for edge cases and validation."""

    def test_issue_source_with_all_types(self) -> None:
        """Test IssueSource works with all source types."""
        for source_type in SourceType:
            source = IssueSource(
                id=f"{source_type.value}-test",
                type=source_type,
                name=f"Test {source_type.value}",
                url=f"https://example.com/{source_type.value}",
            )

            assert source.type == source_type

    def test_issue_with_empty_labels(self, issue_source: IssueSource) -> None:
        """Test Issue with empty labels list."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test Issue",
            labels=[],
        )

        assert issue.labels == []

    def test_issue_with_special_characters_in_title(self, issue_source: IssueSource) -> None:
        """Test Issue with special characters in title."""
        title = "Fix: 🐛 Bug with 'quotes' and \"double quotes\""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title=title,
        )

        assert issue.title == title

    def test_issue_with_unicode_in_description(self, issue_source: IssueSource) -> None:
        """Test Issue with unicode characters in description."""
        description = "Description with 中文, 日本語, and emoji 🎉"
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            description=description,
        )

        assert issue.description == description

    def test_issue_with_long_description(self, issue_source: IssueSource) -> None:
        """Test Issue with very long description."""
        long_desc = "A" * 10000
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            description=long_desc,
        )

        assert len(issue.description) == 10000

    def test_multiple_issues_same_source(self, issue_source: IssueSource) -> None:
        """Test multiple issues can reference the same source."""
        issue1 = Issue(source_id="GH-1", source=issue_source, title="Issue 1")
        issue2 = Issue(source_id="GH-2", source=issue_source, title="Issue 2")

        assert issue1.source == issue2.source
        assert issue1.source_id != issue2.source_id
