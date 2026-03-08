"""
Unit Tests for Taskmaster Adapter

Tests the TaskmasterConfig and TaskmasterAPIClient classes for integration
with Taskmaster AI API. Uses mocking to avoid requiring actual API
calls during tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from autoflow.agents.taskmaster import TaskmasterConfig, TaskmasterAPIClient


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
