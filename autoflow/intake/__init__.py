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
from autoflow.intake.converter import IssueConverter
from autoflow.intake.github_client import GitHubClient
from autoflow.intake.gitlab_client import GitLabClient
from autoflow.intake.linear_client import LinearClient
from autoflow.intake.mapping import IssueTransformer, LabelMapping
from autoflow.intake.models import (
    Issue,
    IssuePriority,
    IssueSource,
    IssueStatus,
    SourceType,
)
from autoflow.intake.pipeline import (
    IngestionMode,
    IngestionResult,
    IntakePipeline,
    IntakePipelineConfig,
    PipelineError,
    PipelineResult,
    PipelineStats,
    PipelineStatus,
)
from autoflow.intake.sync import (
    SyncDirection,
    SyncError,
    SyncManager,
    SyncManagerConfig,
    SyncResult,
    SyncStats,
    SyncStatus,
    TaskIssueMapping,
)
from autoflow.intake.webhook import (
    WebhookConfig,
    WebhookEvent,
    WebhookEventType,
    WebhookResult,
    WebhookServer,
    WebhookSourceType,
)

__all__ = [
    "Issue",
    "IssuePriority",
    "IssueSource",
    "IssueStatus",
    "SourceType",
    "LabelMapping",
    "IssueTransformer",
    "IssueConverter",
    "IssueClient",
    "IssueClientConfig",
    "IssueResult",
    "IssueSourceType",
    "GitHubClient",
    "GitLabClient",
    "LinearClient",
    "make_http_request",
    "IntakePipeline",
    "IntakePipelineConfig",
    "PipelineStatus",
    "IngestionMode",
    "IngestionResult",
    "PipelineResult",
    "PipelineStats",
    "PipelineError",
    "SyncManager",
    "SyncManagerConfig",
    "SyncStatus",
    "SyncDirection",
    "SyncResult",
    "SyncStats",
    "SyncError",
    "TaskIssueMapping",
    "WebhookServer",
    "WebhookConfig",
    "WebhookEvent",
    "WebhookEventType",
    "WebhookResult",
    "WebhookSourceType",
]
