"""
Unit Tests for Claude Code Adapter

Tests the ClaudeCodeAdapter class for integration with Anthropic's
Claude Code CLI tool. Uses mocking to avoid requiring actual CLI
installation during tests.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.agents.base import (
    AgentConfig,
    ExecutionResult,
    ExecutionStatus,
    ResumeMode,
)
from autoflow.agents.claude_code import ClaudeCodeAdapter


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def adapter() -> ClaudeCodeAdapter:
    """Create a basic ClaudeCodeAdapter instance for testing."""
    return ClaudeCodeAdapter()


@pytest.fixture
def custom_adapter() -> ClaudeCodeAdapter:
    """Create a ClaudeCodeAdapter with custom settings."""
    return ClaudeCodeAdapter(
        command="claude-custom",
        default_args=["--print", "--verbose"],
        default_timeout=600,
    )


@pytest.fixture
def config() -> AgentConfig:
    """Create a basic AgentConfig for testing."""
    return AgentConfig(
        command="claude",
        args=["--print"],
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


class TestClaudeCodeAdapterInit:
    """Tests for ClaudeCodeAdapter initialization."""

    def test_init_defaults(self, adapter: ClaudeCodeAdapter) -> None:
        """Test adapter initialization with default values."""
        assert adapter._command == "claude"
        assert adapter._default_args == ["--print"]
        assert adapter._default_timeout == 300

    def test_init_custom_command(self, custom_adapter: ClaudeCodeAdapter) -> None:
        """Test adapter initialization with custom command."""
        assert custom_adapter._command == "claude-custom"
        assert custom_adapter._default_args == ["--print", "--verbose"]
        assert custom_adapter._default_timeout == 600

    def test_init_partial_custom(self) -> None:
        """Test adapter initialization with partial custom values."""
        adapter = ClaudeCodeAdapter(command="my-claude")
        assert adapter._command == "my-claude"
        assert adapter._default_args == ["--print"]
        assert adapter._default_timeout == 300


# ============================================================================
# Resume Mode Tests
# ============================================================================


class TestClaudeCodeAdapterResumeMode:
    """Tests for resume mode handling."""

    def test_get_resume_mode(self, adapter: ClaudeCodeAdapter) -> None:
        """Test that Claude Code uses NATIVE resume mode."""
        assert adapter.get_resume_mode() == ResumeMode.NATIVE

    def test_supports_resume(self, adapter: ClaudeCodeAdapter) -> None:
        """Test that adapter supports resume."""
        assert adapter.supports_resume() is True


# ============================================================================
# Command Building Tests
# ============================================================================


class TestClaudeCodeAdapterBuildCommand:
    """Tests for command building."""

    def test_build_command_basic(
        self, adapter: ClaudeCodeAdapter, config: AgentConfig
    ) -> None:
        """Test building a basic command."""
        cmd = adapter._build_command("Fix the bug", config)

        assert cmd[0] == "claude"
        assert "--print" in cmd
        assert "Fix the bug" in cmd

    def test_build_command_with_session_id(
        self, adapter: ClaudeCodeAdapter, config: AgentConfig
    ) -> None:
        """Test building a command with session ID for resume."""
        cmd = adapter._build_command(
            "Continue the task", config, session_id="/path/to/project"
        )

        assert "-r" in cmd
        assert "/path/to/project" in cmd
        assert "Continue the task" in cmd

    def test_build_command_with_custom_args(self, adapter: ClaudeCodeAdapter) -> None:
        """Test building a command with custom args from config."""
        config = AgentConfig(
            command="claude",
            args=["--print", "--dangerously-skip-permissions"],
        )
        cmd = adapter._build_command("Test prompt", config)

        assert "--print" in cmd
        assert "--dangerously-skip-permissions" in cmd


# ============================================================================
# Execute Tests
# ============================================================================


class TestClaudeCodeAdapterExecute:
    """Tests for the execute method."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        adapter: ClaudeCodeAdapter,
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
        adapter: ClaudeCodeAdapter,
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
        adapter: ClaudeCodeAdapter,
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
        adapter: ClaudeCodeAdapter,
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
    async def test_execute_with_string_workdir(
        self,
        adapter: ClaudeCodeAdapter,
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

    @pytest.mark.asyncio
    async def test_execute_sets_session_id(
        self,
        adapter: ClaudeCodeAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test that execute sets session_id based on workdir."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Test",
                workdir=temp_workdir,
                config=config,
            )

            assert result.session_id is not None
            assert str(temp_workdir.resolve()) in result.session_id


# ============================================================================
# Resume Tests
# ============================================================================


class TestClaudeCodeAdapterResume:
    """Tests for the resume method."""

    @pytest.mark.asyncio
    async def test_resume_success(
        self,
        adapter: ClaudeCodeAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test successful session resume."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Task continued", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.resume(
                session_id=str(temp_workdir),
                new_prompt="Continue the task",
            )

            assert result.success is True
            assert result.output == "Task continued"

    @pytest.mark.asyncio
    async def test_resume_invalid_session(self, adapter: ClaudeCodeAdapter) -> None:
        """Test resume with non-existent session directory."""
        result = await adapter.resume(
            session_id="/nonexistent/path",
            new_prompt="Continue",
        )

        assert result.status == ExecutionStatus.ERROR
        assert "does not exist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_resume_includes_resume_flag(
        self,
        adapter: ClaudeCodeAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test that resume command includes -r flag."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await adapter.resume(
                session_id=str(temp_workdir),
                new_prompt="Continue",
            )

            call_args = mock_exec.call_args[0]
            assert "-r" in call_args
            assert str(temp_workdir) in call_args


# ============================================================================
# Health Check Tests
# ============================================================================


class TestClaudeCodeAdapterHealthCheck:
    """Tests for the check_health method."""

    @pytest.mark.asyncio
    async def test_check_health_available(self, adapter: ClaudeCodeAdapter) -> None:
        """Test health check when CLI is available."""
        with patch("shutil.which", return_value="/usr/bin/claude"):
            result = await adapter.check_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_health_not_available(self, adapter: ClaudeCodeAdapter) -> None:
        """Test health check when CLI is not available."""
        with patch("shutil.which", return_value=None):
            result = await adapter.check_health()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_health_custom_command(
        self, custom_adapter: ClaudeCodeAdapter
    ) -> None:
        """Test health check uses custom command."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/claude-custom"
            result = await custom_adapter.check_health()

            mock_which.assert_called_with("claude-custom")
            assert result is True


# ============================================================================
# Representation Tests
# ============================================================================


class TestClaudeCodeAdapterRepr:
    """Tests for string representation."""

    def test_repr(self, adapter: ClaudeCodeAdapter) -> None:
        """Test __repr__ includes key information."""
        repr_str = repr(adapter)

        assert "ClaudeCodeAdapter" in repr_str
        assert "claude" in repr_str
        assert "native" in repr_str

    def test_name_property(self, adapter: ClaudeCodeAdapter) -> None:
        """Test name property returns lowercase adapter name."""
        assert adapter.name == "claudecode"


# ============================================================================
# Config Default Handling Tests
# ============================================================================


class TestClaudeCodeAdapterConfigDefaults:
    """Tests for config default value handling."""

    @pytest.mark.asyncio
    async def test_execute_uses_config_command(
        self,
        adapter: ClaudeCodeAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test that execute uses command from config when provided."""
        config = AgentConfig(command="claude-from-config")
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
            assert "claude-from-config" in call_args

    @pytest.mark.asyncio
    async def test_execute_sets_default_command_if_missing(
        self,
        adapter: ClaudeCodeAdapter,
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
            assert config.command == "claude"
            call_args = mock_exec.call_args[0]
            assert "claude" in call_args
