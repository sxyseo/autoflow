"""
Autoflow Intake Converter Module

Provides conversion logic for transforming external issues into Autoflow
specs and tasks with proper label mapping and metadata preservation.

Usage:
    from autoflow.intake.converter import IssueConverter

    # Create a converter with custom label mapping
    converter = IssueConverter()

    # Convert an issue to a spec
    spec = converter.issue_to_spec(issue)

    # Convert an issue to a task
    task = converter.issue_to_task(issue)

    # Convert an issue to both spec and task
    spec, task = converter.convert_issue(issue)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from autoflow.core.state import Spec, Task, TaskStatus
from autoflow.intake.mapping import LabelMapping
from autoflow.intake.models import Issue, IssuePriority, IssueStatus


class IssueConverter(BaseModel):
    """
    Converts external issues into Autoflow specs and tasks.

    Handles transformation of Issue objects from external sources (GitHub,
    GitLab, Linear) into native Autoflow Spec and Task objects with proper
    status/priority mapping and metadata preservation.

    Attributes:
        label_mapping: LabelMapping configuration for extracting categories
        spec_prefix: Prefix for generated spec IDs (default: "spec")
        task_prefix: Prefix for generated task IDs (default: "task")
        preserve_labels: Whether to preserve original labels in task metadata
        add_source_links: Whether to add source URLs to task description

    Example:
        >>> converter = IssueConverter()
        >>> issue = Issue(
        ...     source_id="GH-123",
        ...     title="Fix authentication bug",
        ...     status=IssueStatus.TODO,
        ...     priority=IssuePriority.HIGH
        ... )
        >>> spec, task = converter.convert_issue(issue)
    """

    label_mapping: LabelMapping = Field(default_factory=LabelMapping)
    spec_prefix: str = "spec"
    task_prefix: str = "task"
    preserve_labels: bool = True
    add_source_links: bool = True

    def convert_issue(
        self,
        issue: Issue,
        create_spec: bool = True,
        create_task: bool = True,
    ) -> tuple[Optional[Spec], Optional[Task]]:
        """
        Convert an issue into spec and/or task.

        This is the main entry point for issue conversion. It can create
        a spec, a task, or both depending on the parameters.

        Args:
            issue: The Issue object to convert
            create_spec: Whether to create a spec from the issue
            create_task: Whether to create a task from the issue

        Returns:
            Tuple of (spec, task) - either may be None if not created

        Example:
            >>> converter = IssueConverter()
            >>> spec, task = converter.convert_issue(issue)
            >>> # Or create only a task
            >>> _, task = converter.convert_issue(issue, create_spec=False)
        """
        spec = None
        task = None

        if create_spec:
            spec = self.issue_to_spec(issue)

        if create_task:
            task = self.issue_to_task(issue, spec_id=spec.id if spec else None)

        return spec, task

    def issue_to_spec(self, issue: Issue) -> Spec:
        """
        Convert an issue into a Spec.

        Creates a comprehensive specification document from an issue,
        including all context from comments, labels, and metadata.

        Args:
            issue: The Issue object to convert

        Returns:
            Spec object with issue content and metadata

        Example:
            >>> converter = IssueConverter()
            >>> spec = converter.issue_to_spec(issue)
            >>> print(f"Created spec: {spec.id}")
        """
        # Generate a unique spec ID
        spec_id = f"{self.spec_prefix}-{issue.source.type.value}-{issue.source_id}"

        # Build spec content with rich context
        content = self._build_spec_content(issue)

        # Extract tags from labels and category
        tags = self._extract_tags(issue)

        # Build metadata to preserve source information
        metadata = {
            "source": {
                "type": issue.source.type.value,
                "id": issue.source_id,
                "name": issue.source.name,
                "url": issue.source_url,
            },
            "issue": {
                "status": issue.status.value,
                "priority": issue.priority.value,
                "labels": issue.labels,
                "assignees": issue.assignees,
                "milestone": issue.milestone,
                "creator": issue.creator,
                "created_at": issue.created_at.isoformat()
                if issue.created_at
                else None,
                "updated_at": issue.updated_at.isoformat()
                if issue.updated_at
                else None,
                "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
            },
            "category": issue.metadata.get("category"),
            "synced_at": issue.synced_at.isoformat() if issue.synced_at else None,
        }

        # Add any additional metadata from the issue
        for key, value in issue.metadata.items():
            if key not in metadata["issue"]:
                metadata["issue"][key] = value

        return Spec(
            id=spec_id,
            title=issue.title,
            content=content,
            version="1.0",
            created_at=issue.created_at or datetime.utcnow(),
            updated_at=issue.updated_at or datetime.utcnow(),
            author=issue.creator or issue.source.name,
            tags=tags,
            metadata=metadata,
        )

    def issue_to_task(
        self,
        issue: Issue,
        spec_id: Optional[str] = None,
    ) -> Task:
        """
        Convert an issue into a Task.

        Creates a task from an issue with proper status and priority mapping.
        Optionally associates the task with a spec.

        Args:
            issue: The Issue object to convert
            spec_id: Optional spec ID to associate with this task

        Returns:
            Task object with mapped status and priority

        Example:
            >>> converter = IssueConverter()
            >>> task = converter.issue_to_task(issue)
            >>> print(f"Task status: {task.status}")
        """
        # Generate a unique task ID
        task_id = f"{self.task_prefix}-{issue.source.type.value}-{issue.source_id}"

        # Map issue status to task status
        task_status = self._map_task_status(issue.status)

        # Map issue priority to task priority (1-10 scale)
        task_priority = self._map_task_priority(issue.priority)

        # Build description with source link if enabled
        description = issue.description or ""
        if self.add_source_links and issue.source_url:
            source_link = (
                f"\n\n---\n\n**Source:** [{issue.source.name}]({issue.source_url})"
            )
            if source_link not in description:
                description = description + source_link

        # Build metadata to preserve source information
        metadata: dict[str, Any] = {
            "source": {
                "type": issue.source.type.value,
                "id": issue.source_id,
                "name": issue.source.name,
                "url": issue.source_url,
            },
            "issue": {
                "status": issue.status.value,
                "priority": issue.priority.value,
                "milestone": issue.milestone,
                "creator": issue.creator,
            },
        }

        # Add labels if preservation is enabled
        if self.preserve_labels and issue.labels:
            labels = issue.labels.copy()
        else:
            labels = []

        # Add category as a label if present
        category = issue.metadata.get("category")
        if category and category not in labels:
            labels.append(category)

        # Store original labels in metadata even if not preserved as labels
        if issue.labels:
            metadata["issue"]["labels"] = issue.labels

        # Add category to metadata
        if category:
            metadata["category"] = category

        # Associate with spec if provided
        if spec_id:
            metadata["spec_id"] = spec_id

        # Add any additional metadata from the issue
        for key, value in issue.metadata.items():
            if key not in metadata["issue"]:
                metadata[key] = value

        return Task(
            id=task_id,
            title=issue.title,
            description=description,
            status=task_status,
            priority=task_priority,
            created_at=issue.created_at or datetime.utcnow(),
            updated_at=issue.updated_at or datetime.utcnow(),
            assigned_agent=issue.assignees[0] if issue.assignees else None,
            labels=labels,
            dependencies=[],
            metadata=metadata,
        )

    def _build_spec_content(self, issue: Issue) -> str:
        """
        Build comprehensive spec content from an issue.

        Creates a well-formatted specification document including
        description, labels, comments, and context.

        Args:
            issue: The Issue object

        Returns:
            Formatted spec content as a string
        """
        sections = []

        # Title and main description
        sections.append(f"# {issue.title}\n")

        # Description
        if issue.description:
            sections.append(f"## Description\n\n{issue.description}\n")

        # Category
        category = issue.metadata.get("category")
        if category:
            sections.append(f"## Category\n\n{category}\n")

        # Labels
        if issue.labels:
            labels_str = ", ".join(f"`{label}`" for label in issue.labels)
            sections.append(f"## Labels\n\n{labels_str}\n")

        # Priority and Status
        sections.append(
            f"## Priority & Status\n\n"
            f"- **Priority:** {issue.priority.value}\n"
            f"- **Status:** {issue.status.value}\n"
        )

        # Assignees
        if issue.assignees:
            assignees_str = ", ".join(issue.assignees)
            sections.append(f"- **Assignees:** {assignees_str}\n")

        # Milestone
        if issue.milestone:
            sections.append(f"- **Milestone:** {issue.milestone}\n")

        sections.append("\n")

        # Source information
        if issue.source_url:
            sections.append(
                f"## Source\n\n"
                f"- **Repository:** {issue.source.name}\n"
                f"- **URL:** {issue.source_url}\n"
                f"- **Issue ID:** {issue.source_id}\n\n"
            )

        # Comments
        if issue.comments:
            sections.append("## Comments\n\n")
            for i, comment in enumerate(issue.comments, 1):
                author = comment.get("author", "Unknown")
                body = comment.get("body", "")
                created_at = comment.get("created_at", "")

                sections.append(f"### Comment {i} by {author}\n\n")
                if body:
                    sections.append(f"{body}\n\n")
                if created_at:
                    sections.append(f"*Posted: {created_at}*\n\n")

        # Metadata
        if issue.creator:
            sections.append(f"---\n\n*Created by: {issue.creator}*")

        return "\n".join(sections)

    def _extract_tags(self, issue: Issue) -> list[str]:
        """
        Extract tags from an issue for spec tagging.

        Combines labels and category into a set of unique tags.

        Args:
            issue: The Issue object

        Returns:
            List of unique tags
        """
        tags = set()

        # Add all labels as tags (sanitized)
        for label in issue.labels:
            # Convert to lowercase and replace spaces/special chars
            tag = label.lower().replace(" ", "-").replace("/", "-")
            tag = "".join(c for c in tag if c.isalnum() or c in "-_")
            if tag:
                tags.add(tag)

        # Add category as a tag
        category = issue.metadata.get("category")
        if category:
            tags.add(category.lower())

        # Add source type
        tags.add(issue.source.type.value)

        return sorted(tags)

    def _map_task_status(self, issue_status: IssueStatus) -> TaskStatus:
        """
        Map IssueStatus to TaskStatus.

        Converts between the two status enumerations, handling any
        differences in the state models.

        Args:
            issue_status: The IssueStatus to map

        Returns:
            Corresponding TaskStatus

        Example:
            >>> converter = IssueConverter()
            >>> status = converter._map_task_status(IssueStatus.IN_PROGRESS)
            >>> print(status)
            <TaskStatus.IN_PROGRESS: 'in_progress'>
        """
        status_mapping = {
            IssueStatus.BACKLOG: TaskStatus.PENDING,
            IssueStatus.TODO: TaskStatus.PENDING,
            IssueStatus.IN_PROGRESS: TaskStatus.IN_PROGRESS,
            IssueStatus.IN_REVIEW: TaskStatus.IN_PROGRESS,
            IssueStatus.DONE: TaskStatus.COMPLETED,
            IssueStatus.CANCELLED: TaskStatus.CANCELLED,
            IssueStatus.ARCHIVED: TaskStatus.CANCELLED,
        }

        return status_mapping.get(
            issue_status,
            TaskStatus.PENDING,
        )

    def _map_task_priority(self, issue_priority: IssuePriority) -> int:
        """
        Map IssuePriority to Task priority (1-10 scale).

        Converts the enum-based priority to a numeric scale used
        by Task objects.

        Args:
            issue_priority: The IssuePriority to map

        Returns:
            Integer priority from 1-10 (higher is more urgent)

        Example:
            >>> converter = IssueConverter()
            >>> priority = converter._map_task_priority(IssuePriority.HIGH)
            >>> print(priority)
            8
        """
        priority_mapping = {
            IssuePriority.URGENT: 10,
            IssuePriority.HIGH: 8,
            IssuePriority.MEDIUM: 5,
            IssuePriority.LOW: 3,
            IssuePriority.NO_PRIORITY: 1,
        }

        return priority_mapping.get(
            issue_priority,
            1,
        )
