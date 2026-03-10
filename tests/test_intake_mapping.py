"""
Unit Tests for Autoflow Intake Mapping

Tests the label mapping and issue transformation logic for converting
external issues from GitHub, GitLab, and Linear into normalized Issue objects.

These tests verify proper label matching, priority extraction, and
issue data transformation from various sources.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.intake.mapping import LabelMapping, LabelRule, IssueTransformer
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
def sample_github_issue_data() -> dict[str, Any]:
    """Return sample GitHub issue API response data."""
    return {
        "id": 123456789,
        "number": 123,
        "title": "Fix authentication bug",
        "body": "Users cannot log in with SSO",
        "state": "open",
        "labels": [
            {"name": "bug"},
            {"name": "auth"},
            {"name": "priority:high"},
        ],
        "assignees": [
            {"login": "alice"},
            {"login": "bob"},
        ],
        "milestone": {"title": "v1.0"},
        "user": {"login": "charlie"},
        "html_url": "https://github.com/user/repo/issues/123",
        "pull_request": None,
        "draft": False,
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-02T10:00:00Z",
        "closed_at": None,
    }


@pytest.fixture
def sample_gitlab_issue_data() -> dict[str, Any]:
    """Return sample GitLab issue API response data."""
    return {
        "id": 456,
        "iid": 789,
        "title": "Add new feature",
        "description": "Implement user preferences",
        "state": "opened",
        "labels": ["feature", "enhancement", "priority:medium"],
        "assignees": [
            {"username": "alice"},
        ],
        "milestone": {"title": "v2.0"},
        "author": {"username": "bob"},
        "web_url": "https://gitlab.com/user/project/issues/789",
        "references": {"full": "user/project#789"},
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-02T10:00:00Z",
        "closed_at": None,
    }


@pytest.fixture
def sample_linear_issue_data() -> dict[str, Any]:
    """Return sample Linear issue API response data."""
    return {
        "id": "LIN-123",
        "title": "Optimize database queries",
        "description": "Improve query performance",
        "identifier": "ENG-456",
        "state": {
            "type": "in_progress",
        },
        "priority": {
            "priority": "high",
        },
        "labels": [
            {"name": "performance"},
            {"name": "backend"},
        ],
        "assignee": {
            "name": "Alice Johnson",
            "displayName": "alice",
        },
        "cycle": {
            "name": "Sprint 1",
        },
        "creator": {
            "name": "Bob Smith",
        },
        "team": {
            "name": "Engineering",
        },
        "url": "https://linear.app/example/issue/ENG-456",
        "createdAt": "2024-01-01T10:00:00Z",
        "updatedAt": "2024-01-02T10:00:00Z",
        "completedAt": None,
    }


@pytest.fixture
def github_source() -> IssueSource:
    """Create a sample GitHub issue source."""
    return IssueSource(
        id="github-test",
        type=SourceType.GITHUB,
        name="user/repo",
        url="https://github.com/user/repo",
    )


@pytest.fixture
def gitlab_source() -> IssueSource:
    """Create a sample GitLab issue source."""
    return IssueSource(
        id="gitlab-test",
        type=SourceType.GITLAB,
        name="user/project",
        url="https://gitlab.com/user/project",
    )


@pytest.fixture
def linear_source() -> IssueSource:
    """Create a sample Linear issue source."""
    return IssueSource(
        id="linear-test",
        type=SourceType.LINEAR,
        name="Example Workspace",
        url="https://linear.app/example",
    )


# ============================================================================
# LabelRule Tests
# ============================================================================


class TestLabelRule:
    """Tests for LabelRule model."""

    def test_label_rule_init_simple(self) -> None:
        """Test LabelRule initialization with simple pattern."""
        rule = LabelRule(pattern="bug", priority=IssuePriority.HIGH)

        assert rule.pattern == "bug"
        assert rule.priority == IssuePriority.HIGH
        assert rule.category is None
        assert rule.is_regex is False

    def test_label_rule_init_regex(self) -> None:
        """Test LabelRule initialization with regex pattern."""
        rule = LabelRule(
            pattern="bug.*",
            priority=IssuePriority.URGENT,
            category="bug",
            is_regex=True,
        )

        assert rule.pattern == "bug.*"
        assert rule.priority == IssuePriority.URGENT
        assert rule.category == "bug"
        assert rule.is_regex is True

    def test_label_rule_category_only(self) -> None:
        """Test LabelRule with only category."""
        rule = LabelRule(pattern="feature", category="enhancement")

        assert rule.category == "enhancement"
        assert rule.priority is None

    def test_label_rule_invalid_pattern(self) -> None:
        """Test LabelRule with invalid regex pattern."""
        # Should not raise on init, but will fail when used
        rule = LabelRule(pattern="[invalid(", is_regex=True)
        assert rule.pattern == "[invalid("


# ============================================================================
# LabelMapping Tests
# ============================================================================


class TestLabelMapping:
    """Tests for LabelMapping model."""

    def test_label_mapping_init_default(self) -> None:
        """Test LabelMapping initialization with default rules."""
        mapping = LabelMapping()

        assert len(mapping.priority_rules) > 0
        assert len(mapping.category_rules) > 0
        assert mapping.default_priority == IssuePriority.NO_PRIORITY
        assert mapping.default_category is None

    def test_label_mapping_init_custom(self) -> None:
        """Test LabelMapping initialization with custom rules."""
        custom_rules = [
            LabelRule(pattern="urgent", priority=IssuePriority.URGENT),
        ]
        mapping = LabelMapping(
            priority_rules=custom_rules,
            default_priority=IssuePriority.MEDIUM,
        )

        assert len(mapping.priority_rules) == 1
        assert mapping.default_priority == IssuePriority.MEDIUM

    def test_get_priority_exact_match(self) -> None:
        """Test get_priority with exact label match."""
        mapping = LabelMapping()
        priority = mapping.get_priority("urgent")

        assert priority == IssuePriority.URGENT

    def test_get_priority_regex_match(self) -> None:
        """Test get_priority with regex pattern match."""
        mapping = LabelMapping()
        priority = mapping.get_priority("high-priority")

        assert priority == IssuePriority.HIGH

    def test_get_priority_case_insensitive(self) -> None:
        """Test get_priority is case insensitive."""
        mapping = LabelMapping()
        priority = mapping.get_priority("URGENT")

        assert priority == IssuePriority.URGENT

    def test_get_priority_no_match(self) -> None:
        """Test get_priority returns None when no match."""
        mapping = LabelMapping()
        priority = mapping.get_priority("unknown-label")

        assert priority is None

    def test_get_category_exact_match(self) -> None:
        """Test get_category with exact label match."""
        mapping = LabelMapping()
        category = mapping.get_category("bug")

        assert category == "bug"

    def test_get_category_regex_match(self) -> None:
        """Test get_category with regex pattern match."""
        mapping = LabelMapping()
        category = mapping.get_category("bug:authentication")

        assert category == "bug"

    def test_get_category_no_match(self) -> None:
        """Test get_category returns None when no match."""
        mapping = LabelMapping()
        category = mapping.get_category("unknown")

        assert category is None

    def test_extract_priority_single_label(self) -> None:
        """Test extract_priority with single priority label."""
        mapping = LabelMapping()
        priority = mapping.extract_priority(["urgent"])

        assert priority == IssuePriority.URGENT

    def test_extract_priority_multiple_labels(self) -> None:
        """Test extract_priority picks highest priority."""
        mapping = LabelMapping()
        priority = mapping.extract_priority(["low", "urgent", "medium"])

        # Should pick urgent (highest)
        assert priority == IssuePriority.URGENT

    def test_extract_priority_no_match(self) -> None:
        """Test extract_priority returns default when no match."""
        mapping = LabelMapping()
        priority = mapping.extract_priority(["unknown", "labels"])

        assert priority == IssuePriority.NO_PRIORITY

    def test_extract_priority_custom_default(self) -> None:
        """Test extract_priority with custom default."""
        mapping = LabelMapping(default_priority=IssuePriority.MEDIUM)
        priority = mapping.extract_priority(["unknown"])

        assert priority == IssuePriority.MEDIUM

    def test_extract_category_first_match(self) -> None:
        """Test extract_category returns first matching category."""
        mapping = LabelMapping()
        category = mapping.extract_category(["bug", "feature"])

        assert category == "bug"

    def test_extract_category_no_match(self) -> None:
        """Test extract_category returns default when no match."""
        mapping = LabelMapping()
        category = mapping.extract_category(["unknown", "labels"])

        assert category is None

    def test_extract_category_custom_default(self) -> None:
        """Test extract_category with custom default."""
        mapping = LabelMapping(default_category="other")
        category = mapping.extract_category(["unknown"])

        assert category == "other"

    def test_extract_priority_highest_wins(self) -> None:
        """Test that extract_priority returns highest priority found."""
        mapping = LabelMapping()
        labels = ["low", "medium", "high", "urgent"]

        # Test all priority levels
        assert mapping.extract_priority(["low"]) == IssuePriority.LOW
        assert mapping.extract_priority(["medium"]) == IssuePriority.MEDIUM
        assert mapping.extract_priority(["high"]) == IssuePriority.HIGH
        assert mapping.extract_priority(["urgent"]) == IssuePriority.URGENT


# ============================================================================
# IssueTransformer Tests
# ============================================================================


class TestIssueTransformer:
    """Tests for IssueTransformer class."""

    def test_transformer_init_default(self) -> None:
        """Test IssueTransformer initialization with default mapping."""
        transformer = IssueTransformer()

        assert isinstance(transformer.label_mapping, LabelMapping)

    def test_transformer_init_custom_mapping(self) -> None:
        """Test IssueTransformer initialization with custom mapping."""
        custom_mapping = LabelMapping(default_priority=IssuePriority.HIGH)
        transformer = IssueTransformer(label_mapping=custom_mapping)

        assert transformer.label_mapping == custom_mapping


class TestIssueTransformerGitHub:
    """Tests for IssueTransformer.from_github method."""

    def test_from_github_basic(
        self,
        sample_github_issue_data: dict,
        github_source: IssueSource,
    ) -> None:
        """Test basic GitHub issue transformation."""
        transformer = IssueTransformer()
        issue = transformer.from_github(sample_github_issue_data, github_source)

        assert issue.source_id == "123456789"
        assert issue.title == "Fix authentication bug"
        assert issue.description == "Users cannot log in with SSO"
        assert issue.source == github_source
        assert issue.status == IssueStatus.TODO
        assert issue.priority == IssuePriority.HIGH
        assert "bug" in issue.labels
        assert "auth" in issue.labels

    def test_from_github_closed_issue(
        self,
        github_source: IssueSource,
    ) -> None:
        """Test GitHub issue transformation for closed issue."""
        data = {
            "id": 123,
            "title": "Closed issue",
            "body": "This is closed",
            "state": "closed",
            "labels": [],
            "assignees": [],
            "user": {"login": "test"},
            "html_url": "https://github.com/test/test/issues/1",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T10:00:00Z",
            "closed_at": "2024-01-03T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_github(data, github_source)

        assert issue.status == IssueStatus.DONE
        assert issue.closed_at is not None

    def test_from_github_pull_request(
        self,
        github_source: IssueSource,
    ) -> None:
        """Test GitHub pull request transformation."""
        data = {
            "id": 123,
            "title": "Add feature",
            "body": "PR description",
            "state": "open",
            "draft": True,
            "pull_request": {"url": "https://api.github.com/repos/test/test/pulls/1"},
            "labels": [],
            "assignees": [],
            "user": {"login": "test"},
            "html_url": "https://github.com/test/test/pull/1",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_github(data, github_source)

        assert issue.status == IssueStatus.TODO
        assert issue.metadata["pull_request"] is True

    def test_from_github_assignees(
        self,
        github_source: IssueSource,
    ) -> None:
        """Test GitHub issue with assignees."""
        data = {
            "id": 123,
            "title": "Test",
            "labels": [],
            "assignees": [
                {"login": "alice"},
                {"login": "bob"},
            ],
            "user": {"login": "charlie"},
            "html_url": "https://github.com/test/test/issues/1",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_github(data, github_source)

        assert "alice" in issue.assignees
        assert "bob" in issue.assignees

    def test_from_github_milestone(
        self,
        github_source: IssueSource,
    ) -> None:
        """Test GitHub issue with milestone."""
        data = {
            "id": 123,
            "title": "Test",
            "labels": [],
            "assignees": [],
            "milestone": {"title": "v1.0"},
            "user": {"login": "test"},
            "html_url": "https://github.com/test/test/issues/1",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_github(data, github_source)

        assert issue.milestone == "v1.0"

    def test_from_github_datetime_parsing(
        self,
        github_source: IssueSource,
    ) -> None:
        """Test datetime parsing in GitHub issues."""
        data = {
            "id": 123,
            "title": "Test",
            "labels": [],
            "assignees": [],
            "user": {"login": "test"},
            "html_url": "https://github.com/test/test/issues/1",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T11:30:00Z",
            "closed_at": "2024-01-03T12:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_github(data, github_source)

        assert isinstance(issue.created_at, datetime)
        assert isinstance(issue.updated_at, datetime)
        assert isinstance(issue.closed_at, datetime)


class TestIssueTransformerGitLab:
    """Tests for IssueTransformer.from_gitlab method."""

    def test_from_gitlab_basic(
        self,
        sample_gitlab_issue_data: dict,
        gitlab_source: IssueSource,
    ) -> None:
        """Test basic GitLab issue transformation."""
        transformer = IssueTransformer()
        issue = transformer.from_gitlab(sample_gitlab_issue_data, gitlab_source)

        assert issue.source_id == "456"
        assert issue.title == "Add new feature"
        assert issue.description == "Implement user preferences"
        assert issue.source == gitlab_source
        assert issue.status == IssueStatus.TODO
        assert "feature" in issue.labels

    def test_from_gitlab_closed_issue(
        self,
        gitlab_source: IssueSource,
    ) -> None:
        """Test GitLab issue transformation for closed issue."""
        data = {
            "id": 123,
            "title": "Closed issue",
            "description": "This is closed",
            "state": "closed",
            "labels": [],
            "assignees": [],
            "author": {"username": "test"},
            "web_url": "https://gitlab.com/test/test/issues/1",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T10:00:00Z",
            "closed_at": "2024-01-03T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_gitlab(data, gitlab_source)

        assert issue.status == IssueStatus.DONE
        assert issue.closed_at is not None

    def test_from_gitlab_assignees(
        self,
        gitlab_source: IssueSource,
    ) -> None:
        """Test GitLab issue with assignees."""
        data = {
            "id": 123,
            "title": "Test",
            "labels": [],
            "assignees": [
                {"username": "alice"},
            ],
            "author": {"username": "bob"},
            "web_url": "https://gitlab.com/test/test/issues/1",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_gitlab(data, gitlab_source)

        assert "alice" in issue.assignees

    def test_from_gitlab_metadata(
        self,
        gitlab_source: IssueSource,
    ) -> None:
        """Test GitLab issue metadata preservation."""
        data = {
            "id": 123,
            "iid": 456,
            "title": "Test",
            "labels": [],
            "assignees": [],
            "author": {"username": "test"},
            "web_url": "https://gitlab.com/test/test/issues/1",
            "references": {"full": "test/test#456"},
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_gitlab(data, gitlab_source)

        assert issue.metadata["iid"] == 456
        assert issue.metadata["references"] == {"full": "test/test#456"}


class TestIssueTransformerLinear:
    """Tests for IssueTransformer.from_linear method."""

    def test_from_linear_basic(
        self,
        sample_linear_issue_data: dict,
        linear_source: IssueSource,
    ) -> None:
        """Test basic Linear issue transformation."""
        transformer = IssueTransformer()
        issue = transformer.from_linear(sample_linear_issue_data, linear_source)

        assert issue.source_id == "LIN-123"
        assert issue.title == "Optimize database queries"
        assert issue.status == IssueStatus.IN_PROGRESS
        assert issue.priority == IssuePriority.HIGH
        assert "performance" in issue.labels

    def test_from_linear_state_mapping(
        self,
        linear_source: IssueSource,
    ) -> None:
        """Test Linear state to IssueStatus mapping."""
        transformer = IssueTransformer()

        state_tests = [
            ("backlog", IssueStatus.BACKLOG),
            ("todo", IssueStatus.TODO),
            ("in_progress", IssueStatus.IN_PROGRESS),
            ("done", IssueStatus.DONE),
            ("canceled", IssueStatus.CANCELLED),
        ]

        for linear_state, expected_status in state_tests:
            data = {
                "id": "TEST-1",
                "title": "Test",
                "state": {"type": linear_state},
                "priority": {"priority": "none"},
                "labels": [],
                "url": "https://linear.app/test/test-1",
                "createdAt": "2024-01-01T10:00:00Z",
                "updatedAt": "2024-01-02T10:00:00Z",
            }

            issue = transformer.from_linear(data, linear_source)
            assert issue.status == expected_status

    def test_from_linear_priority_mapping(
        self,
        linear_source: IssueSource,
    ) -> None:
        """Test Linear priority to IssuePriority mapping."""
        transformer = IssueTransformer()

        priority_tests = [
            ("urgent", IssuePriority.URGENT),
            ("high", IssuePriority.HIGH),
            ("medium", IssuePriority.MEDIUM),
            ("low", IssuePriority.LOW),
            ("none", IssuePriority.NO_PRIORITY),
        ]

        for linear_priority, expected_priority in priority_tests:
            data = {
                "id": "TEST-1",
                "title": "Test",
                "state": {"type": "todo"},
                "priority": {"priority": linear_priority},
                "labels": [],
                "url": "https://linear.app/test/test-1",
                "createdAt": "2024-01-01T10:00:00Z",
                "updatedAt": "2024-01-02T10:00:00Z",
            }

            issue = transformer.from_linear(data, linear_source)
            assert issue.priority == expected_priority

    def test_from_linear_label_priority_override(
        self,
        linear_source: IssueSource,
    ) -> None:
        """Test that label priority overrides Linear priority."""
        data = {
            "id": "TEST-1",
            "title": "Test",
            "state": {"type": "todo"},
            "priority": {"priority": "low"},
            "labels": [{"name": "urgent"}],
            "url": "https://linear.app/test/test-1",
            "createdAt": "2024-01-01T10:00:00Z",
            "updatedAt": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_linear(data, linear_source)

        # Label should override
        assert issue.priority == IssuePriority.URGENT

    def test_from_linear_assignee(
        self,
        linear_source: IssueSource,
    ) -> None:
        """Test Linear issue with assignee."""
        data = {
            "id": "TEST-1",
            "title": "Test",
            "state": {"type": "todo"},
            "priority": {"priority": "none"},
            "assignee": {"name": "Alice", "displayName": "alice"},
            "labels": [],
            "url": "https://linear.app/test/test-1",
            "createdAt": "2024-01-01T10:00:00Z",
            "updatedAt": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_linear(data, linear_source)

        assert "Alice" in issue.assignees

    def test_from_linear_cycle(
        self,
        linear_source: IssueSource,
    ) -> None:
        """Test Linear issue with cycle."""
        data = {
            "id": "TEST-1",
            "title": "Test",
            "state": {"type": "todo"},
            "priority": {"priority": "none"},
            "cycle": {"name": "Sprint 1"},
            "labels": [],
            "url": "https://linear.app/test/test-1",
            "createdAt": "2024-01-01T10:00:00Z",
            "updatedAt": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_linear(data, linear_source)

        assert issue.milestone == "Sprint 1"

    def test_from_linear_metadata(
        self,
        linear_source: IssueSource,
    ) -> None:
        """Test Linear issue metadata preservation."""
        data = {
            "id": "TEST-1",
            "title": "Test",
            "identifier": "ENG-123",
            "state": {"type": "todo"},
            "priority": {"priority": "none"},
            "team": {"name": "Engineering"},
            "labels": [],
            "url": "https://linear.app/test/test-1",
            "createdAt": "2024-01-01T10:00:00Z",
            "updatedAt": "2024-01-02T10:00:00Z",
        }

        transformer = IssueTransformer()
        issue = transformer.from_linear(data, linear_source)

        assert issue.metadata["identifier"] == "ENG-123"
        assert issue.metadata["team"] == "Engineering"


class TestIssueTransformerDatetimeParsing:
    """Tests for IssueTransformer._parse_datetime method."""

    def test_parse_datetime_valid(self) -> None:
        """Test parsing valid ISO 8601 datetime."""
        transformer = IssueTransformer()

        result = transformer._parse_datetime("2024-01-01T10:00:00Z")

        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_parse_datetime_with_timezone(self) -> None:
        """Test parsing datetime with timezone offset."""
        transformer = IssueTransformer()

        result = transformer._parse_datetime("2024-01-01T10:00:00+05:00")

        assert isinstance(result, datetime)

    def test_parse_datetime_none(self) -> None:
        """Test parsing None returns None."""
        transformer = IssueTransformer()

        result = transformer._parse_datetime(None)

        assert result is None

    def test_parse_datetime_empty_string(self) -> None:
        """Test parsing empty string returns None."""
        transformer = IssueTransformer()

        result = transformer._parse_datetime("")

        assert result is None

    def test_parse_datetime_invalid(self) -> None:
        """Test parsing invalid datetime returns None."""
        transformer = IssueTransformer()

        result = transformer._parse_datetime("not a datetime")

        assert result is None


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestIntakeMappingEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_label_mapping_empty_labels(self) -> None:
        """Test label mapping with empty label list."""
        mapping = LabelMapping()

        priority = mapping.extract_priority([])
        category = mapping.extract_category([])

        assert priority == IssuePriority.NO_PRIORITY
        assert category is None

    def test_transformer_missing_fields(
        self,
        github_source: IssueSource,
    ) -> None:
        """Test transformer handles missing fields gracefully."""
        transformer = IssueTransformer()

        # Minimal data
        data = {
            "id": 123,
            "title": "Minimal issue",
            "labels": [],
            "user": {"login": "test"},
            "html_url": "https://github.com/test/test/issues/1",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-02T10:00:00Z",
        }

        issue = transformer.from_github(data, github_source)

        assert issue.title == "Minimal issue"
        assert issue.description == ""
        assert issue.assignees == []

    def test_multiple_regex_rules(self) -> None:
        """Test that multiple regex rules can match."""
        custom_rules = [
            LabelRule(pattern="^bug:.*", priority=IssuePriority.URGENT, is_regex=True),
            LabelRule(pattern="^bug$", priority=IssuePriority.HIGH, is_regex=True),
        ]

        mapping = LabelMapping(
            priority_rules=custom_rules,
            category_rules=[],  # Clear default category rules
        )

        # Regex should match first
        assert mapping.get_priority("bug:auth") == IssuePriority.URGENT
        # Exact match (with regex anchors)
        assert mapping.get_priority("bug") == IssuePriority.HIGH

    def test_category_extraction_order(self) -> None:
        """Test that category extraction respects order."""
        custom_rules = [
            LabelRule(pattern="feature", category="first"),
            LabelRule(pattern="enhancement", category="second"),
        ]

        mapping = LabelMapping(category_rules=custom_rules)

        # First match should win
        assert mapping.extract_category(["feature", "enhancement"]) == "first"
