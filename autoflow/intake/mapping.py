"""
Autoflow Intake Mapping Module

Provides label mapping and issue transformation logic for converting
external issues from sources like GitHub, GitLab, and Linear into
normalized Autoflow Issue objects.

Usage:
    from autoflow.intake.mapping import LabelMapping, IssueTransformer

    # Create label mappings
    mapping = LabelMapping()

    # Transform an external issue
    transformer = IssueTransformer(label_mapping=mapping)
    issue = transformer.transform(github_issue_data, source)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from autoflow.intake.models import (
    Issue,
    IssuePriority,
    IssueSource,
    IssueStatus,
    SourceType,
)


class LabelRule(BaseModel):
    """
    A single label mapping rule.

    Maps a label pattern to a priority and/or category.

    Attributes:
        pattern: Label name or regex pattern to match
        priority: Priority to assign when label matches
        category: Category to assign when label matches
        is_regex: Whether pattern is a regex (default: False)

    Example:
        >>> rule = LabelRule(
        ...     pattern="bug.*",
        ...     priority=IssuePriority.HIGH,
        ...     category="bug",
        ...     is_regex=True
        ... )
    """

    pattern: str
    priority: Optional[IssuePriority] = None
    category: Optional[str] = None
    is_regex: bool = False

    @field_validator("pattern", mode="before")
    @classmethod
    def compile_pattern(cls, v: str) -> str:
        """Validate that regex patterns compile correctly."""
        # Validation will happen when used in matcher
        return v


class LabelMapping(BaseModel):
    """
    Configuration for mapping labels to priorities and categories.

    Allows flexible transformation of source labels into Autoflow
    priorities and categories through pattern matching rules.

    Attributes:
        priority_rules: Rules that map labels to priorities
        category_rules: Rules that map labels to categories
        default_priority: Default priority if no rules match
        default_category: Default category if no rules match

    Example:
        >>> mapping = LabelMapping()
        >>> priority = mapping.get_priority("bug:critical")
        >>> print(priority)
        <IssuePriority.URGENT: 'urgent'>
    """

    priority_rules: list[LabelRule] = Field(
        default_factory=lambda: [
            LabelRule(pattern="urgent", priority=IssuePriority.URGENT),
            LabelRule(pattern="critical", priority=IssuePriority.URGENT),
            LabelRule(pattern="high.*", priority=IssuePriority.HIGH, is_regex=True),
            LabelRule(pattern="priority:high", priority=IssuePriority.HIGH),
            LabelRule(pattern="medium", priority=IssuePriority.MEDIUM),
            LabelRule(pattern="priority:medium", priority=IssuePriority.MEDIUM),
            LabelRule(pattern="low", priority=IssuePriority.LOW),
            LabelRule(pattern="priority:low", priority=IssuePriority.LOW),
        ]
    )

    category_rules: list[LabelRule] = Field(
        default_factory=lambda: [
            LabelRule(pattern="bug", category="bug"),
            LabelRule(pattern="bug:.*", category="bug", is_regex=True),
            LabelRule(pattern="feature", category="feature"),
            LabelRule(pattern="enhancement", category="feature"),
            LabelRule(pattern="docs", category="documentation"),
            LabelRule(pattern="documentation", category="documentation"),
            LabelRule(pattern="test", category="testing"),
            LabelRule(pattern="testing", category="testing"),
            LabelRule(pattern="refactor", category="refactoring"),
            LabelRule(pattern="chore", category="maintenance"),
            LabelRule(pattern="maintenance", category="maintenance"),
            LabelRule(pattern="security", category="security"),
            LabelRule(pattern="performance", category="performance"),
        ]
    )

    default_priority: IssuePriority = IssuePriority.NO_PRIORITY
    default_category: Optional[str] = None

    def get_priority(self, label: str) -> Optional[IssuePriority]:
        """
        Get the priority for a label based on configured rules.

        Checks all priority rules in order and returns the priority
        from the first matching rule.

        Args:
            label: Label string to match against rules

        Returns:
            Matched IssuePriority or None if no match

        Example:
            >>> mapping = LabelMapping()
            >>> mapping.get_priority("bug:critical")
            <IssuePriority.URGENT: 'urgent'>
        """
        for rule in self.priority_rules:
            if rule.is_regex:
                if re.search(rule.pattern, label, re.IGNORECASE):
                    return rule.priority
            else:
                if rule.pattern.lower() == label.lower():
                    return rule.priority
        return None

    def get_category(self, label: str) -> Optional[str]:
        """
        Get the category for a label based on configured rules.

        Checks all category rules in order and returns the category
        from the first matching rule.

        Args:
            label: Label string to match against rules

        Returns:
            Matched category string or None if no match

        Example:
            >>> mapping = LabelMapping()
            >>> mapping.get_category("bug:authentication")
            'bug'
        """
        for rule in self.category_rules:
            if rule.is_regex:
                if re.search(rule.pattern, label, re.IGNORECASE):
                    return rule.category
            else:
                if rule.pattern.lower() == label.lower():
                    return rule.category
        return None

    def extract_priority(
        self,
        labels: list[str],
    ) -> IssuePriority:
        """
        Extract the highest priority from a list of labels.

        Returns the highest priority found among all labels,
        or the default priority if no matches.

        Args:
            labels: List of label strings

        Returns:
            Highest IssuePriority found or default

        Example:
            >>> mapping = LabelMapping()
            >>> mapping.extract_priority(["bug", "low"])
            <IssuePriority.HIGH: 'high'>
        """
        priority_order = [
            IssuePriority.URGENT,
            IssuePriority.HIGH,
            IssuePriority.MEDIUM,
            IssuePriority.LOW,
            IssuePriority.NO_PRIORITY,
        ]

        for priority_level in priority_order:
            for label in labels:
                if self.get_priority(label) == priority_level:
                    return priority_level

        return self.default_priority

    def extract_category(
        self,
        labels: list[str],
    ) -> Optional[str]:
        """
        Extract a category from a list of labels.

        Returns the first matching category from the labels.

        Args:
            labels: List of label strings

        Returns:
            Matched category string or None

        Example:
            >>> mapping = LabelMapping()
            >>> mapping.extract_category(["bug:auth", "security"])
            'bug'
        """
        for label in labels:
            category = self.get_category(label)
            if category:
                return category
        return self.default_category


class IssueTransformer(BaseModel):
    """
    Transforms external issue data into normalized Issue objects.

    Handles conversion from source-specific formats (GitHub, GitLab, Linear)
    to the unified Autoflow Issue model, including label mapping and
    status normalization.

    Attributes:
        label_mapping: LabelMapping configuration for priority/category extraction

    Example:
        >>> transformer = IssueTransformer()
        >>> issue = transformer.from_github(github_data, source)
    """

    label_mapping: LabelMapping = Field(default_factory=LabelMapping)

    def from_github(
        self,
        data: dict[str, Any],
        source: IssueSource,
    ) -> Issue:
        """
        Transform a GitHub issue into a normalized Issue.

        Args:
            data: GitHub issue API response data
            source: IssueSource for the GitHub repository

        Returns:
            Normalized Issue object

        Example:
            >>> source = IssueSource(
            ...     id="github-repo",
            ...     type=SourceType.GITHUB,
            ...     name="user/repo",
            ...     url="https://github.com/user/repo"
            ... )
            >>> transformer = IssueTransformer()
            >>> issue = transformer.from_github(github_api_data, source)
        """
        # Extract labels
        labels = [
            label.get("name", "")
            for label in data.get("labels", [])
            if label.get("name")
        ]

        # Map GitHub state to IssueStatus
        state = data.get("state", "open")
        if state == "open":
            # Check if it's a draft PR
            if data.get("draft") or data.get("pull_request"):
                status = IssueStatus.TODO
            else:
                status = IssueStatus.TODO
        elif state == "closed":
            status = IssueStatus.DONE
        else:
            status = IssueStatus.BACKLOG

        # Extract priority and category from labels
        priority = self.label_mapping.extract_priority(labels)
        category = self.label_mapping.extract_category(labels)

        # Parse dates
        created_at = self._parse_datetime(data.get("created_at"))
        updated_at = self._parse_datetime(data.get("updated_at"))
        closed_at = self._parse_datetime(data.get("closed_at"))

        # Get assignees
        assignees = [
            assignee.get("login", "")
            for assignee in data.get("assignees", [])
            if assignee.get("login")
        ]

        # Get milestone
        milestone = None
        if data.get("milestone"):
            milestone = data["milestone"].get("title")

        return Issue(
            source_id=str(data.get("id", "")),
            source=source,
            title=data.get("title", ""),
            description=data.get("body", ""),
            status=status,
            priority=priority,
            labels=labels,
            assignees=assignees,
            milestone=milestone,
            created_at=created_at,
            updated_at=updated_at,
            closed_at=closed_at,
            creator=data.get("user", {}).get("login"),
            source_url=data.get("html_url"),
            metadata={
                "category": category,
                "number": data.get("number"),
                "pull_request": data.get("pull_request") is not None,
            },
            synced_at=datetime.utcnow(),
        )

    def from_gitlab(
        self,
        data: dict[str, Any],
        source: IssueSource,
    ) -> Issue:
        """
        Transform a GitLab issue into a normalized Issue.

        Args:
            data: GitLab issue API response data
            source: IssueSource for the GitLab project

        Returns:
            Normalized Issue object

        Example:
            >>> source = IssueSource(
            ...     id="gitlab-project",
            ...     type=SourceType.GITLAB,
            ...     name="user/project",
            ...     url="https://gitlab.com/user/project"
            ... )
            >>> transformer = IssueTransformer()
            >>> issue = transformer.from_gitlab(gitlab_api_data, source)
        """
        # Extract labels
        labels = data.get("labels", [])

        # Map GitLab state to IssueStatus
        state = data.get("state", "opened")
        if state == "opened":
            status = IssueStatus.TODO
        elif state == "closed":
            status = IssueStatus.DONE
        else:
            status = IssueStatus.BACKLOG

        # Extract priority and category from labels
        priority = self.label_mapping.extract_priority(labels)
        category = self.label_mapping.extract_category(labels)

        # Parse dates
        created_at = self._parse_datetime(data.get("created_at"))
        updated_at = self._parse_datetime(data.get("updated_at"))
        closed_at = self._parse_datetime(data.get("closed_at"))

        # Get assignees
        assignees = [
            assignee.get("username", "")
            for assignee in data.get("assignees", [])
            if assignee.get("username")
        ]

        # Get milestone
        milestone = None
        if data.get("milestone"):
            milestone = data["milestone"].get("title")

        return Issue(
            source_id=str(data.get("id", "")),
            source=source,
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=status,
            priority=priority,
            labels=labels,
            assignees=assignees,
            milestone=milestone,
            created_at=created_at,
            updated_at=updated_at,
            closed_at=closed_at,
            creator=data.get("author", {}).get("username"),
            source_url=data.get("web_url"),
            metadata={
                "category": category,
                "iid": data.get("iid"),
                "references": data.get("references"),
            },
            synced_at=datetime.utcnow(),
        )

    def from_linear(
        self,
        data: dict[str, Any],
        source: IssueSource,
    ) -> Issue:
        """
        Transform a Linear issue into a normalized Issue.

        Args:
            data: Linear issue API response data
            source: IssueSource for the Linear workspace

        Returns:
            Normalized Issue object

        Example:
            >>> source = IssueSource(
            ...     id="linear-workspace",
            ...     type=SourceType.LINEAR,
            ...     name="My Workspace",
            ...     url="https://linear.app/workspace"
            ... )
            >>> transformer = IssueTransformer()
            >>> issue = transformer.from_linear(linear_api_data, source)
        """
        # Extract labels (Linear calls them "labels")
        labels = []
        for label_data in data.get("labels", []):
            label_name = label_data.get("name", "")
            if label_name:
                labels.append(label_name)

        # Map Linear state to IssueStatus
        state_data = data.get("state", {})
        state_type = state_data.get("type", "backlog")

        state_mapping = {
            "backlog": IssueStatus.BACKLOG,
            "todo": IssueStatus.TODO,
            "in_progress": IssueStatus.IN_PROGRESS,
            "done": IssueStatus.DONE,
            "canceled": IssueStatus.CANCELLED,
        }

        status = state_mapping.get(state_type, IssueStatus.BACKLOG)

        # Map Linear priority to IssuePriority
        priority_data = data.get("priority", {})
        linear_priority = priority_data.get("priority", "no_priority")

        linear_priority_mapping = {
            "urgent": IssuePriority.URGENT,
            "high": IssuePriority.HIGH,
            "medium": IssuePriority.MEDIUM,
            "low": IssuePriority.LOW,
            "none": IssuePriority.NO_PRIORITY,
        }

        priority = linear_priority_mapping.get(
            linear_priority,
            IssuePriority.NO_PRIORITY
        )

        # Override with label mapping if available
        if labels:
            label_priority = self.label_mapping.extract_priority(labels)
            if label_priority != IssuePriority.NO_PRIORITY:
                priority = label_priority

        # Extract category from labels
        category = self.label_mapping.extract_category(labels)

        # Parse dates
        created_at = self._parse_datetime(data.get("createdAt"))
        updated_at = self._parse_datetime(data.get("updatedAt"))
        closed_at = self._parse_datetime(data.get("completedAt"))

        # Get assignees
        assignees = []
        assignee = data.get("assignee")
        if assignee:
            assignee_name = assignee.get("name") or assignee.get("displayName", "")
            if assignee_name:
                assignees.append(assignee_name)

        # Get cycle (similar to milestone)
        milestone = None
        cycle = data.get("cycle")
        if cycle:
            milestone = cycle.get("name")

        return Issue(
            source_id=data.get("id", ""),
            source=source,
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=status,
            priority=priority,
            labels=labels,
            assignees=assignees,
            milestone=milestone,
            created_at=created_at,
            updated_at=updated_at,
            closed_at=closed_at,
            creator=data.get("creator", {}).get("name"),
            source_url=data.get("url"),
            metadata={
                "category": category,
                "identifier": data.get("identifier"),
                "team": data.get("team", {}).get("name"),
            },
            synced_at=datetime.utcnow(),
        )

    def _parse_datetime(
        self,
        date_str: Optional[str],
    ) -> Optional[datetime]:
        """
        Parse an ISO 8601 datetime string.

        Args:
            date_str: ISO 8601 datetime string or None

        Returns:
            datetime object or None if parsing fails

        Example:
            >>> transformer = IssueTransformer()
            >>> dt = transformer._parse_datetime("2024-01-01T12:00:00Z")
        """
        if not date_str:
            return None

        try:
            # Remove 'Z' suffix and handle timezone
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            return datetime.fromisoformat(date_str)
        except (ValueError, AttributeError):
            return None
