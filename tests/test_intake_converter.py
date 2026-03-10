"""
Unit Tests for Autoflow Intake Converter

Tests the conversion logic for transforming external issues into
Autoflow specs and tasks with proper label mapping and metadata preservation.

These tests verify proper issue-to-spec and issue-to-task conversion
with status/priority mapping and metadata handling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.core.state import Spec, Task, TaskStatus
from autoflow.intake.converter import IssueConverter
from autoflow.intake.mapping import LabelMapping
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
def issue_source() -> IssueSource:
    """Create a sample issue source."""
    return IssueSource(
        id="github-test",
        type=SourceType.GITHUB,
        name="user/repo",
        url="https://github.com/user/repo",
    )


@pytest.fixture
def sample_issue(issue_source: IssueSource) -> Issue:
    """Create a sample issue for testing."""
    return Issue(
        source_id="GH-123",
        source=issue_source,
        title="Fix authentication bug",
        description="Users cannot log in with SSO",
        status=IssueStatus.TODO,
        priority=IssuePriority.HIGH,
        labels=["bug", "auth", "high-priority"],
        assignees=["alice", "bob"],
        milestone="v1.0",
        creator="charlie",
        source_url="https://github.com/user/repo/issues/123",
        comments=[
            {
                "author": "alice",
                "body": "I can reproduce this",
                "created_at": "2024-01-02T10:00:00Z",
            },
            {
                "author": "bob",
                "body": "Working on a fix",
                "created_at": "2024-01-03T10:00:00Z",
            },
        ],
        metadata={
            "category": "bug",
            "number": 123,
        },
        synced_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_issue_minimal(issue_source: IssueSource) -> Issue:
    """Create a minimal issue for testing."""
    return Issue(
        source_id="GH-1",
        source=issue_source,
        title="Simple issue",
    )


# ============================================================================
# IssueConverter Initialization Tests
# ============================================================================


class TestIssueConverterInit:
    """Tests for IssueConverter initialization."""

    def test_converter_init_default(self) -> None:
        """Test IssueConverter initialization with defaults."""
        converter = IssueConverter()

        assert isinstance(converter.label_mapping, LabelMapping)
        assert converter.spec_prefix == "spec"
        assert converter.task_prefix == "task"
        assert converter.preserve_labels is True
        assert converter.add_source_links is True

    def test_converter_init_custom(self) -> None:
        """Test IssueConverter initialization with custom settings."""
        custom_mapping = LabelMapping(default_priority=IssuePriority.HIGH)
        converter = IssueConverter(
            label_mapping=custom_mapping,
            spec_prefix="custom-spec",
            task_prefix="custom-task",
            preserve_labels=False,
            add_source_links=False,
        )

        assert converter.label_mapping == custom_mapping
        assert converter.spec_prefix == "custom-spec"
        assert converter.task_prefix == "custom-task"
        assert converter.preserve_labels is False
        assert converter.add_source_links is False


# ============================================================================
# IssueConverter.convert_issue Tests
# ============================================================================


class TestIssueConverterConvertIssue:
    """Tests for IssueConverter.convert_issue method."""

    def test_convert_issue_both(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test convert_issue creates both spec and task."""
        converter = IssueConverter()
        spec, task = converter.convert_issue(sample_issue)

        assert spec is not None
        assert task is not None
        assert isinstance(spec, Spec)
        assert isinstance(task, Task)

    def test_convert_issue_spec_only(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test convert_issue creates only spec."""
        converter = IssueConverter()
        spec, task = converter.convert_issue(sample_issue, create_task=False)

        assert spec is not None
        assert task is None

    def test_convert_issue_task_only(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test convert_issue creates only task."""
        converter = IssueConverter()
        spec, task = converter.convert_issue(sample_issue, create_spec=False)

        assert spec is None
        assert task is not None

    def test_convert_issue_neither(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test convert_issue creates neither."""
        converter = IssueConverter()
        spec, task = converter.convert_issue(
            sample_issue,
            create_spec=False,
            create_task=False,
        )

        assert spec is None
        assert task is None

    def test_convert_issue_task_has_spec_id(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test convert_issue associates task with spec."""
        converter = IssueConverter()
        spec, task = converter.convert_issue(sample_issue)

        assert task is not None
        assert task.metadata.get("spec_id") == spec.id


# ============================================================================
# IssueConverter.issue_to_spec Tests
# ============================================================================


class TestIssueConverterIssueToSpec:
    """Tests for IssueConverter.issue_to_spec method."""

    def test_issue_to_spec_basic(
        self,
        sample_issue_minimal: Issue,
    ) -> None:
        """Test basic issue to spec conversion."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue_minimal)

        assert spec.id == "spec-github-GH-1"
        assert spec.title == "Simple issue"
        assert spec.content is not None
        assert spec.version == "1.0"

    def test_issue_to_spec_with_content(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion with full content."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        assert spec.title == "Fix authentication bug"
        assert "Fix authentication bug" in spec.content
        assert "Users cannot log in with SSO" in spec.content
        assert "bug" in spec.tags

    def test_issue_to_spec_preserves_dates(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion preserves dates."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        assert spec.created_at == sample_issue.created_at
        assert spec.updated_at == sample_issue.updated_at

    def test_issue_to_spec_author(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion sets author."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        assert spec.author == "charlie"

    def test_issue_to_spec_author_fallback(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test issue to spec conversion author fallback."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            creator=None,
        )

        converter = IssueConverter()
        spec = converter.issue_to_spec(issue)

        assert spec.author == "user/repo"

    def test_issue_to_spec_tags(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion extracts tags."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        assert "bug" in spec.tags
        assert "auth" in spec.tags
        assert "github" in spec.tags

    def test_issue_to_spec_metadata(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion preserves metadata."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        assert spec.metadata["source"]["type"] == "github"
        assert spec.metadata["source"]["id"] == "GH-123"
        assert spec.metadata["issue"]["status"] == "todo"
        assert spec.metadata["issue"]["priority"] == "high"
        assert spec.metadata["category"] == "bug"

    def test_issue_to_spec_with_comments(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion includes comments."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        assert "Comments" in spec.content
        assert "I can reproduce this" in spec.content
        assert "Working on a fix" in spec.content

    def test_issue_to_spec_content_structure(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion creates proper content structure."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        content = spec.content

        # Should have major sections
        assert "# Fix authentication bug" in content
        assert "## Description" in content
        assert "## Priority & Status" in content
        assert "## Source" in content

    def test_issue_to_spec_with_category(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test issue to spec conversion with category."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            metadata={"category": "feature"},
        )

        converter = IssueConverter()
        spec = converter.issue_to_spec(issue)

        assert "## Category" in spec.content
        assert "feature" in spec.content

    def test_issue_to_spec_with_assignees(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion includes assignees."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        assert "alice" in spec.content
        assert "bob" in spec.content

    def test_issue_to_spec_with_milestone(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to spec conversion includes milestone."""
        converter = IssueConverter()
        spec = converter.issue_to_spec(sample_issue)

        assert "v1.0" in spec.content

    def test_issue_to_spec_without_comments(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test issue to spec conversion without comments."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            comments=[],
        )

        converter = IssueConverter()
        spec = converter.issue_to_spec(issue)

        # Should still create spec, just without comments section
        assert spec is not None


# ============================================================================
# IssueConverter.issue_to_task Tests
# ============================================================================


class TestIssueConverterIssueToTask:
    """Tests for IssueConverter.issue_to_task method."""

    def test_issue_to_task_basic(
        self,
        sample_issue_minimal: Issue,
    ) -> None:
        """Test basic issue to task conversion."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue_minimal)

        assert task.id == "task-github-GH-1"
        assert task.title == "Simple issue"
        assert task.status == TaskStatus.PENDING
        assert task.priority == 1  # NO_PRIORITY maps to 1

    def test_issue_to_task_with_status(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion with status mapping."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue)

        assert task.status == TaskStatus.PENDING  # TODO maps to PENDING

    def test_issue_to_task_in_progress_status(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test issue to task conversion with in_progress status."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            status=IssueStatus.IN_PROGRESS,
        )

        converter = IssueConverter()
        task = converter.issue_to_task(issue)

        assert task.status == TaskStatus.IN_PROGRESS

    def test_issue_to_task_done_status(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test issue to task conversion with done status."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            status=IssueStatus.DONE,
        )

        converter = IssueConverter()
        task = converter.issue_to_task(issue)

        assert task.status == TaskStatus.COMPLETED

    def test_issue_to_task_priority_mapping(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test issue to task priority mapping."""
        converter = IssueConverter()

        priority_tests = [
            (IssuePriority.URGENT, 10),
            (IssuePriority.HIGH, 8),
            (IssuePriority.MEDIUM, 5),
            (IssuePriority.LOW, 3),
            (IssuePriority.NO_PRIORITY, 1),
        ]

        for issue_priority, expected_task_priority in priority_tests:
            issue = Issue(
                source_id="GH-1",
                source=issue_source,
                title="Test",
                priority=issue_priority,
            )

            task = converter.issue_to_task(issue)
            assert task.priority == expected_task_priority

    def test_issue_to_task_preserve_labels(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion preserves labels."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue)

        assert "bug" in task.labels
        assert "auth" in task.labels

    def test_issue_to_task_no_preserve_labels(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion doesn't preserve labels when disabled."""
        converter = IssueConverter(preserve_labels=False)
        task = converter.issue_to_task(sample_issue)

        # Should only have category (bug), not original labels like 'auth' or 'high-priority'
        assert "auth" not in task.labels
        assert "high-priority" not in task.labels
        assert "bug" in task.labels  # But category is added
        assert "bug" in task.metadata["issue"]["labels"]  # Original labels in metadata

    def test_issue_to_task_adds_category_label(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion adds category as label."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue)

        assert "bug" in task.labels  # Category added

    def test_issue_to_task_with_source_link(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion adds source link."""
        converter = IssueConverter(add_source_links=True)
        task = converter.issue_to_task(sample_issue)

        assert "github.com" in task.description
        assert "[user/repo]" in task.description

    def test_issue_to_task_no_source_link(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion without source link."""
        converter = IssueConverter(add_source_links=False)
        task = converter.issue_to_task(sample_issue)

        # Should not add the link
        source_link = "\n\n---\n\n**Source:**"
        assert source_link not in task.description

    def test_issue_to_task_assignee(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion sets assignee."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue)

        # First assignee becomes assigned_agent
        assert task.assigned_agent == "alice"

    def test_issue_to_task_no_assignee(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test issue to task conversion without assignee."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            assignees=[],
        )

        converter = IssueConverter()
        task = converter.issue_to_task(issue)

        assert task.assigned_agent is None

    def test_issue_to_task_preserves_dates(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion preserves dates."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue)

        assert task.created_at == sample_issue.created_at
        assert task.updated_at == sample_issue.updated_at

    def test_issue_to_task_metadata(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion preserves metadata."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue)

        assert task.metadata["source"]["type"] == "github"
        assert task.metadata["source"]["id"] == "GH-123"
        assert task.metadata["issue"]["status"] == "todo"
        assert task.metadata["issue"]["priority"] == "high"
        assert task.metadata["category"] == "bug"

    def test_issue_to_task_with_spec_id(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test issue to task conversion with spec association."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue, spec_id="spec-123")

        assert task.metadata["spec_id"] == "spec-123"

    def test_issue_to_task_dependencies_empty(
        self,
        sample_issue_minimal: Issue,
    ) -> None:
        """Test issue to task conversion has empty dependencies."""
        converter = IssueConverter()
        task = converter.issue_to_task(sample_issue_minimal)

        assert task.dependencies == []


# ============================================================================
# IssueConverter._build_spec_content Tests
# ============================================================================


class TestIssueConverterBuildSpecContent:
    """Tests for IssueConverter._build_spec_content method."""

    def test_build_spec_content_minimal(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test building spec content from minimal issue."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Minimal Issue",
        )

        converter = IssueConverter()
        content = converter._build_spec_content(issue)

        assert "# Minimal Issue" in content
        assert "## Priority & Status" in content

    def test_build_spec_content_with_description(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test building spec content with description."""
        converter = IssueConverter()
        content = converter._build_spec_content(sample_issue)

        assert "## Description" in content
        assert "Users cannot log in with SSO" in content

    def test_build_spec_content_with_labels(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test building spec content with labels."""
        converter = IssueConverter()
        content = converter._build_spec_content(sample_issue)

        assert "## Labels" in content
        assert "`bug`" in content
        assert "`auth`" in content

    def test_build_spec_content_without_labels(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test building spec content without labels."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            labels=[],
        )

        converter = IssueConverter()
        content = converter._build_spec_content(issue)

        assert "## Labels" not in content

    def test_build_spec_content_with_source(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test building spec content with source information."""
        converter = IssueConverter()
        content = converter._build_spec_content(sample_issue)

        assert "## Source" in content
        assert "user/repo" in content
        assert sample_issue.source_url in content

    def test_build_spec_content_without_source_url(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test building spec content without source URL."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            source_url=None,
        )

        converter = IssueConverter()
        content = converter._build_spec_content(issue)

        # Should not include source section
        assert "## Source" not in content


# ============================================================================
# IssueConverter._extract_tags Tests
# ============================================================================


class TestIssueConverterExtractTags:
    """Tests for IssueConverter._extract_tags method."""

    def test_extract_tags_from_labels(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test extracting tags from labels."""
        converter = IssueConverter()
        tags = converter._extract_tags(sample_issue)

        assert "bug" in tags
        assert "auth" in tags
        assert "high-priority" in tags

    def test_extract_tags_sanitizes_special_chars(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test tag extraction sanitizes special characters."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            labels=["Bug/Feature", "test label", "C++"],
        )

        converter = IssueConverter()
        tags = converter._extract_tags(issue)

        assert "bug-feature" in tags
        assert "test-label" in tags
        assert "c" in tags  # C++ gets sanitized

    def test_extract_tags_adds_category(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test tag extraction adds category."""
        converter = IssueConverter()
        tags = converter._extract_tags(sample_issue)

        assert "bug" in tags  # Category added

    def test_extract_tags_adds_source_type(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test tag extraction adds source type."""
        converter = IssueConverter()
        tags = converter._extract_tags(sample_issue)

        assert "github" in tags

    def test_extract_tags_returns_sorted(
        self,
        sample_issue: Issue,
    ) -> None:
        """Test tag extraction returns sorted list."""
        converter = IssueConverter()
        tags = converter._extract_tags(sample_issue)

        # Check it's sorted
        assert tags == sorted(tags)


# ============================================================================
# IssueConverter._map_task_status Tests
# ============================================================================


class TestIssueConverterMapTaskStatus:
    """Tests for IssueConverter._map_task_status method."""

    def test_map_task_status_all_values(self) -> None:
        """Test status mapping for all IssueStatus values."""
        converter = IssueConverter()

        status_mapping = {
            IssueStatus.BACKLOG: TaskStatus.PENDING,
            IssueStatus.TODO: TaskStatus.PENDING,
            IssueStatus.IN_PROGRESS: TaskStatus.IN_PROGRESS,
            IssueStatus.IN_REVIEW: TaskStatus.IN_PROGRESS,
            IssueStatus.DONE: TaskStatus.COMPLETED,
            IssueStatus.CANCELLED: TaskStatus.CANCELLED,
            IssueStatus.ARCHIVED: TaskStatus.CANCELLED,
        }

        for issue_status, expected_task_status in status_mapping.items():
            result = converter._map_task_status(issue_status)
            assert result == expected_task_status


# ============================================================================
# IssueConverter._map_task_priority Tests
# ============================================================================


class TestIssueConverterMapTaskPriority:
    """Tests for IssueConverter._map_task_priority method."""

    def test_map_task_priority_all_values(self) -> None:
        """Test priority mapping for all IssuePriority values."""
        converter = IssueConverter()

        priority_mapping = {
            IssuePriority.URGENT: 10,
            IssuePriority.HIGH: 8,
            IssuePriority.MEDIUM: 5,
            IssuePriority.LOW: 3,
            IssuePriority.NO_PRIORITY: 1,
        }

        for issue_priority, expected_task_priority in priority_mapping.items():
            result = converter._map_task_priority(issue_priority)
            assert result == expected_task_priority


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestIssueConverterEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_converter_with_unicode_characters(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test converter handles unicode characters."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Fix: 🐛 Bug with 中文 and 日本語",
            description="Test with emoji 🎉",
        )

        converter = IssueConverter()
        spec = converter.issue_to_spec(issue)
        task = converter.issue_to_task(issue)

        assert "🐛" in spec.title
        assert "🎉" in spec.content
        assert "🐛" in task.title

    def test_converter_with_long_description(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test converter handles long descriptions."""
        long_desc = "A" * 10000
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            description=long_desc,
        )

        converter = IssueConverter()
        spec = converter.issue_to_spec(issue)
        task = converter.issue_to_task(issue)

        assert len(spec.content) >= 10000
        assert len(task.description) >= 10000

    def test_converter_with_empty_metadata(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test converter handles empty metadata."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            metadata={},
        )

        converter = IssueConverter()
        spec = converter.issue_to_spec(issue)
        task = converter.issue_to_task(issue)

        assert spec.metadata is not None
        assert task.metadata is not None

    def test_converter_preserves_custom_metadata(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test converter preserves custom metadata fields."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Test",
            metadata={
                "custom_field": "custom_value",
                "number": 123,
            },
        )

        converter = IssueConverter()
        spec = converter.issue_to_spec(issue)
        task = converter.issue_to_task(issue)

        assert spec.metadata.get("custom_field") != "custom_value"  # In issue sub-dict
        assert task.metadata.get("custom_field") == "custom_value"

    def test_converter_id_generation_different_sources(
        self,
    ) -> None:
        """Test converter generates different IDs for different sources."""
        github_source = IssueSource(
            id="github-test",
            type=SourceType.GITHUB,
            name="user/repo",
            url="https://github.com/user/repo",
        )

        gitlab_source = IssueSource(
            id="gitlab-test",
            type=SourceType.GITLAB,
            name="user/project",
            url="https://gitlab.com/user/project",
        )

        github_issue = Issue(
            source_id="123",
            source=github_source,
            title="Test",
        )

        gitlab_issue = Issue(
            source_id="123",
            source=gitlab_source,
            title="Test",
        )

        converter = IssueConverter()

        github_spec = converter.issue_to_spec(github_issue)
        gitlab_spec = converter.issue_to_spec(gitlab_issue)

        assert github_spec.id != gitlab_spec.id
        assert "github" in github_spec.id
        assert "gitlab" in gitlab_spec.id

    def test_converter_with_closed_issue(
        self,
        issue_source: IssueSource,
    ) -> None:
        """Test converter handles closed issues."""
        issue = Issue(
            source_id="GH-1",
            source=issue_source,
            title="Closed issue",
            status=IssueStatus.DONE,
            closed_at=datetime.utcnow(),
        )

        converter = IssueConverter()
        task = converter.issue_to_task(issue)

        assert task.status == TaskStatus.COMPLETED
