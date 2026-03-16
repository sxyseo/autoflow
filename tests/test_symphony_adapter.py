"""
Unit Tests for Symphony Adapter

Tests the SymphonyAdapter class for integration with Symphony's
multi-agent orchestration framework. Uses mocking to avoid requiring
actual CLI installation during tests.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.agents.base import (
    AgentConfig,
    ExecutionResult,
    ExecutionStatus,
    ResumeMode,
)
from autoflow.agents.symphony import SymphonyAdapter, SymphonyRuntime


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def adapter() -> SymphonyAdapter:
    """Create a basic SymphonyAdapter instance for testing."""
    return SymphonyAdapter()


@pytest.fixture
def custom_adapter() -> SymphonyAdapter:
    """Create a SymphonyAdapter with custom settings."""
    return SymphonyAdapter(
        command="symphony-custom",
        default_args=["agent", "run", "--verbose"],
        default_timeout=600,
        api_url="http://localhost:9090",
    )


@pytest.fixture
def config() -> AgentConfig:
    """Create a basic AgentConfig for testing."""
    return AgentConfig(
        command="symphony",
        args=["agent", "run"],
        timeout_seconds=300,
    )


@pytest.fixture
def temp_workdir(tmp_path: Path) -> Path:
    """Create a temporary working directory."""
    workdir = tmp_path / "project"
    workdir.mkdir()
    return workdir


# ============================================================================
# Initialization Tests
# ============================================================================


class TestSymphonyAdapterInit:
    """Tests for SymphonyAdapter initialization."""

    def test_init_defaults(self, adapter: SymphonyAdapter) -> None:
        """Test adapter initialization with default values."""
        assert adapter._command == "symphony"
        assert adapter._default_args == ["agent", "run"]
        assert adapter._default_timeout == 300
        assert adapter._api_url == "http://localhost:8080"
        assert adapter._active_sessions == {}

    def test_init_custom_values(self, custom_adapter: SymphonyAdapter) -> None:
        """Test adapter initialization with custom values."""
        assert custom_adapter._command == "symphony-custom"
        assert custom_adapter._default_args == ["agent", "run", "--verbose"]
        assert custom_adapter._default_timeout == 600
        assert custom_adapter._api_url == "http://localhost:9090"

    def test_init_partial_custom(self) -> None:
        """Test adapter initialization with partial custom values."""
        adapter = SymphonyAdapter(command="my-symphony", default_timeout=120)
        assert adapter._command == "my-symphony"
        assert adapter._default_args == ["agent", "run"]
        assert adapter._default_timeout == 120
        assert adapter._api_url == "http://localhost:8080"


# ============================================================================
# Resume Mode Tests
# ============================================================================


class TestSymphonyAdapterResumeMode:
    """Tests for resume mode handling."""

    def test_get_resume_mode(self, adapter: SymphonyAdapter) -> None:
        """Test that Symphony uses NATIVE resume mode."""
        assert adapter.get_resume_mode() == ResumeMode.NATIVE

    def test_supports_resume(self, adapter: SymphonyAdapter) -> None:
        """Test that adapter supports resume."""
        assert adapter.supports_resume() is True


# ============================================================================
# Command Building Tests
# ============================================================================


class TestSymphonyAdapterBuildCommand:
    """Tests for command building."""

    def test_build_command_basic(
        self, adapter: SymphonyAdapter, config: AgentConfig
    ) -> None:
        """Test building a basic command."""
        cmd = adapter._build_command("Fix the bug", config)

        assert cmd[0] == "symphony"
        assert "agent" in cmd
        assert "run" in cmd
        assert "Fix the bug" in cmd

    def test_build_command_with_session_id(
        self, adapter: SymphonyAdapter, config: AgentConfig
    ) -> None:
        """Test building a command with session ID for resume."""
        cmd = adapter._build_command(
            "Continue the task", config, session_id="session-abc-123"
        )

        assert "--session" in cmd
        assert "session-abc-123" in cmd
        assert "Continue the task" in cmd

    def test_build_command_with_api_url(
        self, adapter: SymphonyAdapter, config: AgentConfig
    ) -> None:
        """Test building a command with custom API URL."""
        config.metadata["api_url"] = "http://localhost:9090"
        cmd = adapter._build_command("Test prompt", config)

        assert "--api-url" in cmd
        assert "http://localhost:9090" in cmd

    def test_build_command_with_custom_args(self, adapter: SymphonyAdapter) -> None:
        """Test building a command with custom args from config."""
        config = AgentConfig(
            command="symphony",
            args=["agent", "run", "--verbose"],
        )
        cmd = adapter._build_command("Test prompt", config)

        assert "--verbose" in cmd

    def test_build_command_includes_timeout(
        self, adapter: SymphonyAdapter, config: AgentConfig
    ) -> None:
        """Test that command includes timeout."""
        cmd = adapter._build_command("Test prompt", config)

        assert "--timeout" in cmd
        assert "300" in cmd


# ============================================================================
# Session ID Extraction Tests
# ============================================================================


class TestSymphonyAdapterSessionExtraction:
    """Tests for session ID extraction from output."""

    def test_extract_session_id_from_session_line(self, adapter: SymphonyAdapter) -> None:
        """Test extracting session ID from 'Session:' line."""
        output = "Some output\nSession: abc-123-def\nMore output"
        session_id = adapter._extract_session_id(output)

        assert session_id == "abc-123-def"

    def test_extract_session_id_from_session_id_line(
        self, adapter: SymphonyAdapter
    ) -> None:
        """Test extracting session ID from 'session_id:' line."""
        output = "output\nsession_id: xyz-789\nend"
        session_id = adapter._extract_session_id(output)

        assert session_id == "xyz-789"

    def test_extract_session_id_from_json(self, adapter: SymphonyAdapter) -> None:
        """Test extracting session ID from JSON output."""
        output = '{"session_id": "json-session-123", "status": "running"}'
        session_id = adapter._extract_session_id(output)

        assert session_id == "json-session-123"

    def test_extract_session_id_from_json_camel_case(
        self, adapter: SymphonyAdapter
    ) -> None:
        """Test extracting sessionId from JSON (camelCase)."""
        output = '{"sessionId": "camel-123", "status": "running"}'
        session_id = adapter._extract_session_id(output)

        assert session_id == "camel-123"

    def test_extract_session_id_none(self, adapter: SymphonyAdapter) -> None:
        """Test extracting session ID from output without session info."""
        output = "Just some output\nWithout session info"
        session_id = adapter._extract_session_id(output)

        assert session_id is None

    def test_extract_session_id_empty_output(self, adapter: SymphonyAdapter) -> None:
        """Test extracting session ID from empty output."""
        assert adapter._extract_session_id(None) is None
        assert adapter._extract_session_id("") is None


# ============================================================================
# Output Parsing Tests
# ============================================================================


class TestSymphonyAdapterOutputParsing:
    """Tests for output parsing."""

    def test_parse_output_valid_json(self, adapter: SymphonyAdapter) -> None:
        """Test parsing valid JSON output."""
        json_str = '{"status": "success", "result": "done"}'
        result = adapter._parse_output(json_str)

        assert result == {"status": "success", "result": "done"}

    def test_parse_output_empty(self, adapter: SymphonyAdapter) -> None:
        """Test parsing empty output."""
        result = adapter._parse_output(None)
        assert result == {}

        result = adapter._parse_output("")
        assert result == {}

    def test_parse_output_invalid_json(self, adapter: SymphonyAdapter) -> None:
        """Test parsing invalid JSON returns raw output."""
        invalid_json = "This is not JSON"
        result = adapter._parse_output(invalid_json)

        assert result == {"raw_output": "This is not JSON"}


# ============================================================================
# Execute Tests
# ============================================================================


class TestSymphonyAdapterExecute:
    """Tests for the execute method."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test successful execution."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Task completed successfully", b"")
        mock_process.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            result = await adapter.execute(
                prompt="Fix the bug",
                workdir=temp_workdir,
                config=config,
            )

            assert result.success is True
            assert result.status == ExecutionStatus.SUCCESS
            assert result.output == "Task completed successfully"
            assert result.exit_code == 0
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_failure(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test execution with non-zero exit code."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"Error: Something went wrong")
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Fix the bug",
                workdir=temp_workdir,
                config=config,
            )

            assert result.success is False
            assert result.status == ExecutionStatus.FAILURE
            assert result.exit_code == 1
            assert "Error: Something went wrong" in result.error

    @pytest.mark.asyncio
    async def test_execute_timeout(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test execution timeout handling."""
        mock_process = AsyncMock()
        mock_process.communicate.side_effect = asyncio.TimeoutError()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Long running task",
                workdir=temp_workdir,
                config=config,
            )

            assert result.status == ExecutionStatus.TIMEOUT
            assert result.exit_code == -1
            assert "timed out" in result.error.lower()
            mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_not_found(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test handling when command is not found."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError()
        ):
            result = await adapter.execute(
                prompt="Fix the bug",
                workdir=temp_workdir,
                config=config,
            )

            assert result.status == ExecutionStatus.ERROR
            assert result.exit_code == -1
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_stores_session_info(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test that execute stores session information."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"Session: test-session-123\nTask completed",
            b"",
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Test prompt",
                workdir=temp_workdir,
                config=config,
            )

            assert result.session_id == "test-session-123"
            assert "test-session-123" in adapter._active_sessions
            assert adapter._active_sessions["test-session-123"]["prompt"] == "Test prompt"

    @pytest.mark.asyncio
    async def test_execute_without_session_id_uses_workdir(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test that execute uses workdir as session_id when no session in output."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Test prompt",
                workdir=temp_workdir,
                config=config,
            )

            assert result.session_id is not None
            assert str(temp_workdir.resolve()) in result.session_id

    @pytest.mark.asyncio
    async def test_execute_parses_json_output(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test that execute parses JSON output when available."""
        json_output = {"status": "done", "agents_used": 3}
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            json.dumps(json_output).encode(),
            b"",
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Test",
                workdir=temp_workdir,
                config=config,
            )

            assert "parsed_output" in result.metadata
            assert result.metadata["parsed_output"] == json_output

    @pytest.mark.asyncio
    async def test_execute_with_string_workdir(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test execution with string workdir (converted to Path)."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Test",
                workdir=str(temp_workdir),
                config=config,
            )

            assert result.success is True


# ============================================================================
# Resume Tests
# ============================================================================


class TestSymphonyAdapterResume:
    """Tests for the resume method."""

    @pytest.mark.asyncio
    async def test_resume_success(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test successful session resume."""
        # First, create a session
        adapter._active_sessions["test-session"] = {
            "prompt": "Original task",
            "workdir": str(temp_workdir),
        }

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Task continued", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.resume(
                session_id="test-session",
                new_prompt="Continue the task",
                config=config,
            )

            assert result.success is True
            assert result.output == "Task continued"
            assert result.session_id == "test-session"

    @pytest.mark.asyncio
    async def test_resume_invalid_session(self, adapter: SymphonyAdapter) -> None:
        """Test resume with non-existent session ID."""
        result = await adapter.resume(
            session_id="nonexistent-session",
            new_prompt="Continue",
        )

        assert result.status == ExecutionStatus.ERROR
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_resume_workdir_not_exists(
        self, adapter: SymphonyAdapter
    ) -> None:
        """Test resume when work directory doesn't exist."""
        adapter._active_sessions["test-session"] = {
            "prompt": "Original task",
            "workdir": "/nonexistent/path",
        }

        result = await adapter.resume(
            session_id="test-session",
            new_prompt="Continue",
        )

        assert result.status == ExecutionStatus.ERROR
        assert "does not exist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_resume_updates_session_info(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test that resume updates session info with new prompt."""
        adapter._active_sessions["test-session"] = {
            "prompt": "Original task",
            "workdir": str(temp_workdir),
        }

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await adapter.resume(
                session_id="test-session",
                new_prompt="New task",
                config=config,
            )

            assert adapter._active_sessions["test-session"]["prompt"] == "New task"

    @pytest.mark.asyncio
    async def test_resume_without_config_uses_defaults(
        self,
        adapter: SymphonyAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test resume without config uses adapter defaults."""
        adapter._active_sessions["test-session"] = {
            "prompt": "Original task",
            "workdir": str(temp_workdir),
        }

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.resume(
                session_id="test-session",
                new_prompt="Continue",
            )

            assert result.success is True


# ============================================================================
# Health Check Tests
# ============================================================================


class TestSymphonyAdapterHealthCheck:
    """Tests for the check_health method."""

    @pytest.mark.asyncio
    async def test_check_health_available(self, adapter: SymphonyAdapter) -> None:
        """Test health check when CLI is available."""
        with patch("shutil.which", return_value="/usr/bin/symphony"):
            result = await adapter.check_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_health_not_available(self, adapter: SymphonyAdapter) -> None:
        """Test health check when CLI is not available."""
        with patch("shutil.which", return_value=None):
            result = await adapter.check_health()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_health_custom_command(
        self, custom_adapter: SymphonyAdapter
    ) -> None:
        """Test health check uses custom command."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/symphony-custom"
            result = await custom_adapter.check_health()

            mock_which.assert_called_with("symphony-custom")
            assert result is True


# ============================================================================
# Cleanup Tests
# ============================================================================


class TestSymphonyAdapterCleanup:
    """Tests for the cleanup method."""

    @pytest.mark.asyncio
    async def test_cleanup_specific_session(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test cleanup of a specific session."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"Session: test-session\nDone",
            b"",
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Test",
                workdir=temp_workdir,
                config=config,
            )

            session_id = result.session_id
            assert session_id in adapter._active_sessions

            await adapter.cleanup(session_id)
            assert session_id not in adapter._active_sessions

    @pytest.mark.asyncio
    async def test_cleanup_all_sessions(
        self,
        adapter: SymphonyAdapter,
        config: AgentConfig,
        tmp_path: Path,
    ) -> None:
        """Test cleanup of all sessions."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"Session: test-session\nDone",
            b"",
        )
        mock_process.returncode = 0

        workdir1 = tmp_path / "project1"
        workdir2 = tmp_path / "project2"
        workdir1.mkdir()
        workdir2.mkdir()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await adapter.execute(
                prompt="Test1",
                workdir=workdir1,
                config=config,
            )
            # Manually add another session to test
            adapter._active_sessions["manual-session"] = {"prompt": "Test"}

        assert len(adapter._active_sessions) >= 1

        await adapter.cleanup()
        assert len(adapter._active_sessions) == 0


# ============================================================================
# Active Sessions Tests
# ============================================================================


class TestSymphonyAdapterActiveSessions:
    """Tests for the get_active_sessions method."""

    def test_get_active_sessions_returns_copy(
        self, adapter: SymphonyAdapter
    ) -> None:
        """Test that get_active_sessions returns a copy, not the internal dict."""
        adapter._active_sessions["session1"] = {"prompt": "Test1"}
        adapter._active_sessions["session2"] = {"prompt": "Test2"}

        sessions = adapter.get_active_sessions()

        # Should be a copy
        assert sessions == adapter._active_sessions
        assert sessions is not adapter._active_sessions

        # Modifying returned dict shouldn't affect internal
        sessions["session3"] = {"prompt": "Test3"}
        assert "session3" not in adapter._active_sessions


# ============================================================================
# Representation Tests
# ============================================================================


class TestSymphonyAdapterRepr:
    """Tests for string representation."""

    def test_repr(self, adapter: SymphonyAdapter) -> None:
        """Test __repr__ includes key information."""
        repr_str = repr(adapter)

        assert "SymphonyAdapter" in repr_str
        assert "symphony" in repr_str
        assert "http://localhost:8080" in repr_str
        assert "native" in repr_str

    def test_repr_custom(self, custom_adapter: SymphonyAdapter) -> None:
        """Test __repr__ with custom settings."""
        repr_str = repr(custom_adapter)

        assert "symphony-custom" in repr_str
        assert "http://localhost:9090" in repr_str


# ============================================================================
# Config Default Handling Tests
# ============================================================================


class TestSymphonyAdapterConfigDefaults:
    """Tests for config default value handling."""

    @pytest.mark.asyncio
    async def test_execute_uses_config_command(
        self,
        adapter: SymphonyAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test that execute uses command from config when provided."""
        config = AgentConfig(command="symphony-from-config")
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await adapter.execute(
                prompt="Test",
                workdir=temp_workdir,
                config=config,
            )

            call_args = mock_exec.call_args[0]
            assert "symphony-from-config" in call_args

    @pytest.mark.asyncio
    async def test_execute_sets_default_command_if_missing(
        self,
        adapter: SymphonyAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test that execute sets default command if config missing."""
        config = AgentConfig(command="")  # Empty command
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await adapter.execute(
                prompt="Test",
                workdir=temp_workdir,
                config=config,
            )

            # Config should be updated with default command
            assert config.command == "symphony"
            call_args = mock_exec.call_args[0]
            assert "symphony" in call_args

    @pytest.mark.asyncio
    async def test_execute_uses_metadata_api_url(
        self,
        adapter: SymphonyAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test that execute uses api_url from metadata."""
        config = AgentConfig(
            command="symphony",
            metadata={"api_url": "http://custom:9090"},
        )
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await adapter.execute(
                prompt="Test",
                workdir=temp_workdir,
                config=config,
            )

            call_args = mock_exec.call_args[0]
            assert "--api-url" in call_args
            assert "http://custom:9090" in call_args
