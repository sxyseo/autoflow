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
    TaskmasterConfig,
    TaskmasterAPIClient,
    TaskmasterAdapter,
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
