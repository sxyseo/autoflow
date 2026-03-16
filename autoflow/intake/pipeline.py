"""
Autoflow Intake Pipeline Module

Provides orchestration for ingesting issues from external sources into Autoflow.
Coordinates fetching, transforming, converting, and storing issues from GitHub,
GitLab, Linear, and other sources.

Usage:
    from autoflow.intake.pipeline import IntakePipeline, IntakePipelineConfig

    config = IntakePipelineConfig()
    pipeline = IntakePipeline(config=config)

    # Ingest all issues from configured sources
    result = await pipeline.ingest_all()

    # Ingest from a specific source
    result = await pipeline.ingest_from_source("github-repo-id")
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

from autoflow.core.config import Config, load_config
from autoflow.core.state import Spec, StateManager, Task
from autoflow.intake.client import (
    IssueClient,
    IssueClientConfig,
    IssueResult,
    IssueSourceType,
)
from autoflow.intake.converter import IssueConverter
from autoflow.intake.github_client import GitHubClient
from autoflow.intake.gitlab_client import GitLabClient
from autoflow.intake.linear_client import LinearClient
from autoflow.intake.mapping import IssueTransformer
from autoflow.intake.models import Issue, IssueSource, SourceType


class PipelineStatus(str, Enum):
    """Status of the intake pipeline."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class IngestionMode(str, Enum):
    """Mode of issue ingestion."""

    FULL = "full"  # Fetch all issues
    INCREMENTAL = "incremental"  # Only new/updated since last sync
    WEBHOOK = "webhook"  # Process webhook events


class PipelineError(Exception):
    """Exception raised for pipeline errors."""

    def __init__(self, message: str, source: Optional[str] = None):
        self.source = source
        super().__init__(message)


@dataclass
class IngestionResult:
    """
    Result from a single ingestion operation.

    Attributes:
        ingestion_id: Unique identifier for this ingestion run
        source_id: ID of the source that was ingested
        mode: Ingestion mode used
        success: Whether the ingestion completed successfully
        issues_fetched: Number of issues fetched from source
        issues_transformed: Number of issues transformed successfully
        specs_created: Number of specs created
        tasks_created: Number of tasks created
        errors: List of error messages encountered
        started_at: When the ingestion started
        completed_at: When the ingestion completed
        duration_seconds: Total ingestion duration
        metadata: Additional metadata
    """

    ingestion_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_id: str = ""
    mode: IngestionMode = IngestionMode.FULL
    success: bool = False
    issues_fetched: int = 0
    issues_transformed: int = 0
    specs_created: int = 0
    tasks_created: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_complete(
        self,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Mark the ingestion as complete."""
        self.success = success
        if error:
            self.errors.append(error)
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()


@dataclass
class PipelineResult:
    """
    Result from a pipeline operation.

    Attributes:
        pipeline_id: Unique identifier for this pipeline run
        success: Whether the pipeline operation completed successfully
        total_issues: Total number of issues processed
        total_specs: Total number of specs created
        total_tasks: Total number of tasks created
        source_results: Individual results per source
        started_at: When the pipeline run started
        completed_at: When the pipeline run completed
        duration_seconds: Total pipeline duration
        error: Error message if operation failed
        metadata: Additional metadata
    """

    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    success: bool = False
    total_issues: int = 0
    total_specs: int = 0
    total_tasks: int = 0
    source_results: list[IngestionResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_complete(
        self,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Mark the pipeline run as complete."""
        self.success = success
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()

        # Aggregate totals from source results
        for result in self.source_results:
            self.total_issues += result.issues_fetched
            self.total_specs += result.specs_created
            self.total_tasks += result.tasks_created


class PipelineStats(BaseModel):
    """Statistics about pipeline runs."""

    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_issues_processed: int = 0
    total_specs_created: int = 0
    total_tasks_created: int = 0
    average_duration: float = 0.0
    last_run_at: Optional[datetime] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)


class IntakePipelineConfig(BaseModel):
    """
    Configuration for the intake pipeline.

    Attributes:
        state_dir: Directory for storing state
        sources: List of configured issue sources
        mode: Default ingestion mode
        create_specs: Whether to create specs from issues
        create_tasks: Whether to create tasks from issues
        batch_size: Number of issues to process per batch
        max_concurrent_sources: Maximum number of sources to process concurrently
        filter_closed: Whether to skip closed issues
        filter_labels: Optional label filter (only ingest issues with these labels)
        dry_run: If True, don't actually store specs/tasks
        metadata: Additional configuration metadata
    """

    state_dir: Path = Field(default_factory=lambda: Path(".auto-claude/state"))
    sources: list[IssueSource] = Field(default_factory=list)
    mode: IngestionMode = IngestionMode.INCREMENTAL
    create_specs: bool = True
    create_tasks: bool = True
    batch_size: int = 50
    max_concurrent_sources: int = 3
    filter_closed: bool = False
    filter_labels: Optional[list[str]] = None
    dry_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntakePipeline:
    """
    Pipeline for ingesting issues from external sources.

    Orchestrates the complete intake workflow:
    1. Fetch issues from configured sources (GitHub, GitLab, Linear)
    2. Transform to normalized Issue objects
    3. Convert to Autoflow Specs and Tasks
    4. Store in state manager

    The pipeline supports:
    - Multiple concurrent source processing
    - Incremental and full ingestion modes
    - Configurable filtering and transformations
    - Error handling and retry logic
    - Statistics and progress tracking

    Example:
        >>> config = IntakePipelineConfig()
        >>> pipeline = IntakePipeline(config=config)
        >>> await pipeline.initialize()
        >>>
        >>> # Ingest from all configured sources
        >>> result = await pipeline.ingest_all()
        >>>
        >>> # Ingest from a specific source
        >>> result = await pipeline.ingest_from_source("github-repo")
        >>>
        >>> # Process a webhook event
        >>> result = await pipeline.process_webhook(
        ...     source_type="github",
        ...     payload=webhook_data,
        ...     signature=signature
        ... )

    Attributes:
        config: Pipeline configuration
        state: StateManager instance
        transformer: IssueTransformer for normalizing issues
        converter: IssueConverter for creating specs/tasks
        clients: Mapping of source types to client instances
    """

    DEFAULT_TIMEOUT = 300  # 5 minutes per source
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 2.0

    def __init__(
        self,
        config: Optional[IntakePipelineConfig] = None,
        state: Optional[StateManager] = None,
        auto_initialize: bool = False,
    ) -> None:
        """
        Initialize the intake pipeline.

        Args:
            config: Optional pipeline configuration
            state: Optional state manager
            auto_initialize: If True, initialize on creation
        """
        self._config = config or IntakePipelineConfig()
        self._state = state

        # Status tracking
        self._status = PipelineStatus.IDLE
        self._current_result: Optional[PipelineResult] = None

        # Components
        self._transformer: Optional[IssueTransformer] = None
        self._converter: Optional[IssueConverter] = None
        self._clients: dict[SourceType, IssueClient] = {}

        # Statistics
        self._stats = PipelineStats()

        # Background task tracking
        self._running = False

        if auto_initialize:
            asyncio.create_task(self.initialize())

    @property
    def config(self) -> IntakePipelineConfig:
        """Get pipeline configuration."""
        return self._config

    @property
    def state(self) -> StateManager:
        """Get state manager, creating if needed."""
        if self._state is None:
            self._state = StateManager(self._config.state_dir)
            self._state.initialize()
        return self._state

    @property
    def transformer(self) -> IssueTransformer:
        """Get issue transformer, creating if needed."""
        if self._transformer is None:
            self._transformer = IssueTransformer()
        return self._transformer

    @property
    def converter(self) -> IssueConverter:
        """Get issue converter, creating if needed."""
        if self._converter is None:
            self._converter = IssueConverter()
        return self._converter

    @property
    def status(self) -> PipelineStatus:
        """Get current pipeline status."""
        return self._status

    @property
    def stats(self) -> PipelineStats:
        """Get pipeline statistics."""
        return self._stats

    def initialize(self) -> None:
        """
        Initialize the pipeline.

        Sets up client instances and validates configuration.
        """
        self._status = PipelineStatus.INITIALIZING

        try:
            # Initialize clients for each source type
            self._clients = {
                SourceType.GITHUB: GitHubClient(),
                SourceType.GITLAB: GitLabClient(),
                SourceType.LINEAR: LinearClient(),
            }

            self._status = PipelineStatus.IDLE

        except Exception as e:
            self._status = PipelineStatus.ERROR
            raise PipelineError(
                f"Failed to initialize pipeline: {e}",
            ) from e

    async def ingest_all(
        self,
        mode: Optional[IngestionMode] = None,
        source_ids: Optional[list[str]] = None,
    ) -> PipelineResult:
        """
        Ingest issues from all configured sources.

        Args:
            mode: Ingestion mode (defaults to config mode)
            source_ids: Optional list of source IDs to ingest (all if None)

        Returns:
            PipelineResult with ingestion statistics

        Example:
            >>> result = await pipeline.ingest_all(
            ...     mode=IngestionMode.INCREMENTAL,
            ...     source_ids=["github-repo", "gitlab-project"]
            ... )
        """
        if self._status == PipelineStatus.RUNNING:
            raise PipelineError("Pipeline is already running")

        self._status = PipelineStatus.RUNNING
        self._current_result = PipelineResult()
        self._current_result.started_at = datetime.utcnow()

        try:
            # Filter sources if source_ids provided
            sources = self._config.sources
            if source_ids:
                sources = [s for s in sources if s.id in source_ids]

            if not sources:
                raise PipelineError("No sources configured for ingestion")

            # Process sources concurrently (with limit)
            semaphore = asyncio.Semaphore(self._config.max_concurrent_sources)

            async def ingest_with_semaphore(source: IssueSource) -> IngestionResult:
                async with semaphore:
                    return await self.ingest_from_source(
                        source=source,
                        mode=mode or self._config.mode,
                    )

            # Run ingestion tasks
            tasks = [
                ingest_with_semaphore(source)
                for source in sources
                if source.enabled
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    # Log error but continue processing other sources
                    error_result = IngestionResult(
                        source_id="unknown",
                        mode=mode or self._config.mode,
                        success=False,
                        errors=[str(result)],
                    )
                    error_result.mark_complete(success=False, error=str(result))
                    self._current_result.source_results.append(error_result)
                else:
                    self._current_result.source_results.append(result)

            # Update stats
            self._stats.total_runs += 1
            self._stats.last_run_at = datetime.utcnow()

            # Mark complete
            self._current_result.mark_complete(
                success=all(r.success for r in self._current_result.source_results),
            )

            # Update success stats
            if self._current_result.success:
                self._stats.successful_runs += 1
                self._stats.total_issues_processed += self._current_result.total_issues
                self._stats.total_specs_created += self._current_result.total_specs
                self._stats.total_tasks_created += self._current_result.total_tasks
            else:
                self._stats.failed_runs += 1

            return self._current_result

        except Exception as e:
            self._current_result.mark_complete(success=False, error=str(e))
            self._stats.failed_runs += 1
            self._status = PipelineStatus.ERROR
            raise PipelineError(f"Pipeline ingestion failed: {e}") from e

        finally:
            self._status = PipelineStatus.IDLE
            self._current_result = None

    async def ingest_from_source(
        self,
        source: IssueSource,
        mode: IngestionMode = IngestionMode.INCREMENTAL,
    ) -> IngestionResult:
        """
        Ingest issues from a single source.

        Fetches issues from the source, transforms them to normalized
        Issue objects, converts to Specs/Tasks, and stores them.

        Args:
            source: The IssueSource to ingest from
            mode: Ingestion mode

        Returns:
            IngestionResult with statistics for this source

        Example:
            >>> source = IssueSource(
            ...     id="github-repo",
            ...     type=SourceType.GITHUB,
            ...     name="user/repo",
            ...     url="https://github.com/user/repo"
            ... )
            >>> result = await pipeline.ingest_from_source(source)
        """
        result = IngestionResult(
            source_id=source.id,
            mode=mode,
        )
        result.started_at = datetime.utcnow()

        try:
            # Get client for this source type
            client = self._clients.get(source.type)
            if not client:
                raise PipelineError(
                    f"No client available for source type: {source.type.value}",
                    source=source.id,
                )

            # Build client config from source
            client_config = IssueClientConfig(
                source_type=IssueSourceType(source.type.value),
                token=source.config.get("token"),
                repository=source.config.get("repository"),
                webhook_secret=source.config.get("webhook_secret"),
                timeout_seconds=source.config.get("timeout_seconds", 30),
                retry_attempts=source.config.get("retry_attempts", 3),
                retry_delay_seconds=source.config.get("retry_delay_seconds", 1.0),
                base_url=source.config.get("base_url"),
                metadata=source.metadata,
            )

            # List issues from source
            filters = self._build_list_filters(source, mode)
            list_result = await client.list_issues(client_config, **filters)

            if not list_result.success:
                raise PipelineError(
                    f"Failed to list issues: {list_result.error}",
                    source=source.id,
                )

            # Get issues from response
            issues_data = (list_result.data or {}).get("issues", [])
            result.issues_fetched = len(issues_data)

            if not issues_data:
                result.mark_complete(success=True)
                return result

            # Transform and convert issues in batches
            for i in range(0, len(issues_data), self._config.batch_size):
                batch = issues_data[i : i + self._config.batch_size]
                await self._process_batch(
                    source=source,
                    batch=batch,
                    client=client,
                    client_config=client_config,
                    result=result,
                )

            result.mark_complete(success=True)

        except Exception as e:
            result.mark_complete(success=False, error=str(e))

        return result

    async def process_webhook(
        self,
        source_type: str,
        payload: dict[str, Any],
        signature: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> IngestionResult:
        """
        Process a webhook event from an issue source.

        Validates webhook signature, extracts issue data,
        and processes it through the pipeline.

        Args:
            source_type: Type of source (github, gitlab, linear)
            payload: Webhook payload data
            signature: Webhook signature for verification
            source_id: Optional source ID (for looking up config)

        Returns:
            IngestionResult for the webhook processing

        Example:
            >>> result = await pipeline.process_webhook(
            ...     source_type="github",
            ...     payload=webhook_data,
            ...     signature=request.headers["X-Hub-Signature-256"],
            ...     source_id="github-repo"
            ... )
        """
        result = IngestionResult(
            source_id=source_id or "webhook",
            mode=IngestionMode.WEBHOOK,
        )
        result.started_at = datetime.utcnow()

        try:
            # Map source type string to enum
            source_type_enum = SourceType(source_type)

            # Find source configuration
            source = None
            if source_id:
                source = next(
                    (s for s in self._config.sources if s.id == source_id),
                    None,
                )

            if not source:
                raise PipelineError(
                    f"Source not found for webhook: {source_id}",
                    source=source_id,
                )

            # Get client
            client = self._clients.get(source_type_enum)
            if not client:
                raise PipelineError(
                    f"No client for source type: {source_type}",
                    source=source_id,
                )

            # Build client config
            client_config = IssueClientConfig(
                source_type=IssueSourceType(source_type_enum.value),
                token=source.config.get("token"),
                repository=source.config.get("repository"),
                webhook_secret=source.config.get("webhook_secret"),
            )

            # Verify signature
            if signature:
                payload_bytes = str(payload).encode()
                is_valid = await client.verify_webhook(
                    payload_bytes,
                    signature,
                    client_config,
                )
                if not is_valid:
                    raise PipelineError(
                        "Webhook signature verification failed",
                        source=source_id,
                    )

            # Extract issue ID from webhook payload
            issue_id = self._extract_issue_id_from_webhook(
                source_type=source_type_enum,
                payload=payload,
            )

            if not issue_id:
                raise PipelineError(
                    "Could not extract issue ID from webhook payload",
                    source=source_id,
                )

            # Fetch full issue data
            fetch_result = await client.fetch_issue(issue_id, client_config)

            if not fetch_result.success:
                raise PipelineError(
                    f"Failed to fetch issue: {fetch_result.error}",
                    source=source_id,
                )

            # Process the issue
            result.issues_fetched = 1
            await self._process_single_issue(
                source=source,
                issue_data=fetch_result.data,
                client=client,
                client_config=client_config,
                result=result,
            )

            result.mark_complete(success=True)

        except Exception as e:
            result.mark_complete(success=False, error=str(e))

        return result

    async def _process_batch(
        self,
        source: IssueSource,
        batch: list[dict[str, Any]],
        client: IssueClient,
        client_config: IssueClientConfig,
        result: IngestionResult,
    ) -> None:
        """
        Process a batch of issues.

        Args:
            source: The issue source
            batch: List of issue data dictionaries
            client: Client for fetching additional data
            client_config: Client configuration
            result: Result object to update
        """
        for issue_data in batch:
            await self._process_single_issue(
                source=source,
                issue_data=issue_data,
                client=client,
                client_config=client_config,
                result=result,
            )

    async def _process_single_issue(
        self,
        source: IssueSource,
        issue_data: dict[str, Any],
        client: IssueClient,
        client_config: IssueClientConfig,
        result: IngestionResult,
    ) -> None:
        """
        Process a single issue through the pipeline.

        Transforms the issue data, converts to spec/task, and stores.

        Args:
            source: The issue source
            issue_data: Raw issue data from API
            client: Client for fetching additional data
            client_config: Client configuration
            result: Result object to update
        """
        try:
            # Transform to normalized Issue
            if source.type == SourceType.GITHUB:
                issue = self.transformer.from_github(issue_data, source)
            elif source.type == SourceType.GITLAB:
                issue = self.transformer.from_gitlab(issue_data, source)
            elif source.type == SourceType.LINEAR:
                issue = self.transformer.from_linear(issue_data, source)
            else:
                raise PipelineError(
                    f"Unsupported source type: {source.type.value}",
                    source=source.id,
                )

            result.issues_transformed += 1

            # Skip if filtering closed issues
            if self._config.filter_closed and issue.is_closed():
                return

            # Skip if label filter is configured and labels don't match
            if self._config.filter_labels:
                if not any(label in issue.labels for label in self._config.filter_labels):
                    return

            # Skip dry run
            if self._config.dry_run:
                return

            # Convert to spec/task
            spec, task = self.converter.convert_issue(
                issue,
                create_spec=self._config.create_specs,
                create_task=self._config.create_tasks,
            )

            # Store in state manager
            if spec:
                self.state.create_spec(spec)
                result.specs_created += 1

            if task:
                self.state.create_task(task)
                result.tasks_created += 1

        except Exception as e:
            error_msg = f"Failed to process issue: {e}"
            result.errors.append(error_msg)

    def _build_list_filters(
        self,
        source: IssueSource,
        mode: IngestionMode,
    ) -> dict[str, Any]:
        """
        Build filters for listing issues from a source.

        Args:
            source: The issue source
            mode: Ingestion mode

        Returns:
            Dictionary of filters for the list_issues API call
        """
        filters: dict[str, Any] = {
            "state": "all" if not self._config.filter_closed else "open",
            "per_page": self._config.batch_size,
        }

        # Add incremental filter (since last update)
        if mode == IngestionMode.INCREMENTAL:
            # Get last sync time from source metadata
            last_sync = source.metadata.get("last_sync_at")
            if last_sync:
                filters["since"] = last_sync

        # Add label filter if configured
        if self._config.filter_labels:
            filters["labels"] = ",".join(self._config.filter_labels)

        return filters

    def _extract_issue_id_from_webhook(
        self,
        source_type: SourceType,
        payload: dict[str, Any],
    ) -> Optional[str]:
        """
        Extract issue ID from webhook payload.

        Args:
            source_type: Type of source
            payload: Webhook payload

        Returns:
            Issue ID string or None
        """
        try:
            if source_type == SourceType.GITHUB:
                # GitHub webhook: payload["issue"]["number"]
                return str(payload.get("issue", {}).get("number", ""))

            elif source_type == SourceType.GITLAB:
                # GitLab webhook: payload["object_attributes"]["iid"]
                return str(payload.get("object_attributes", {}).get("iid", ""))

            elif source_type == SourceType.LINEAR:
                # Linear webhook: payload["data"]["issue"]["id"]
                return payload.get("data", {}).get("issue", {}).get("id", "")

        except (KeyError, AttributeError, TypeError):
            pass

        return None

    def get_stats(self) -> PipelineStats:
        """
        Get pipeline statistics.

        Returns:
            PipelineStats object with current statistics
        """
        return self._stats

    def reset_stats(self) -> None:
        """Reset pipeline statistics."""
        self._stats = PipelineStats()
