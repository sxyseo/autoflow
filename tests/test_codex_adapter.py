"""
Unit Tests for Codex Adapter

Tests the CodexAdapter class for integration with OpenAI's
Codex CLI tool. Uses mocking to avoid requiring actual CLI
installation during tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.agents.base import (
    AgentConfig,
    ExecutionStatus,
    ResumeMode,
)
from autoflow.agents.codex import CodexAdapter

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def adapter() -> CodexAdapter:
    """Create a basic CodexAdapter instance for testing."""
    return CodexAdapter()


@pytest.fixture
def custom_adapter() -> CodexAdapter:
    """Create a CodexAdapter with custom settings."""
    return CodexAdapter(
        command="codex-custom",
        default_args=["exec", "--json", "--verbose"],
        default_timeout=600,
        approval_policy="suggest",
        sandbox_mode="read-only",
    )


@pytest.fixture
def config() -> AgentConfig:
    """Create a basic AgentConfig for testing."""
    return AgentConfig(
        command="codex",
        args=["exec", "--json"],
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


class TestCodexAdapterInit:
    """Tests for CodexAdapter initialization."""

    def test_init_defaults(self, adapter: CodexAdapter) -> None:
        """Test adapter initialization with default values."""
        assert adapter._command == "codex"
        assert adapter._default_args == ["exec", "--json"]
        assert adapter._default_timeout == 300
        assert adapter._approval_policy == "never"
        assert adapter._sandbox_mode == "full-access"
        assert adapter._session_context == {}

    def test_init_custom_values(self, custom_adapter: CodexAdapter) -> None:
        """Test adapter initialization with custom values."""
        assert custom_adapter._command == "codex-custom"
        assert custom_adapter._default_args == ["exec", "--json", "--verbose"]
        assert custom_adapter._default_timeout == 600
        assert custom_adapter._approval_policy == "suggest"
        assert custom_adapter._sandbox_mode == "read-only"

    def test_init_partial_custom(self) -> None:
        """Test adapter initialization with partial custom values."""
        adapter = CodexAdapter(command="my-codex", default_timeout=120)
        assert adapter._command == "my-codex"
        assert adapter._default_args == ["exec", "--json"]
        assert adapter._default_timeout == 120


# ============================================================================
# Resume Mode Tests
# ============================================================================


class TestCodexAdapterResumeMode:
    """Tests for resume mode handling."""

    def test_get_resume_mode(self, adapter: CodexAdapter) -> None:
        """Test that Codex uses REPROMPT resume mode."""
        assert adapter.get_resume_mode() == ResumeMode.REPROMPT

    def test_supports_resume(self, adapter: CodexAdapter) -> None:
        """Test that adapter supports resume (REPROMPT is supported)."""
        assert adapter.supports_resume() is True


# ============================================================================
# Command Building Tests
# ============================================================================


class TestCodexAdapterBuildCommand:
    """Tests for command building."""

    def test_build_command_basic(
        self, adapter: CodexAdapter, config: AgentConfig
    ) -> None:
        """Test building a basic command."""
        cmd = adapter._build_command("Fix the bug", config)

        assert cmd[0] == "codex"
        assert "exec" in cmd
        assert "--json" in cmd
        assert "Fix the bug" in cmd

    def test_build_command_with_approval_policy(
        self, adapter: CodexAdapter, config: AgentConfig
    ) -> None:
        """Test building a command with approval policy."""
        config.metadata["approval_policy"] = "suggest"
        cmd = adapter._build_command("Test prompt", config)

        assert "--approval-policy" in cmd
        assert "suggest" in cmd

    def test_build_command_with_sandbox_mode(
        self, adapter: CodexAdapter, config: AgentConfig
    ) -> None:
        """Test building a command with sandbox mode."""
        config.metadata["sandbox_mode"] = "read-only"
        cmd = adapter._build_command("Test prompt", config)

        assert "--sandbox" in cmd
        assert "read-only" in cmd

    def test_build_command_with_custom_args(self, adapter: CodexAdapter) -> None:
        """Test building a command with custom args from config."""
        config = AgentConfig(
            command="codex",
            args=["exec", "--json", "--quiet"],
        )
        cmd = adapter._build_command("Test prompt", config)

        assert "--quiet" in cmd


# ============================================================================
# JSON Parsing Tests
# ============================================================================


class TestCodexAdapterJsonParsing:
    """Tests for JSON output parsing."""

    def test_parse_json_output_valid(self, adapter: CodexAdapter) -> None:
        """Test parsing valid JSON output."""
        json_str = '{"status": "success", "result": "done"}'
        result = adapter._parse_json_output(json_str)

        assert result == {"status": "success", "result": "done"}

    def test_parse_json_output_empty(self, adapter: CodexAdapter) -> None:
        """Test parsing empty output."""
        result = adapter._parse_json_output(None)
        assert result == {}

        result = adapter._parse_json_output("")
        assert result == {}

    def test_parse_json_output_invalid(self, adapter: CodexAdapter) -> None:
        """Test parsing invalid JSON returns raw output."""
        invalid_json = "This is not JSON"
        result = adapter._parse_json_output(invalid_json)

        assert result == {"raw_output": "This is not JSON"}


# ============================================================================
# Execute Tests
# ============================================================================


class TestCodexAdapterExecute:
    """Tests for the execute method."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        adapter: CodexAdapter,
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
        adapter: CodexAdapter,
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
        adapter: CodexAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test execution timeout handling."""
        mock_process = AsyncMock()
        mock_process.communicate.side_effect = TimeoutError()
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
        adapter: CodexAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test handling when command is not found."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
            result = await adapter.execute(
                prompt="Fix the bug",
                workdir=temp_workdir,
                config=config,
            )

            assert result.status == ExecutionStatus.ERROR
            assert result.exit_code == -1
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_stores_session_context(
        self,
        adapter: CodexAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test that execute stores session context for reprompt resume."""
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
            assert result.session_id in adapter._session_context
            context = adapter._session_context[result.session_id]
            assert context["prompt"] == "Test prompt"

    @pytest.mark.asyncio
    async def test_execute_parses_json_output(
        self,
        adapter: CodexAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test that execute parses JSON output when available."""
        json_output = {"status": "done", "files_changed": 3}
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
        adapter: CodexAdapter,
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


class TestCodexAdapterResume:
    """Tests for the resume method."""

    @pytest.mark.asyncio
    async def test_resume_success(
        self,
        adapter: CodexAdapter,
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
    async def test_resume_invalid_session(self, adapter: CodexAdapter) -> None:
        """Test resume with non-existent session directory."""
        result = await adapter.resume(
            session_id="/nonexistent/path",
            new_prompt="Continue",
        )

        assert result.status == ExecutionStatus.ERROR
        assert "does not exist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_resume_combines_prompts(
        self,
        adapter: CodexAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test that resume combines original prompt with new prompt."""
        # First execute to store context
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await adapter.execute(
                prompt="Original task",
                workdir=temp_workdir,
                config=config,
            )

            # Now resume
            await adapter.resume(
                session_id=str(temp_workdir),
                new_prompt="New task",
            )

            # Check that context was combined
            context = adapter._session_context.get(str(temp_workdir.resolve()))
            assert context is not None
            assert "Original task" in context["prompt"]
            assert "New task" in context["prompt"]

    @pytest.mark.asyncio
    async def test_resume_without_stored_context(
        self,
        adapter: CodexAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test resume when no stored context exists (starts fresh)."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.resume(
                session_id=str(temp_workdir),
                new_prompt="New task",
            )

            # Should still work, just with the new prompt only
            assert result.success is True


# ============================================================================
# Health Check Tests
# ============================================================================


class TestCodexAdapterHealthCheck:
    """Tests for the check_health method."""

    @pytest.mark.asyncio
    async def test_check_health_available(self, adapter: CodexAdapter) -> None:
        """Test health check when CLI is available."""
        with patch("shutil.which", return_value="/usr/bin/codex"):
            result = await adapter.check_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_health_not_available(self, adapter: CodexAdapter) -> None:
        """Test health check when CLI is not available."""
        with patch("shutil.which", return_value=None):
            result = await adapter.check_health()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_health_custom_command(
        self, custom_adapter: CodexAdapter
    ) -> None:
        """Test health check uses custom command."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/codex-custom"
            result = await custom_adapter.check_health()

            mock_which.assert_called_with("codex-custom")
            assert result is True


# ============================================================================
# Cleanup Tests
# ============================================================================


class TestCodexAdapterCleanup:
    """Tests for the cleanup method."""

    @pytest.mark.asyncio
    async def test_cleanup_specific_session(
        self,
        adapter: CodexAdapter,
        config: AgentConfig,
        temp_workdir: Path,
    ) -> None:
        """Test cleanup of a specific session."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute(
                prompt="Test",
                workdir=temp_workdir,
                config=config,
            )

            session_id = result.session_id
            assert session_id in adapter._session_context

            await adapter.cleanup(session_id)
            assert session_id not in adapter._session_context

    @pytest.mark.asyncio
    async def test_cleanup_all_sessions(
        self,
        adapter: CodexAdapter,
        config: AgentConfig,
        tmp_path: Path,
    ) -> None:
        """Test cleanup of all sessions."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Done", b"")
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
            await adapter.execute(
                prompt="Test2",
                workdir=workdir2,
                config=config,
            )

        assert len(adapter._session_context) >= 2

        await adapter.cleanup()
        assert len(adapter._session_context) == 0


# ============================================================================
# Representation Tests
# ============================================================================


class TestCodexAdapterRepr:
    """Tests for string representation."""

    def test_repr(self, adapter: CodexAdapter) -> None:
        """Test __repr__ includes key information."""
        repr_str = repr(adapter)

        assert "CodexAdapter" in repr_str
        assert "codex" in repr_str
        assert "reprompt" in repr_str

    def test_name_property(self, adapter: CodexAdapter) -> None:
        """Test name property returns lowercase adapter name."""
        assert adapter.name == "codex"


# ============================================================================
# Config Default Handling Tests
# ============================================================================


class TestCodexAdapterConfigDefaults:
    """Tests for config default value handling."""

    @pytest.mark.asyncio
    async def test_execute_uses_config_command(
        self,
        adapter: CodexAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test that execute uses command from config when provided."""
        config = AgentConfig(command="codex-from-config")
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
            assert "codex-from-config" in call_args

    @pytest.mark.asyncio
    async def test_execute_sets_default_command_if_missing(
        self,
        adapter: CodexAdapter,
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
            assert config.command == "codex"
            call_args = mock_exec.call_args[0]
            assert "codex" in call_args

    @pytest.mark.asyncio
    async def test_execute_uses_metadata_approval_policy(
        self,
        adapter: CodexAdapter,
        temp_workdir: Path,
    ) -> None:
        """Test that execute uses approval_policy from metadata."""
        config = AgentConfig(
            command="codex",
            metadata={"approval_policy": "always"},
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
            assert "--approval-policy" in call_args
            assert "always" in call_args
