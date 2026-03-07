"""
Autoflow Issue Intake Module

Provides functionality for ingesting issues from external sources like
GitHub, GitLab, and Linear. Includes models, API clients, and synchronization
logic.

Usage:
    from autoflow.intake import Issue, IssueSource, IssueStatus

    source = IssueSource(
        id="github-example",
        type=SourceType.GITHUB,
        name="example/repo",
        url="https://github.com/example/repo"
    )

    issue = Issue(
        source_id="GH-123",
        source=source,
        title="Fix bug",
        status=IssueStatus.TODO
    )
"""

from autoflow.intake.client import (
    IssueClient,
    IssueClientConfig,
    IssueResult,
    IssueSourceType,
    make_http_request,
)
from autoflow.intake.github_client import GitHubClient
from autoflow.intake.mapping import IssueTransformer, LabelMapping
from autoflow.intake.models import (
    Issue,
    IssuePriority,
    IssueSource,
    IssueStatus,
    SourceType,
)

__all__ = [
    "Issue",
    "IssuePriority",
    "IssueSource",
    "IssueStatus",
    "SourceType",
    "LabelMapping",
    "IssueTransformer",
    "IssueClient",
    "IssueClientConfig",
    "IssueResult",
    "IssueSourceType",
    "GitHubClient",
    "make_http_request",
]
