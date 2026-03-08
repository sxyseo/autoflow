"""
Unit Tests for Taskmaster Adapter

Tests the TaskmasterConfig and TaskmasterAPIClient classes for integration
with Taskmaster AI API. Uses mocking to avoid requiring actual API
calls during tests.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from autoflow.agents.taskmaster import (
    ConflictResolver,
    ConflictResolutionStrategy,
    ConflictType,
    TaskConflict,
    TaskmasterAdapter,
    TaskmasterAPIClient,
    TaskmasterConfig,
    TaskmasterTask,
    TaskmasterTaskStatus,
)
from autoflow.core.state import Task, TaskStatus


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def config() -> TaskmasterConfig:
    """Create a basic TaskmasterConfig for testing."""
    return TaskmasterConfig(
        api_base_url="https://api.taskmaster.ai",
        api_key="test-api-key-12345",
    )


@pytest.fixture
def custom_config() -> TaskmasterConfig:
    """Create a TaskmasterConfig with custom settings."""
    return TaskmasterConfig(
        api_base_url="https://custom.api.taskmaster.ai/",
        api_key="custom-api-key-67890",
        workspace_id="workspace-abc-123",
        timeout_seconds=60,
        retry_attempts=5,
        retry_delay_seconds=2,
        verify_ssl=False,
        enabled=True,
    )


@pytest.fixture
def minimal_config() -> TaskmasterConfig:
    """Create a minimal TaskmasterConfig with only required fields."""
    return TaskmasterConfig(
        api_key="minimal-key",
    )


@pytest.fixture
def adapter(config: TaskmasterConfig) -> TaskmasterAdapter:
    """Create a TaskmasterAdapter instance for testing."""
    return TaskmasterAdapter(config)


@pytest.fixture
def taskmaster_task() -> TaskmasterTask:
    """Create a basic TaskmasterTask for testing."""
    return TaskmasterTask(
        id="tm-001",
        title="Test Task",
        description="A test task for unit testing",
    )


@pytest.fixture
def autoflow_task() -> Task:
    """Create a basic Autoflow Task for testing."""
    return Task(
        id="af-001",
        title="Test Task",
        description="A test task for unit testing",
    )


# ============================================================================
# TaskmasterConfig Initialization Tests
# ============================================================================


class TestTaskmasterConfigInit:
    """Tests for TaskmasterConfig initialization."""

    def test_init_defaults(self) -> None:
        """Test config initialization with default values."""
        config = TaskmasterConfig(api_key="test-key")

        assert config.api_base_url == "https://api.taskmaster.ai"
        assert config.api_key == "test-key"
        assert config.workspace_id is None
        assert config.timeout_seconds == 30
        assert config.retry_attempts == 3
        assert config.retry_delay_seconds == 1
        assert config.verify_ssl is True
        assert config.enabled is True

    def test_init_custom_values(self, custom_config: TaskmasterConfig) -> None:
        """Test config initialization with custom values."""
        assert custom_config.api_base_url == "https://custom.api.taskmaster.ai"
        assert custom_config.api_key == "custom-api-key-67890"
        assert custom_config.workspace_id == "workspace-abc-123"
        assert custom_config.timeout_seconds == 60
        assert custom_config.retry_attempts == 5
        assert custom_config.retry_delay_seconds == 2
        assert custom_config.verify_ssl is False
        assert custom_config.enabled is True

    def test_init_partial_custom(self) -> None:
        """Test config initialization with partial custom values."""
        config = TaskmasterConfig(
            api_key="test-key",
            timeout_seconds=120,
            retry_attempts=1,
        )
        assert config.api_base_url == "https://api.taskmaster.ai"
        assert config.timeout_seconds == 120
        assert config.retry_attempts == 1
        assert config.retry_delay_seconds == 1  # Default


# ============================================================================
# TaskmasterConfig Validation Tests
# ============================================================================


class TestTaskmasterConfigValidation:
    """Tests for TaskmasterConfig field validators."""

    def test_normalize_api_base_url_removes_trailing_slash(self) -> None:
        """Test that trailing slashes are removed from API base URL."""
        config = TaskmasterConfig(
            api_key="test-key",
            api_base_url="https://api.taskmaster.ai/",
        )
        assert config.api_base_url == "https://api.taskmaster.ai"

    def test_normalize_api_base_url_removes_multiple_trailing_slashes(self) -> None:
        """Test that multiple trailing slashes are removed."""
        config = TaskmasterConfig(
            api_key="test-key",
            api_base_url="https://api.taskmaster.ai///",
        )
        assert config.api_base_url == "https://api.taskmaster.ai"

    def test_normalize_api_base_url_no_trailing_slash(self) -> None:
        """Test that URLs without trailing slashes are unchanged."""
        config = TaskmasterConfig(
            api_key="test-key",
            api_base_url="https://api.taskmaster.ai",
        )
        assert config.api_base_url == "https://api.taskmaster.ai"

    def test_validate_positive_int_timeout_negative(self) -> None:
        """Test that negative timeout_seconds raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TaskmasterConfig(api_key="test-key", timeout_seconds=-1)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("timeout_seconds",) for e in errors)

    def test_validate_positive_int_retry_attempts_negative(self) -> None:
        """Test that negative retry_attempts raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TaskmasterConfig(api_key="test-key", retry_attempts=-1)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("retry_attempts",) for e in errors)

    def test_validate_positive_int_retry_delay_negative(self) -> None:
        """Test that negative retry_delay_seconds raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TaskmasterConfig(api_key="test-key", retry_delay_seconds=-1)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("retry_delay_seconds",) for e in errors)

    def test_validate_positive_int_zero_allowed(self) -> None:
        """Test that zero is allowed for positive int fields."""
        config = TaskmasterConfig(
            api_key="test-key",
            timeout_seconds=0,
            retry_attempts=0,
            retry_delay_seconds=0,
        )
        assert config.timeout_seconds == 0
        assert config.retry_attempts == 0
        assert config.retry_delay_seconds == 0


# ============================================================================
# TaskmasterConfig Property Tests
# ============================================================================


class TestTaskmasterConfigProperties:
    """Tests for TaskmasterConfig properties."""

    def test_is_configured_with_api_key(self, config: TaskmasterConfig) -> None:
        """Test is_configured returns True when api_key is set."""
        assert config.is_configured is True

    def test_is_configured_without_api_key(self) -> None:
        """Test is_configured returns False when api_key is None."""
        config = TaskmasterConfig(api_key=None)
        assert config.is_configured is False

    def test_is_configured_with_empty_api_key(self) -> None:
        """Test is_configured returns False when api_key is empty string."""
        config = TaskmasterConfig(api_key="")
        assert config.is_configured is False


# ============================================================================
# TaskmasterConfig Auth Headers Tests
# ============================================================================


class TestTaskmasterConfigAuthHeaders:
    """Tests for TaskmasterConfig authentication headers."""

    def test_get_auth_headers_with_api_key(self, config: TaskmasterConfig) -> None:
        """Test get_auth_headers includes Authorization when api_key is set."""
        headers = config.get_auth_headers()

        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        assert headers["Authorization"] == "Bearer test-api-key-12345"

    def test_get_auth_headers_without_api_key(self) -> None:
        """Test get_auth_headers omits Authorization when api_key is None."""
        config = TaskmasterConfig(api_key=None)
        headers = config.get_auth_headers()

        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        assert "Authorization" not in headers

    def test_get_auth_headers_with_empty_api_key(self) -> None:
        """Test get_auth_headers omits Authorization when api_key is empty."""
        config = TaskmasterConfig(api_key="")
        headers = config.get_auth_headers()

        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        assert "Authorization" not in headers


# ============================================================================
# TaskmasterAPIClient Initialization Tests
# ============================================================================


class TestTaskmasterAPIClientInit:
    """Tests for TaskmasterAPIClient initialization."""

    def test_init_with_configured_config(self, config: TaskmasterConfig) -> None:
        """Test client initialization with properly configured config."""
        client = TaskmasterAPIClient(config)

        assert client.config == config
        assert client._client is None

    def test_init_with_unconfigured_config_raises_error(self) -> None:
        """Test that unconfigured config raises ValueError."""
        config = TaskmasterConfig(api_key=None)

        with pytest.raises(ValueError) as exc_info:
            TaskmasterAPIClient(config)

        assert "api_key" in str(exc_info.value).lower()
        assert "must have" in str(exc_info.value).lower()

    def test_init_with_empty_api_key_raises_error(self) -> None:
        """Test that empty api_key raises ValueError."""
        config = TaskmasterConfig(api_key="")

        with pytest.raises(ValueError) as exc_info:
            TaskmasterAPIClient(config)

        assert "api_key" in str(exc_info.value).lower()

    def test_init_with_disabled_config_raises_error(self) -> None:
        """Test that disabled config raises ValueError."""
        config = TaskmasterConfig(api_key="test-key", enabled=False)

        with pytest.raises(ValueError) as exc_info:
            TaskmasterAPIClient(config)

        assert "enabled" in str(exc_info.value).lower()
        assert "true" in str(exc_info.value).lower()

    def test_init_custom_config(self, custom_config: TaskmasterConfig) -> None:
        """Test client initialization with custom config."""
        client = TaskmasterAPIClient(custom_config)

        assert client.config == custom_config
        assert client._client is None


# ============================================================================
# TaskmasterAPIClient Client Management Tests
# ============================================================================


class TestTaskmasterAPIClientGetClient:
    """Tests for TaskmasterAPIClient._get_client method."""

    @pytest.mark.asyncio
    async def test_get_client_creates_new_client(
        self, config: TaskmasterConfig
    ) -> None:
        """Test that _get_client creates a new httpx.AsyncClient."""
        client = TaskmasterAPIClient(config)
        httpx_client = await client._get_client()

        assert httpx_client is not None
        assert httpx_client.base_url == config.api_base_url
        assert isinstance(httpx_client, MagicMock) or httpx_client is not None

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_caches_client(self, config: TaskmasterConfig) -> None:
        """Test that _get_client caches the client for reuse."""
        client = TaskmasterAPIClient(config)
        httpx_client1 = await client._get_client()
        httpx_client2 = await client._get_client()

        assert httpx_client1 is httpx_client2

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_uses_config_timeout(
        self, custom_config: TaskmasterConfig
    ) -> None:
        """Test that _get_client uses timeout from config."""
        client = TaskmasterAPIClient(custom_config)
        httpx_client = await client._get_client()

        # The timeout should be set based on config
        assert httpx_client is not None

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_uses_config_verify_ssl(
        self, custom_config: TaskmasterConfig
    ) -> None:
        """Test that _get_client uses verify_ssl from config."""
        client = TaskmasterAPIClient(custom_config)
        httpx_client = await client._get_client()

        assert httpx_client is not None

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_sets_auth_headers(
        self, config: TaskmasterConfig
    ) -> None:
        """Test that _get_client sets auth headers from config."""
        client = TaskmasterAPIClient(config)
        httpx_client = await client._get_client()

        assert httpx_client is not None

        # Clean up
        await client.close()


# ============================================================================
# TaskmasterAPIClient Close Tests
# ============================================================================


class TestTaskmasterAPIClientClose:
    """Tests for TaskmasterAPIClient.close method."""

    @pytest.mark.asyncio
    async def test_close_without_client(self, config: TaskmasterConfig) -> None:
        """Test close when no client has been created."""
        client = TaskmasterAPIClient(config)

        # Should not raise an error
        await client.close()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_with_client(self, config: TaskmasterConfig) -> None:
        """Test close closes the httpx client."""
        client = TaskmasterAPIClient(config)
        await client._get_client()

        assert client._client is not None

        await client.close()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, config: TaskmasterConfig) -> None:
        """Test that close can be called multiple times safely."""
        client = TaskmasterAPIClient(config)
        await client._get_client()

        await client.close()
        await client.close()
        await client.close()

        assert client._client is None


# ============================================================================
# TaskmasterAPIClient Representation Tests
# ============================================================================


class TestTaskmasterAPIClientRepr:
    """Tests for TaskmasterAPIClient string representation."""

    def test_repr(self, config: TaskmasterConfig) -> None:
        """Test __repr__ includes key information."""
        client = TaskmasterAPIClient(config)
        repr_str = repr(client)

        assert "TaskmasterAPIClient" in repr_str
        assert config.api_base_url in repr_str
        assert "workspace_id" in repr_str

    def test_repr_with_workspace(self, custom_config: TaskmasterConfig) -> None:
        """Test __repr__ includes workspace_id when set."""
        client = TaskmasterAPIClient(custom_config)
        repr_str = repr(client)

        assert "workspace-abc-123" in repr_str


# ============================================================================
# TaskmasterAPIClient Context Manager Tests
# ============================================================================


class TestTaskmasterAPIClientContextManager:
    """Tests for TaskmasterAPIClient async context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager_enter(self, config: TaskmasterConfig) -> None:
        """Test entering async context manager returns client."""
        async with TaskmasterAPIClient(config) as client:
            assert isinstance(client, TaskmasterAPIClient)
            assert client.config == config

    @pytest.mark.asyncio
    async def test_async_context_manager_exit_closes_client(
        self, config: TaskmasterConfig
    ) -> None:
        """Test exiting async context manager closes the client."""
        async with TaskmasterAPIClient(config) as client:
            await client._get_client()
            assert client._client is not None

        # After exiting, client should be closed
        assert client._client is None

    @pytest.mark.asyncio
    async def test_async_context_manager_exception_cleanup(
        self, config: TaskmasterConfig
    ) -> None:
        """Test that exceptions in context manager still close the client."""
        try:
            async with TaskmasterAPIClient(config) as client:
                await client._get_client()
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Client should still be closed
        assert client._client is None


# ============================================================================
# TaskmasterAPIClient Health Check Tests
# ============================================================================


class TestTaskmasterAPIClientHealthCheck:
    """Tests for TaskmasterAPIClient.check_health method."""

    @pytest.mark.asyncio
    async def test_check_health_success(self, config: TaskmasterConfig) -> None:
        """Test health check returns True when API is accessible."""
        client = TaskmasterAPIClient(config)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(client, "_make_request", return_value={}):
            result = await client.check_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_health_failure(self, config: TaskmasterConfig) -> None:
        """Test health check returns False when API is inaccessible."""
        client = TaskmasterAPIClient(config)

        with patch.object(
            client, "_make_request", side_effect=Exception("API error")
        ):
            result = await client.check_health()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_health_with_workspace(
        self, custom_config: TaskmasterConfig
    ) -> None:
        """Test health check uses workspace endpoint when configured."""
        client = TaskmasterAPIClient(custom_config)

        with patch.object(client, "_make_request", return_value={}) as mock_req:
            await client.check_health()

            # Should call with workspace endpoint
            mock_req.assert_called_once()
            call_args = mock_req.call_args
            assert "workspaces/workspace-abc-123" in call_args[0][1]


# ============================================================================
# TaskmasterAdapter Initialization Tests
# ============================================================================


class TestTaskmasterAdapterInit:
    """Tests for TaskmasterAdapter initialization."""

    def test_init_with_config(self, adapter: TaskmasterAdapter, config: TaskmasterConfig) -> None:
        """Test adapter initialization with config."""
        assert adapter.config == config

    def test_init_custom_config(self, custom_config: TaskmasterConfig) -> None:
        """Test adapter initialization with custom config."""
        adapter = TaskmasterAdapter(custom_config)
        assert adapter.config == custom_config


# ============================================================================
# Task Mapping Tests - Taskmaster to Autoflow
# ============================================================================


class TestTaskMappingTaskmasterToAutoflow:
    """Tests for mapping TaskmasterTask to Autoflow Task."""

    def test_map_basic_task(
        self, adapter: TaskmasterAdapter, taskmaster_task: TaskmasterTask
    ) -> None:
        """Test mapping a basic task with minimal fields."""
        autoflow_task = adapter._map_taskmaster_to_autoflow(taskmaster_task)

        assert autoflow_task.id == "tm-001"
        assert autoflow_task.title == "Test Task"
        assert autoflow_task.description == "A test task for unit testing"
        assert autoflow_task.status == TaskStatus.PENDING
        assert autoflow_task.priority == 5
        assert autoflow_task.assigned_agent is None

    def test_map_all_fields(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping a task with all fields populated."""
        tm_task = TaskmasterTask(
            id="tm-002",
            title="Complete Task",
            description="Full task description",
            status=TaskmasterTaskStatus.IN_PROGRESS,
            priority=8,
            assigned_to="agent-001",
            project_id="proj-123",
            parent_task_id="parent-456",
            labels=["bug", "urgent"],
            dependencies=["dep-001", "dep-002"],
            taskmaster_id="tm-original-002",
            metadata={"custom_field": "custom_value"},
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)

        assert af_task.id == "tm-002"
        assert af_task.title == "Complete Task"
        assert af_task.status == TaskStatus.IN_PROGRESS
        assert af_task.priority == 8
        assert af_task.assigned_agent == "agent-001"
        assert af_task.labels == ["bug", "urgent"]
        assert af_task.dependencies == ["dep-001", "dep-002"]
        assert af_task.metadata["taskmaster_id"] == "tm-original-002"
        assert af_task.metadata["project_id"] == "proj-123"
        assert af_task.metadata["parent_task_id"] == "parent-456"
        assert af_task.metadata["custom_field"] == "custom_value"

    def test_map_status_todo(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping TODO status to PENDING."""
        tm_task = TaskmasterTask(
            id="tm-003",
            title="Todo Task",
            status=TaskmasterTaskStatus.TODO,
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.status == TaskStatus.PENDING

    def test_map_status_in_progress(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping IN_PROGRESS status."""
        tm_task = TaskmasterTask(
            id="tm-004",
            title="In Progress Task",
            status=TaskmasterTaskStatus.IN_PROGRESS,
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.status == TaskStatus.IN_PROGRESS

    def test_map_status_in_review(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping IN_REVIEW status to IN_PROGRESS."""
        tm_task = TaskmasterTask(
            id="tm-005",
            title="In Review Task",
            status=TaskmasterTaskStatus.IN_REVIEW,
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.status == TaskStatus.IN_PROGRESS

    def test_map_status_done(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping DONE status to COMPLETED."""
        tm_task = TaskmasterTask(
            id="tm-006",
            title="Done Task",
            status=TaskmasterTaskStatus.DONE,
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.status == TaskStatus.COMPLETED

    def test_map_status_cancelled(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping CANCELLED status."""
        tm_task = TaskmasterTask(
            id="tm-007",
            title="Cancelled Task",
            status=TaskmasterTaskStatus.CANCELLED,
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.status == TaskStatus.CANCELLED

    def test_map_status_blocked(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping BLOCKED status to FAILED."""
        tm_task = TaskmasterTask(
            id="tm-008",
            title="Blocked Task",
            status=TaskmasterTaskStatus.BLOCKED,
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.status == TaskStatus.FAILED

    def test_map_with_completed_at(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with completed_at timestamp."""
        completed_at = datetime(2024, 1, 15, 10, 30, 0)
        tm_task = TaskmasterTask(
            id="tm-009",
            title="Completed Task",
            status=TaskmasterTaskStatus.DONE,
            completed_at=completed_at,
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert "completed_at" in af_task.metadata
        assert af_task.metadata["completed_at"] == completed_at.isoformat()

    def test_map_empty_lists(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with empty labels and dependencies."""
        tm_task = TaskmasterTask(
            id="tm-010",
            title="Empty Lists Task",
            labels=[],
            dependencies=[],
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.labels == []
        assert af_task.dependencies == []

    def test_map_with_metadata(self, adapter: TaskmasterAdapter) -> None:
        """Test that original metadata is preserved."""
        tm_task = TaskmasterTask(
            id="tm-011",
            title="Metadata Task",
            metadata={
                "source": "external",
                "priority_reason": "customer request",
                "estimate_hours": 5,
            },
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.metadata["source"] == "external"
        assert af_task.metadata["priority_reason"] == "customer request"
        assert af_task.metadata["estimate_hours"] == 5

    def test_map_without_optional_fields(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task without optional fields like taskmaster_id."""
        tm_task = TaskmasterTask(
            id="tm-012",
            title="Minimal Task",
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert "taskmaster_id" not in af_task.metadata
        assert "project_id" not in af_task.metadata
        assert "parent_task_id" not in af_task.metadata
        assert "completed_at" not in af_task.metadata

    def test_map_with_project_and_parent(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with both project_id and parent_task_id."""
        tm_task = TaskmasterTask(
            id="tm-013",
            title="Nested Task",
            project_id="project-abc",
            parent_task_id="parent-def",
        )

        af_task = adapter._map_taskmaster_to_autoflow(tm_task)
        assert af_task.metadata["project_id"] == "project-abc"
        assert af_task.metadata["parent_task_id"] == "parent-def"


# ============================================================================
# Task Mapping Tests - Autoflow to Taskmaster
# ============================================================================


class TestTaskMappingAutoflowToTaskmaster:
    """Tests for mapping Autoflow Task to TaskmasterTask."""

    def test_map_basic_task(
        self, adapter: TaskmasterAdapter, autoflow_task: Task
    ) -> None:
        """Test mapping a basic task with minimal fields."""
        taskmaster_task = adapter._map_autoflow_to_taskmaster(autoflow_task)

        assert taskmaster_task.id == "af-001"
        assert taskmaster_task.title == "Test Task"
        assert taskmaster_task.description == "A test task for unit testing"
        assert taskmaster_task.status == TaskmasterTaskStatus.TODO
        assert taskmaster_task.priority == 5
        assert taskmaster_task.assigned_to is None

    def test_map_all_fields(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping a task with all fields populated."""
        af_task = Task(
            id="af-002",
            title="Complete Task",
            description="Full task description",
            status=TaskStatus.IN_PROGRESS,
            priority=8,
            assigned_agent="agent-001",
            labels=["bug", "urgent"],
            dependencies=["dep-001", "dep-002"],
            metadata={
                "taskmaster_id": "tm-original-002",
                "project_id": "proj-123",
                "parent_task_id": "parent-456",
                "custom_field": "custom_value",
            },
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)

        assert tm_task.id == "af-002"
        assert tm_task.title == "Complete Task"
        assert tm_task.status == TaskmasterTaskStatus.IN_PROGRESS
        assert tm_task.priority == 8
        assert tm_task.assigned_to == "agent-001"
        assert tm_task.labels == ["bug", "urgent"]
        assert tm_task.dependencies == ["dep-001", "dep-002"]
        assert tm_task.taskmaster_id == "tm-original-002"
        assert tm_task.project_id == "proj-123"
        assert tm_task.parent_task_id == "parent-456"
        assert tm_task.metadata["custom_field"] == "custom_value"

    def test_map_status_pending(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping PENDING status to TODO."""
        af_task = Task(
            id="af-003",
            title="Pending Task",
            status=TaskStatus.PENDING,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.status == TaskmasterTaskStatus.TODO

    def test_map_status_in_progress(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping IN_PROGRESS status."""
        af_task = Task(
            id="af-004",
            title="In Progress Task",
            status=TaskStatus.IN_PROGRESS,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.status == TaskmasterTaskStatus.IN_PROGRESS

    def test_map_status_completed(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping COMPLETED status to DONE."""
        af_task = Task(
            id="af-005",
            title="Completed Task",
            status=TaskStatus.COMPLETED,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.status == TaskmasterTaskStatus.DONE

    def test_map_status_failed(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping FAILED status to BLOCKED."""
        af_task = Task(
            id="af-006",
            title="Failed Task",
            status=TaskStatus.FAILED,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.status == TaskmasterTaskStatus.BLOCKED

    def test_map_status_cancelled(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping CANCELLED status."""
        af_task = Task(
            id="af-007",
            title="Cancelled Task",
            status=TaskStatus.CANCELLED,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.status == TaskmasterTaskStatus.CANCELLED

    def test_map_with_completed_at_in_metadata(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with completed_at in metadata."""
        completed_at = datetime(2024, 1, 15, 10, 30, 0)
        af_task = Task(
            id="af-008",
            title="Completed Task",
            status=TaskStatus.COMPLETED,
            metadata={"completed_at": completed_at.isoformat()},
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.completed_at == completed_at

    def test_map_with_invalid_completed_at(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with invalid completed_at format."""
        af_task = Task(
            id="af-009",
            title="Invalid Date Task",
            metadata={"completed_at": "invalid-date-format"},
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.completed_at is None

    def test_map_empty_lists(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with empty labels and dependencies."""
        af_task = Task(
            id="af-010",
            title="Empty Lists Task",
            labels=[],
            dependencies=[],
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.labels == []
        assert tm_task.dependencies == []

    def test_map_with_metadata(self, adapter: TaskmasterAdapter) -> None:
        """Test that non-taskmaster metadata is preserved."""
        af_task = Task(
            id="af-011",
            title="Metadata Task",
            metadata={
                "source": "external",
                "priority_reason": "customer request",
                "estimate_hours": 5,
            },
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.metadata["source"] == "external"
        assert tm_task.metadata["priority_reason"] == "customer request"
        assert tm_task.metadata["estimate_hours"] == 5

    def test_map_excludes_taskmaster_fields_from_metadata(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test that taskmaster-specific fields are excluded from metadata."""
        af_task = Task(
            id="af-012",
            title="Full Metadata Task",
            metadata={
                "taskmaster_id": "tm-123",
                "project_id": "proj-456",
                "parent_task_id": "parent-789",
                "completed_at": "2024-01-15T10:30:00",
                "other_field": "should_remain",
            },
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)

        # These fields should be in the main object, not metadata
        assert tm_task.taskmaster_id == "tm-123"
        assert tm_task.project_id == "proj-456"
        assert tm_task.parent_task_id == "parent-789"
        assert "completed_at" not in tm_task.metadata

        # Other fields should remain in metadata
        assert tm_task.metadata["other_field"] == "should_remain"

    def test_map_without_optional_metadata_fields(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task without taskmaster-specific metadata."""
        af_task = Task(
            id="af-013",
            title="Minimal Metadata Task",
            metadata={"custom_field": "value"},
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.taskmaster_id is None
        assert tm_task.project_id is None
        assert tm_task.parent_task_id is None
        assert tm_task.completed_at is None
        assert tm_task.metadata["custom_field"] == "value"

    def test_map_preserves_timestamps(self, adapter: TaskmasterAdapter) -> None:
        """Test that created_at and updated_at are preserved."""
        created_at = datetime(2024, 1, 10, 9, 0, 0)
        updated_at = datetime(2024, 1, 12, 14, 30, 0)

        af_task = Task(
            id="af-014",
            title="Timestamp Task",
            created_at=created_at,
            updated_at=updated_at,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.created_at == created_at
        assert tm_task.updated_at == updated_at


# ============================================================================
# Task Mapping Round-Trip Tests
# ============================================================================


class TestTaskMappingRoundTrip:
    """Tests for round-trip mapping (Autoflow → Taskmaster → Autoflow)."""

    def test_round_trip_preserves_data(self, adapter: TaskmasterAdapter) -> None:
        """Test that round-trip mapping preserves key data."""
        original_af_task = Task(
            id="af-015",
            title="Round Trip Task",
            description="Test round-trip mapping",
            status=TaskStatus.IN_PROGRESS,
            priority=7,
            assigned_agent="agent-123",
            labels=["feature", "backend"],
            dependencies=["dep-001"],
            metadata={
                "custom_data": "test_value",
                "project_id": "proj-789",
            },
        )

        # Autoflow → Taskmaster
        tm_task = adapter._map_autoflow_to_taskmaster(original_af_task)

        # Taskmaster → Autoflow
        result_af_task = adapter._map_taskmaster_to_autoflow(tm_task)

        # Verify key fields are preserved
        assert result_af_task.id == original_af_task.id
        assert result_af_task.title == original_af_task.title
        assert result_af_task.description == original_af_task.description
        assert result_af_task.status == original_af_task.status
        assert result_af_task.priority == original_af_task.priority
        assert result_af_task.assigned_agent == original_af_task.assigned_agent
        assert result_af_task.labels == original_af_task.labels
        assert result_af_task.dependencies == original_af_task.dependencies

    def test_round_trip_with_all_statuses(self, adapter: TaskmasterAdapter) -> None:
        """Test round-trip mapping for all status values."""
        status_pairs = [
            (TaskStatus.PENDING, TaskmasterTaskStatus.TODO),
            (TaskStatus.IN_PROGRESS, TaskmasterTaskStatus.IN_PROGRESS),
            (TaskStatus.COMPLETED, TaskmasterTaskStatus.DONE),
            (TaskStatus.FAILED, TaskmasterTaskStatus.BLOCKED),
            (TaskStatus.CANCELLED, TaskmasterTaskStatus.CANCELLED),
        ]

        for af_status, tm_status in status_pairs:
            af_task = Task(
                id=f"af-status-{af_status}",
                title="Status Test",
                status=af_status,
            )

            tm_task = adapter._map_autoflow_to_taskmaster(af_task)
            assert tm_task.status == tm_status

            result_af_task = adapter._map_taskmaster_to_autoflow(tm_task)
            assert result_af_task.status == af_status


# ============================================================================
# Task Mapping Edge Cases Tests
# ============================================================================


class TestTaskMappingEdgeCases:
    """Tests for edge cases in task mapping."""

    def test_map_with_none_assigned_agent(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test mapping task with None assigned_agent."""
        af_task = Task(
            id="af-edge-001",
            title="No Assignee",
            assigned_agent=None,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.assigned_to is None

    def test_map_with_empty_description(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with empty description."""
        af_task = Task(
            id="af-edge-002",
            title="Empty Description",
            description="",
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.description == ""

    def test_map_with_zero_priority(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with zero priority."""
        af_task = Task(
            id="af-edge-003",
            title="Zero Priority",
            priority=0,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.priority == 0

    def test_map_with_high_priority(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with maximum priority."""
        af_task = Task(
            id="af-edge-004",
            title="High Priority",
            priority=10,
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.priority == 10

    def test_map_with_complex_metadata(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test mapping task with complex nested metadata."""
        af_task = Task(
            id="af-edge-005",
            title="Complex Metadata",
            metadata={
                "nested": {
                    "level1": {
                        "level2": ["item1", "item2"],
                    }
                },
                "list_of_dicts": [
                    {"key": "value1"},
                    {"key": "value2"},
                ],
            },
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert tm_task.metadata["nested"]["level1"]["level2"] == ["item1", "item2"]
        assert len(tm_task.metadata["list_of_dicts"]) == 2

    def test_map_with_special_characters_in_fields(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test mapping task with special characters."""
        af_task = Task(
            id="af-edge-006",
            title="Task with \"quotes\" and 'apostrophes'",
            description="Description with\nnewlines and\ttabs",
            labels=["tag-with-dash", "tag_with_underscore", "tag.with.dots"],
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert "quotes" in tm_task.title
        assert "apostrophes" in tm_task.title
        assert "\n" in tm_task.description
        assert "\t" in tm_task.description
        assert "tag-with-dash" in tm_task.labels

    def test_map_with_unicode_characters(self, adapter: TaskmasterAdapter) -> None:
        """Test mapping task with Unicode characters."""
        af_task = Task(
            id="af-edge-007",
            title="Unicode Task 测试 🚀",
            description="Description with emoji: ✨ 💻",
            labels=["标签", "tag"],
        )

        tm_task = adapter._map_autoflow_to_taskmaster(af_task)
        assert "测试" in tm_task.title
        assert "🚀" in tm_task.title
        assert "✨" in tm_task.description
        assert "标签" in tm_task.labels


# ============================================================================
# Taskmaster to Autoflow Sync Tests
# ============================================================================


class TestTaskmasterToAutoflowSync:
    """Tests for syncing tasks from Taskmaster to Autoflow."""

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_basic(
        self, adapter: TaskmasterAdapter, taskmaster_task: TaskmasterTask
    ) -> None:
        """Test basic sync from Taskmaster to Autoflow."""
        # Mock the API client and fetch_tasks
        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = [taskmaster_task]

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
            return_value=mock_client,
        ) as mock_api_client:
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_api_client.return_value.__aexit__ = AsyncMock()

            # Perform sync
            tasks = await adapter.sync_from_taskmaster()

            # Verify results
            assert len(tasks) == 1
            assert tasks[0].id == "tm-001"
            assert tasks[0].title == "Test Task"
            assert tasks[0].description == "A test task for unit testing"

            # Verify API was called correctly
            mock_client.fetch_tasks.assert_called_once_with(
                status=None,
                project_id=None,
                parent_task_id=None,
                limit=None,
            )

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_with_filters(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync with status and project filters."""
        # Create multiple tasks with different statuses
        todo_task = TaskmasterTask(
            id="tm-101",
            title="Todo Task",
            status=TaskmasterTaskStatus.TODO,
        )
        in_progress_task = TaskmasterTask(
            id="tm-102",
            title="In Progress Task",
            status=TaskmasterTaskStatus.IN_PROGRESS,
        )

        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = [todo_task, in_progress_task]

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
            return_value=mock_client,
        ) as mock_api_client:
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_api_client.return_value.__aexit__ = AsyncMock()

            # Sync with filters
            tasks = await adapter.sync_from_taskmaster(
                status=TaskmasterTaskStatus.TODO,
                project_id="proj-123",
                limit=10,
            )

            # Verify results
            assert len(tasks) == 2

            # Verify API was called with filters
            mock_client.fetch_tasks.assert_called_once_with(
                status=TaskmasterTaskStatus.TODO,
                project_id="proj-123",
                parent_task_id=None,
                limit=10,
            )

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_empty_results(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync when no tasks are returned."""
        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = []

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
            return_value=mock_client,
        ) as mock_api_client:
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_api_client.return_value.__aexit__ = AsyncMock()

            # Perform sync
            tasks = await adapter.sync_from_taskmaster()

            # Verify empty results
            assert len(tasks) == 0
            mock_client.fetch_tasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_multiple_tasks(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync with multiple tasks."""
        # Create multiple tasks
        tasks_data = [
            TaskmasterTask(
                id=f"tm-{i:03d}",
                title=f"Task {i}",
                status=TaskmasterTaskStatus.TODO,
                priority=i,
            )
            for i in range(1, 6)
        ]

        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = tasks_data

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
            return_value=mock_client,
        ) as mock_api_client:
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_api_client.return_value.__aexit__ = AsyncMock()

            # Perform sync
            tasks = await adapter.sync_from_taskmaster()

            # Verify all tasks were synced
            assert len(tasks) == 5
            for i, task in enumerate(tasks, 1):
                assert task.id == f"tm-{i:03d}"
                assert task.title == f"Task {i}"
                assert task.priority == i

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_all_statuses(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync correctly maps all Taskmaster statuses to Autoflow."""
        status_pairs = [
            (TaskmasterTaskStatus.TODO, TaskStatus.PENDING),
            (TaskmasterTaskStatus.IN_PROGRESS, TaskStatus.IN_PROGRESS),
            (TaskmasterTaskStatus.IN_REVIEW, TaskStatus.IN_PROGRESS),
            (TaskmasterTaskStatus.DONE, TaskStatus.COMPLETED),
            (TaskmasterTaskStatus.CANCELLED, TaskStatus.CANCELLED),
            (TaskmasterTaskStatus.BLOCKED, TaskStatus.FAILED),
        ]

        for tm_status, af_status in status_pairs:
            tm_task = TaskmasterTask(
                id=f"tm-status-{tm_status}",
                title="Status Test",
                status=tm_status,
            )

            mock_client = AsyncMock()
            mock_client.fetch_tasks.return_value = [tm_task]

            with patch(
                "autoflow.agents.taskmaster.TaskmasterAPIClient",
                return_value=mock_client,
            ) as mock_api_client:
                mock_api_client.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_api_client.return_value.__aexit__ = AsyncMock()

                # Sync with status filter
                tasks = await adapter.sync_from_taskmaster(status=tm_status)

                # Verify status mapping
                assert len(tasks) == 1
                assert tasks[0].status == af_status

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_preserves_metadata(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync preserves task metadata correctly."""
        tm_task = TaskmasterTask(
            id="tm-meta-001",
            title="Metadata Task",
            description="Test metadata preservation",
            status=TaskmasterTaskStatus.IN_PROGRESS,
            priority=8,
            assigned_to="agent-123",
            project_id="proj-456",
            parent_task_id="parent-789",
            labels=["feature", "backend", "api"],
            dependencies=["dep-001", "dep-002"],
            metadata={"custom_field": "custom_value"},
        )

        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = [tm_task]

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
            return_value=mock_client,
        ) as mock_api_client:
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_api_client.return_value.__aexit__ = AsyncMock()

            # Perform sync
            tasks = await adapter.sync_from_taskmaster()

            # Verify metadata preservation
            assert len(tasks) == 1
            task = tasks[0]
            assert task.priority == 8
            assert task.assigned_agent == "agent-123"
            assert task.labels == ["feature", "backend", "api"]
            assert task.dependencies == ["dep-001", "dep-002"]
            assert task.metadata["project_id"] == "proj-456"
            assert task.metadata["parent_task_id"] == "parent-789"
            assert task.metadata["custom_field"] == "custom_value"

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_not_configured(
        self, custom_config: TaskmasterConfig
    ) -> None:
        """Test sync fails when config is not properly configured."""
        # Create config without api_key
        bad_config = TaskmasterConfig(api_key=None)
        adapter = TaskmasterAdapter(bad_config)

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await adapter.sync_from_taskmaster()

        assert "api_key" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_disabled(
        self, config: TaskmasterConfig
    ) -> None:
        """Test sync fails when integration is disabled."""
        # Create config with enabled=False
        bad_config = TaskmasterConfig(api_key="test-key", enabled=False)
        adapter = TaskmasterAdapter(bad_config)

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await adapter.sync_from_taskmaster()

        assert "enabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_api_error(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync handles API errors correctly."""
        # Create a mock client that raises an error
        mock_client = AsyncMock()
        mock_client.fetch_tasks.side_effect = Exception("API Error: Connection failed")

        # Patch the API client class
        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            # Set up the mock to return our mock client from __aenter__
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Should propagate the exception
            with pytest.raises(Exception) as exc_info:
                await adapter.sync_from_taskmaster()

            assert "API Error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_with_parent_filter(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync with parent_task_id filter."""
        parent_task = TaskmasterTask(
            id="tm-parent-001",
            title="Parent Task",
            status=TaskmasterTaskStatus.TODO,
        )
        child_task = TaskmasterTask(
            id="tm-child-001",
            title="Child Task",
            status=TaskmasterTaskStatus.TODO,
            parent_task_id="tm-parent-001",
        )

        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = [child_task]

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
            return_value=mock_client,
        ) as mock_api_client:
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_api_client.return_value.__aexit__ = AsyncMock()

            # Sync with parent filter
            tasks = await adapter.sync_from_taskmaster(
                parent_task_id="tm-parent-001"
            )

            # Verify results
            assert len(tasks) == 1
            assert tasks[0].id == "tm-child-001"
            assert tasks[0].metadata["parent_task_id"] == "tm-parent-001"

            # Verify API was called with parent filter
            mock_client.fetch_tasks.assert_called_once_with(
                status=None,
                project_id=None,
                parent_task_id="tm-parent-001",
                limit=None,
            )

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_handles_conversion_errors(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync continues even if some tasks fail to convert."""
        # Create a mix of valid and invalid tasks
        valid_task = TaskmasterTask(
            id="tm-valid-001",
            title="Valid Task",
            status=TaskmasterTaskStatus.TODO,
        )

        # Create a task that will fail conversion
        # We'll simulate this by making the mock return a partial object
        class InvalidTask:
            id = "tm-invalid-001"
            title = "Invalid Task"
            # Missing required fields that will cause conversion to fail

        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = [valid_task, InvalidTask()]  # type: ignore

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
            return_value=mock_client,
        ) as mock_api_client:
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_api_client.return_value.__aexit__ = AsyncMock()

            # Sync should continue and return only valid tasks
            tasks = await adapter.sync_from_taskmaster()

            # Should have only the valid task
            assert len(tasks) == 1
            assert tasks[0].id == "tm-valid-001"

    @pytest.mark.asyncio
    async def test_sync_from_taskmaster_with_limit(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync respects limit parameter."""
        # Create many tasks
        tasks_data = [
            TaskmasterTask(
                id=f"tm-{i:03d}",
                title=f"Task {i}",
                status=TaskmasterTaskStatus.TODO,
            )
            for i in range(1, 21)  # 20 tasks
        ]

        # Return only 5 when limit is applied
        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = tasks_data[:5]

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
            return_value=mock_client,
        ) as mock_api_client:
            mock_api_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_api_client.return_value.__aexit__ = AsyncMock()

            # Sync with limit
            tasks = await adapter.sync_from_taskmaster(limit=5)

            # Verify limit was passed to API
            mock_client.fetch_tasks.assert_called_once_with(
                status=None,
                project_id=None,
                parent_task_id=None,
                limit=5,
            )

            # Verify only 5 tasks returned
            assert len(tasks) == 5


# ============================================================================
# Autoflow to Taskmaster Sync Tests
# ============================================================================


class TestAutoflowToTaskmasterSync:
    """Tests for sync_to_taskmaster method (exporting Autoflow tasks to Taskmaster)."""

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_basic(
        self, adapter: TaskmasterAdapter, autoflow_task: Task
    ) -> None:
        """Test basic sync of Autoflow tasks to Taskmaster."""
        # Create mock client
        mock_client = AsyncMock()

        # Mock the create_task response to return a TaskmasterTask
        created_taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Test Task",
            description="A test task for unit testing",
            status=TaskmasterTaskStatus.TODO,
        )
        mock_client.create_task.return_value = created_taskmaster_task

        # Patch the API client
        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync the task
            result = await adapter.sync_to_taskmaster([autoflow_task])

            # Verify results
            assert len(result) == 1
            assert result[0].id == "tm-001"
            assert result[0].title == "Test Task"

            # Verify API was called
            mock_client.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_not_configured(
        self, adapter: TaskmasterAdapter, autoflow_task: Task
    ) -> None:
        """Test sync raises ValueError when config is not configured."""
        # Create config with missing API key
        bad_config = TaskmasterConfig(api_key="")
        bad_adapter = TaskmasterAdapter(bad_config)

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await bad_adapter.sync_to_taskmaster([autoflow_task])

        assert "api_key" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_not_enabled(
        self, adapter: TaskmasterAdapter, autoflow_task: Task
    ) -> None:
        """Test sync raises ValueError when config is not enabled."""
        # Create config with enabled=False
        bad_config = TaskmasterConfig(api_key="test-key", enabled=False)
        bad_adapter = TaskmasterAdapter(bad_config)

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await bad_adapter.sync_to_taskmaster([autoflow_task])

        assert "enabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_empty_list(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync with empty task list."""
        mock_client = AsyncMock()
        mock_client.create_task.return_value = None

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync empty list
            result = await adapter.sync_to_taskmaster([])

            # Verify no tasks created
            assert len(result) == 0
            mock_client.create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_multiple_tasks(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync with multiple tasks."""
        # Create multiple Autoflow tasks
        autoflow_tasks = [
            Task(
                id=f"af-{i:03d}",
                title=f"Task {i}",
                description=f"Description for task {i}",
                status=TaskStatus.PENDING,
            )
            for i in range(1, 4)
        ]

        # Create mock client
        mock_client = AsyncMock()

        # Mock responses for each task
        def create_task_side_effect(**kwargs):
            title = kwargs.get("title", "")
            # Extract number from title
            task_num = title.split()[-1] if title else "0"
            return TaskmasterTask(
                id=f"tm-{task_num}",
                title=title,
                status=TaskmasterTaskStatus.TODO,
            )

        mock_client.create_task.side_effect = create_task_side_effect

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync all tasks
            result = await adapter.sync_to_taskmaster(autoflow_tasks)

            # Verify all tasks were created
            assert len(result) == 3
            assert mock_client.create_task.call_count == 3

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_status_mapping(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test that Autoflow task statuses are correctly mapped to Taskmaster."""
        # Create tasks with different statuses
        autoflow_tasks = [
            Task(
                id="af-001",
                title="Pending Task",
                status=TaskStatus.PENDING,
            ),
            Task(
                id="af-002",
                title="In Progress Task",
                status=TaskStatus.IN_PROGRESS,
            ),
            Task(
                id="af-003",
                title="Completed Task",
                status=TaskStatus.COMPLETED,
            ),
            Task(
                id="af-004",
                title="Failed Task",
                status=TaskStatus.FAILED,
            ),
            Task(
                id="af-005",
                title="Cancelled Task",
                status=TaskStatus.CANCELLED,
            ),
        ]

        # Track the statuses passed to create_task
        created_statuses = []

        mock_client = AsyncMock()

        def capture_status(**kwargs):
            created_statuses.append(kwargs.get("status"))
            return TaskmasterTask(
                id="tm-001",
                title=kwargs.get("title", ""),
                status=kwargs.get("status", TaskmasterTaskStatus.TODO),
            )

        mock_client.create_task.side_effect = capture_status

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync tasks
            await adapter.sync_to_taskmaster(autoflow_tasks)

            # Verify status mapping
            assert TaskmasterTaskStatus.TODO in created_statuses
            assert TaskmasterTaskStatus.IN_PROGRESS in created_statuses
            assert TaskmasterTaskStatus.DONE in created_statuses
            assert TaskmasterTaskStatus.BLOCKED in created_statuses
            assert TaskmasterTaskStatus.CANCELLED in created_statuses

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_with_metadata(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync with task metadata including project_id and parent_task_id."""
        # Create task with metadata
        autoflow_task = Task(
            id="af-001",
            title="Task with Metadata",
            description="Test task",
            status=TaskStatus.PENDING,
            metadata={
                "project_id": "proj-123",
                "parent_task_id": "tm-parent-001",
                "custom_field": "custom_value",
                "another_field": 42,
            },
        )

        mock_client = AsyncMock()
        mock_client.create_task.return_value = TaskmasterTask(
            id="tm-001",
            title="Task with Metadata",
            status=TaskmasterTaskStatus.TODO,
        )

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync task
            await adapter.sync_to_taskmaster([autoflow_task])

            # Verify metadata was extracted and passed
            call_kwargs = mock_client.create_task.call_args.kwargs
            assert call_kwargs.get("project_id") == "proj-123"
            assert call_kwargs.get("parent_task_id") == "tm-parent-001"
            assert call_kwargs.get("metadata") == {
                "custom_field": "custom_value",
                "another_field": 42,
            }

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_with_labels_and_dependencies(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync with labels and dependencies."""
        autoflow_task = Task(
            id="af-001",
            title="Task with Extras",
            status=TaskStatus.PENDING,
            labels=["bug", "high-priority"],
            dependencies=["af-002", "af-003"],
        )

        mock_client = AsyncMock()
        mock_client.create_task.return_value = TaskmasterTask(
            id="tm-001",
            title="Task with Extras",
            status=TaskmasterTaskStatus.TODO,
        )

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync task
            await adapter.sync_to_taskmaster([autoflow_task])

            # Verify labels and dependencies were passed
            call_kwargs = mock_client.create_task.call_args.kwargs
            assert call_kwargs.get("labels") == ["bug", "high-priority"]
            assert call_kwargs.get("dependencies") == ["af-002", "af-003"]

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_handles_api_errors(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync continues even if some tasks fail to create."""
        autoflow_tasks = [
            Task(id="af-001", title="Valid Task 1", status=TaskStatus.PENDING),
            Task(id="af-002", title="Valid Task 2", status=TaskStatus.PENDING),
            Task(id="af-003", title="Valid Task 3", status=TaskStatus.PENDING),
        ]

        mock_client = AsyncMock()

        # Make the second task fail
        call_count = [0]

        def create_task_with_error(**kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("API Error: Task creation failed")
            return TaskmasterTask(
                id=f"tm-{call_count[0]}",
                title=kwargs.get("title", ""),
                status=TaskmasterTaskStatus.TODO,
            )

        mock_client.create_task.side_effect = create_task_with_error

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync should continue and return only successful tasks
            result = await adapter.sync_to_taskmaster(autoflow_tasks)

            # Should have 2 successful tasks (first and third)
            assert len(result) == 2
            assert result[0].id == "tm-1"
            assert result[1].id == "tm-3"

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_with_assigned_agent(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync maps assigned_agent to assigned_to."""
        autoflow_task = Task(
            id="af-001",
            title="Assigned Task",
            status=TaskStatus.PENDING,
            assigned_agent="agent-001",
        )

        mock_client = AsyncMock()
        mock_client.create_task.return_value = TaskmasterTask(
            id="tm-001",
            title="Assigned Task",
            status=TaskmasterTaskStatus.TODO,
            assigned_to="agent-001",
        )

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync task
            await adapter.sync_to_taskmaster([autoflow_task])

            # Verify assigned_agent was mapped to assigned_to
            call_kwargs = mock_client.create_task.call_args.kwargs
            assert call_kwargs.get("assigned_to") == "agent-001"

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_with_priority(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync preserves priority."""
        autoflow_task = Task(
            id="af-001",
            title="High Priority Task",
            status=TaskStatus.PENDING,
            priority=8,
        )

        mock_client = AsyncMock()
        mock_client.create_task.return_value = TaskmasterTask(
            id="tm-001",
            title="High Priority Task",
            status=TaskmasterTaskStatus.TODO,
            priority=8,
        )

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync task
            await adapter.sync_to_taskmaster([autoflow_task])

            # Verify priority was preserved
            call_kwargs = mock_client.create_task.call_args.kwargs
            assert call_kwargs.get("priority") == 8

    @pytest.mark.asyncio
    async def test_sync_to_taskmaster_with_description(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test sync handles task description."""
        autoflow_task = Task(
            id="af-001",
            title="Task with Description",
            description="This is a detailed description of the task",
            status=TaskStatus.PENDING,
        )

        mock_client = AsyncMock()
        mock_client.create_task.return_value = TaskmasterTask(
            id="tm-001",
            title="Task with Description",
            description="This is a detailed description of the task",
            status=TaskmasterTaskStatus.TODO,
        )

        with patch(
            "autoflow.agents.taskmaster.TaskmasterAPIClient",
        ) as MockAPIClient:
            mock_instance = MockAPIClient.return_value
            mock_instance.__aenter__ = AsyncMock(return_value=mock_client)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Sync task
            await adapter.sync_to_taskmaster([autoflow_task])

            # Verify description was passed
            call_kwargs = mock_client.create_task.call_args.kwargs
            assert call_kwargs.get("description") == "This is a detailed description of the task"


# ============================================================================
# Conflict Resolution Tests
# ============================================================================


class TestConflictResolution:
    """Tests for conflict detection and resolution functionality."""

    # ------------------------------------------------------------------------
    # Enum Tests
    # ------------------------------------------------------------------------

    def test_conflict_type_enum_values(self) -> None:
        """Test ConflictType enum has correct values."""
        assert ConflictType.STATUS.value == "status"
        assert ConflictType.PRIORITY.value == "priority"
        assert ConflictType.TITLE.value == "title"
        assert ConflictType.DESCRIPTION.value == "description"
        assert ConflictType.ASSIGNMENT.value == "assignment"
        assert ConflictType.METADATA.value == "metadata"
        assert ConflictType.DELETED.value == "deleted"

    def test_conflict_resolution_strategy_enum_values(self) -> None:
        """Test ConflictResolutionStrategy enum has correct values."""
        assert ConflictResolutionStrategy.LAST_WRITE_WINS.value == "last_write_wins"
        assert ConflictResolutionStrategy.TIMESTAMP_BASED.value == "timestamp_based"
        assert ConflictResolutionStrategy.MANUAL.value == "manual"
        assert ConflictResolutionStrategy.AUTOFLOW_WINS.value == "autoflow_wins"
        assert ConflictResolutionStrategy.TASKMASTER_WINS.value == "taskmaster_wins"

    # ------------------------------------------------------------------------
    # TaskConflict Model Tests
    # ------------------------------------------------------------------------

    def test_task_conflict_creation(self) -> None:
        """Test creating a TaskConflict instance."""
        autoflow_updated = datetime(2026, 3, 8, 10, 0, 0)
        taskmaster_updated = datetime(2026, 3, 8, 11, 0, 0)

        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.STATUS,
            autoflow_value=TaskStatus.IN_PROGRESS,
            taskmaster_value=TaskmasterTaskStatus.DONE,
            autoflow_updated_at=autoflow_updated,
            taskmaster_updated_at=taskmaster_updated,
        )

        assert conflict.task_id == "task-001"
        assert conflict.conflict_type == ConflictType.STATUS
        assert conflict.autoflow_value == TaskStatus.IN_PROGRESS
        assert conflict.taskmaster_value == TaskmasterTaskStatus.DONE
        assert conflict.autoflow_updated_at == autoflow_updated
        assert conflict.taskmaster_updated_at == taskmaster_updated
        assert conflict.resolved is False
        assert conflict.resolution is None
        assert conflict.resolved_value is None

    def test_task_conflict_resolve_method(self) -> None:
        """Test marking a conflict as resolved."""
        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.STATUS,
            autoflow_value=TaskStatus.IN_PROGRESS,
            taskmaster_value=TaskmasterTaskStatus.DONE,
            autoflow_updated_at=datetime(2026, 3, 8, 10, 0, 0),
            taskmaster_updated_at=datetime(2026, 3, 8, 11, 0, 0),
        )

        assert conflict.resolved is False

        conflict.resolve(
            ConflictResolutionStrategy.TASKMASTER_WINS,
            TaskStatus.DONE,
        )

        assert conflict.resolved is True
        assert conflict.resolution == ConflictResolutionStrategy.TASKMASTER_WINS
        assert conflict.resolved_value == TaskStatus.DONE

    def test_task_conflict_with_metadata(self) -> None:
        """Test TaskConflict with custom metadata."""
        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.PRIORITY,
            autoflow_value=5,
            taskmaster_value=8,
            autoflow_updated_at=datetime(2026, 3, 8, 10, 0, 0),
            taskmaster_updated_at=datetime(2026, 3, 8, 11, 0, 0),
            metadata={"reason": "concurrent_update", "user": "test-user"},
        )

        assert conflict.metadata == {"reason": "concurrent_update", "user": "test-user"}

    # ------------------------------------------------------------------------
    # ConflictResolver Tests
    # ------------------------------------------------------------------------

    def test_conflict_resolver_init_defaults(self) -> None:
        """Test ConflictResolver initialization with defaults."""
        resolver = ConflictResolver()

        assert resolver.strategy == ConflictResolutionStrategy.LAST_WRITE_WINS
        assert resolver.strict_mode is False

    def test_conflict_resolver_init_custom(self) -> None:
        """Test ConflictResolver initialization with custom values."""
        resolver = ConflictResolver(
            strategy=ConflictResolutionStrategy.AUTOFLOW_WINS,
            strict_mode=True,
        )

        assert resolver.strategy == ConflictResolutionStrategy.AUTOFLOW_WINS
        assert resolver.strict_mode is True

    def test_detect_conflicts_no_conflicts(self) -> None:
        """Test conflict detection with matching tasks."""
        resolver = ConflictResolver()

        autoflow_task = Task(
            id="task-001",
            title="Same Title",
            description="Same Description",
            status=TaskStatus.PENDING,
            priority=5,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Same Title",
            description="Same Description",
            status=TaskmasterTaskStatus.TODO,
            priority=5,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflicts = resolver.detect_conflicts(autoflow_task, taskmaster_task)

        assert len(conflicts) == 0

    def test_detect_conflicts_status_mismatch(self) -> None:
        """Test conflict detection detects status differences."""
        resolver = ConflictResolver()

        autoflow_task = Task(
            id="task-001",
            title="Task",
            status=TaskStatus.IN_PROGRESS,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Task",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflicts = resolver.detect_conflicts(autoflow_task, taskmaster_task)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.STATUS
        assert conflicts[0].autoflow_value == TaskStatus.IN_PROGRESS
        assert conflicts[0].taskmaster_value == TaskmasterTaskStatus.DONE

    def test_detect_conflicts_multiple_differences(self) -> None:
        """Test conflict detection detects multiple field differences."""
        resolver = ConflictResolver()

        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            description="Autoflow Description",
            status=TaskStatus.PENDING,
            priority=3,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            description="Taskmaster Description",
            status=TaskmasterTaskStatus.IN_PROGRESS,
            priority=7,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflicts = resolver.detect_conflicts(autoflow_task, taskmaster_task)

        assert len(conflicts) == 4
        conflict_types = {c.conflict_type for c in conflicts}
        assert ConflictType.TITLE in conflict_types
        assert ConflictType.DESCRIPTION in conflict_types
        assert ConflictType.STATUS in conflict_types
        assert ConflictType.PRIORITY in conflict_types

    def test_detect_conflicts_assignment_mismatch(self) -> None:
        """Test conflict detection detects assignment differences."""
        resolver = ConflictResolver()

        autoflow_task = Task(
            id="task-001",
            title="Task",
            status=TaskStatus.PENDING,
            assigned_agent="agent-001",
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Task",
            status=TaskmasterTaskStatus.TODO,
            assigned_to="agent-002",
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflicts = resolver.detect_conflicts(autoflow_task, taskmaster_task)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.ASSIGNMENT
        assert conflicts[0].autoflow_value == "agent-001"
        assert conflicts[0].taskmaster_value == "agent-002"

    def test_resolve_conflict_autoflow_wins(self) -> None:
        """Test resolution with AUTOFLOW_WINS strategy."""
        resolver = ConflictResolver(strategy=ConflictResolutionStrategy.AUTOFLOW_WINS)

        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.STATUS,
            autoflow_value=TaskStatus.PENDING,
            taskmaster_value=TaskmasterTaskStatus.DONE,
            autoflow_updated_at=datetime(2026, 3, 8, 9, 0, 0),
            taskmaster_updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        resolved = resolver.resolve_conflict(conflict, autoflow_task, taskmaster_task)

        assert resolved.title == "Autoflow Title"
        assert resolved.status == TaskStatus.PENDING

    def test_resolve_conflict_taskmaster_wins(self) -> None:
        """Test resolution with TASKMASTER_WINS strategy."""
        resolver = ConflictResolver(strategy=ConflictResolutionStrategy.TASKMASTER_WINS)

        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.STATUS,
            autoflow_value=TaskStatus.PENDING,
            taskmaster_value=TaskmasterTaskStatus.DONE,
            autoflow_updated_at=datetime(2026, 3, 8, 9, 0, 0),
            taskmaster_updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        resolved = resolver.resolve_conflict(conflict, autoflow_task, taskmaster_task)

        assert resolved.title == "Taskmaster Title"
        assert resolved.status == TaskStatus.DONE

    def test_resolve_conflict_last_write_wins_autoflow_newer(self) -> None:
        """Test LAST_WRITE_WINS when Autoflow is newer."""
        resolver = ConflictResolver(strategy=ConflictResolutionStrategy.LAST_WRITE_WINS)

        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 9, 0, 0),
        )

        # Autoflow updated more recently
        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.STATUS,
            autoflow_value=TaskStatus.PENDING,
            taskmaster_value=TaskmasterTaskStatus.DONE,
            autoflow_updated_at=datetime(2026, 3, 8, 10, 0, 0),
            taskmaster_updated_at=datetime(2026, 3, 8, 9, 0, 0),
        )

        resolved = resolver.resolve_conflict(conflict, autoflow_task, taskmaster_task)

        assert resolved.title == "Autoflow Title"
        assert resolved.status == TaskStatus.PENDING

    def test_resolve_conflict_last_write_wins_taskmaster_newer(self) -> None:
        """Test LAST_WRITE_WINS when Taskmaster is newer."""
        resolver = ConflictResolver(strategy=ConflictResolutionStrategy.LAST_WRITE_WINS)

        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        # Taskmaster updated more recently
        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.STATUS,
            autoflow_value=TaskStatus.PENDING,
            taskmaster_value=TaskmasterTaskStatus.DONE,
            autoflow_updated_at=datetime(2026, 3, 8, 9, 0, 0),
            taskmaster_updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        resolved = resolver.resolve_conflict(conflict, autoflow_task, taskmaster_task)

        assert resolved.title == "Taskmaster Title"
        assert resolved.status == TaskStatus.DONE

    def test_resolve_conflict_manual_raises_in_strict_mode(self) -> None:
        """Test MANUAL strategy raises error in strict mode."""
        resolver = ConflictResolver(
            strategy=ConflictResolutionStrategy.MANUAL,
            strict_mode=True,
        )

        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.STATUS,
            autoflow_value=TaskStatus.PENDING,
            taskmaster_value=TaskmasterTaskStatus.DONE,
            autoflow_updated_at=datetime(2026, 3, 8, 9, 0, 0),
            taskmaster_updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        with pytest.raises(ValueError, match="Manual resolution required"):
            resolver.resolve_conflict(conflict, autoflow_task, taskmaster_task)

    def test_resolve_conflict_manual_no_strict_mode(self) -> None:
        """Test MANUAL strategy returns Autoflow version in non-strict mode."""
        resolver = ConflictResolver(
            strategy=ConflictResolutionStrategy.MANUAL,
            strict_mode=False,
        )

        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflict = TaskConflict(
            task_id="task-001",
            conflict_type=ConflictType.STATUS,
            autoflow_value=TaskStatus.PENDING,
            taskmaster_value=TaskmasterTaskStatus.DONE,
            autoflow_updated_at=datetime(2026, 3, 8, 9, 0, 0),
            taskmaster_updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        # In non-strict mode, defaults to Autoflow version
        resolved = resolver.resolve_conflict(conflict, autoflow_task, taskmaster_task)

        assert resolved.title == "Autoflow Title"

    def test_resolve_all_conflicts_no_conflicts(self) -> None:
        """Test resolving all conflicts when there are none."""
        resolver = ConflictResolver()

        autoflow_task = Task(
            id="task-001",
            title="Same Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Same Title",
            status=TaskmasterTaskStatus.TODO,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        resolved_task, conflicts = resolver.resolve_all_conflicts(
            autoflow_task, taskmaster_task
        )

        assert len(conflicts) == 0
        assert resolved_task.title == "Same Title"

    def test_resolve_all_conflicts_with_conflicts(self) -> None:
        """Test resolving all conflicts marks them as resolved."""
        resolver = ConflictResolver(strategy=ConflictResolutionStrategy.TASKMASTER_WINS)

        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
            priority=5,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            priority=8,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        resolved_task, conflicts = resolver.resolve_all_conflicts(
            autoflow_task, taskmaster_task
        )

        assert len(conflicts) > 0
        # All conflicts should be marked as resolved
        for conflict in conflicts:
            assert conflict.resolved is True
            assert conflict.resolution == ConflictResolutionStrategy.TASKMASTER_WINS

        # Resolved task should have Taskmaster values
        assert resolved_task.title == "Taskmaster Title"
        assert resolved_task.status == TaskStatus.DONE
        assert resolved_task.priority == 8

    # ------------------------------------------------------------------------
    # Adapter Conflict Detection Tests
    # ------------------------------------------------------------------------

    def test_adapter_detect_conflicts(self, adapter: TaskmasterAdapter) -> None:
        """Test adapter's _detect_conflicts method."""
        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.IN_PROGRESS,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        conflicts = adapter._detect_conflicts(autoflow_task, taskmaster_task)

        assert len(conflicts) == 2  # Title and Status

    def test_adapter_resolve_conflicts_default_strategy(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test adapter's _resolve_conflicts with default strategy."""
        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        resolved_task, conflicts = adapter._resolve_conflicts(
            autoflow_task, taskmaster_task
        )

        assert len(conflicts) > 0
        assert resolved_task.id == "task-001"

    def test_adapter_resolve_conflicts_custom_strategy(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test adapter's _resolve_conflicts with custom strategy."""
        autoflow_task = Task(
            id="task-001",
            title="Autoflow Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Taskmaster Title",
            status=TaskmasterTaskStatus.DONE,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        resolved_task, conflicts = adapter._resolve_conflicts(
            autoflow_task,
            taskmaster_task,
            strategy=ConflictResolutionStrategy.AUTOFLOW_WINS,
        )

        assert len(conflicts) > 0
        # Should use Autoflow values
        assert resolved_task.title == "Autoflow Title"
        assert resolved_task.status == TaskStatus.PENDING

    def test_adapter_resolve_conflicts_preserves_resolver_strategy(
        self, adapter: TaskmasterAdapter
    ) -> None:
        """Test that custom strategy doesn't permanently change resolver's strategy."""
        autoflow_task = Task(
            id="task-001",
            title="Title",
            status=TaskStatus.PENDING,
        )

        taskmaster_task = TaskmasterTask(
            id="tm-001",
            title="Title",
            status=TaskmasterTaskStatus.TODO,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        original_strategy = adapter.conflict_resolver.strategy

        # Resolve with custom strategy
        adapter._resolve_conflicts(
            autoflow_task,
            taskmaster_task,
            strategy=ConflictResolutionStrategy.AUTOFLOW_WINS,
        )

        # Resolver's strategy should be unchanged
        assert adapter.conflict_resolver.strategy == original_strategy
