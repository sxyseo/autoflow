"""
Integration Tests for Tmux Session Management

Tests the TmuxSession and TmuxManager classes for managing
tmux sessions for autonomous agent execution.

These tests mock the actual tmux commands to avoid requiring
tmux to be installed in the test environment.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.tmux import (
    ManagerStats,
    SessionInfo,
    SessionStatus,
    TmuxManager,
    TmuxManagerError,
    TmuxSession,
    TmuxSessionError,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_tmux_available() -> MagicMock:
    """Mock shutil.which to return tmux path."""
    with patch("autoflow.tmux.session.shutil.which") as mock:
        mock.return_value = "/usr/bin/tmux"
        yield mock


@pytest.fixture
def mock_tmux_not_available() -> MagicMock:
    """Mock shutil.which to return None (tmux not installed)."""
    with patch("autoflow.tmux.session.shutil.which") as mock:
        mock.return_value = None
        yield mock


@pytest.fixture
def mock_async_subprocess() -> MagicMock:
    """Mock asyncio subprocess creation."""
    with patch("autoflow.tmux.session.asyncio.create_subprocess_exec") as mock:
        yield mock


@pytest.fixture
def temp_workdir(tmp_path: Path) -> Path:
    """Create a temporary working directory for tests."""
    workdir = tmp_path / "test_project"
    workdir.mkdir()
    return workdir


@pytest.fixture
def manager() -> TmuxManager:
    """Create a TmuxManager instance for testing."""
    return TmuxManager(max_concurrent=5)


# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_process(
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> MagicMock:
    """Create a mock subprocess process."""
    process = MagicMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.kill = MagicMock()
    process.wait = AsyncMock()
    return process


# ============================================================================
# TmuxSession Tests
# ============================================================================


class TestTmuxSessionInit:
    """Tests for TmuxSession initialization."""

    def test_session_init_basic(self, temp_workdir: Path) -> None:
        """Test basic session initialization."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        assert session.name == "test-agent"
        assert session.workdir == temp_workdir
        assert session.status == SessionStatus.CREATED
        assert session.session_id.startswith("autoflow-test-agent-")

    def test_session_init_custom_id(self, temp_workdir: Path) -> None:
        """Test session with custom ID."""
        session = TmuxSession(
            name="test-agent",
            workdir=temp_workdir,
            session_id="custom-session-id",
        )

        assert session.session_id == "custom-session-id"

    def test_session_init_with_env(self, temp_workdir: Path) -> None:
        """Test session with environment variables."""
        env = {"FOO": "bar", "BAZ": "qux"}
        session = TmuxSession(
            name="test-agent",
            workdir=temp_workdir,
            env=env,
        )

        assert session._env == env

    def test_session_id_sanitization(self, temp_workdir: Path) -> None:
        """Test that special characters in name are sanitized."""
        session = TmuxSession(
            name="test agent!@#$%",
            workdir=temp_workdir,
        )

        assert "autoflow-test-agent-" in session.session_id
        # Should not contain special characters except hyphens
        session_name_part = session.session_id.split("-")[1:3]
        for part in session_name_part:
            assert part.isalnum() or part == ""

    def test_session_info_property(self, temp_workdir: Path) -> None:
        """Test session info property."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        info = session.info

        assert isinstance(info, SessionInfo)
        assert info.session_id == session.session_id
        assert info.name == "test-agent"
        assert info.status == SessionStatus.CREATED


class TestTmuxSessionStart:
    """Tests for TmuxSession.start() method."""

    @pytest.mark.asyncio
    async def test_start_tmux_not_available(
        self,
        temp_workdir: Path,
        mock_tmux_not_available: MagicMock,
    ) -> None:
        """Test start fails when tmux is not available."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        with pytest.raises(TmuxSessionError) as exc_info:
            await session.start()

        assert "tmux is not available" in str(exc_info.value)
        assert session.status == SessionStatus.ERROR

    @pytest.mark.asyncio
    async def test_start_workdir_not_exists(
        self,
        temp_workdir: Path,
        mock_tmux_available: MagicMock,
    ) -> None:
        """Test start fails when working directory doesn't exist."""
        non_existent = temp_workdir / "nonexistent"
        session = TmuxSession(name="test-agent", workdir=non_existent)

        with pytest.raises(FileNotFoundError):
            await session.start()

    @pytest.mark.asyncio
    async def test_start_success(
        self,
        temp_workdir: Path,
        mock_tmux_available: MagicMock,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test successful session start."""
        # Mock session_exists to return False (new session)
        # Mock the new-session command to succeed
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        with patch.object(
            TmuxSession,
            "session_exists",
            return_value=False,
        ):
            await session.start()

        assert session.status == SessionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_already_exists(
        self,
        temp_workdir: Path,
        mock_tmux_available: MagicMock,
    ) -> None:
        """Test start when session already exists."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        with patch.object(
            TmuxSession,
            "session_exists",
            return_value=True,
        ):
            await session.start()

        assert session.status == SessionStatus.RUNNING


class TestTmuxSessionCommands:
    """Tests for TmuxSession command methods."""

    @pytest.mark.asyncio
    async def test_send_command_not_running(self, temp_workdir: Path) -> None:
        """Test send_command fails when session not running."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        with pytest.raises(TmuxSessionError) as exc_info:
            await session.send_command("echo hello")

        assert "not running" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_command_success(
        self,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test successful command send."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        # Should not raise
        await session.send_command("echo hello")

    @pytest.mark.asyncio
    async def test_send_keys_not_running(self, temp_workdir: Path) -> None:
        """Test send_keys fails when session not running."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        with pytest.raises(TmuxSessionError):
            await session.send_keys("C-c")

    @pytest.mark.asyncio
    async def test_send_keys_success(
        self,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test successful key send."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        # Should not raise
        await session.send_keys("C-c")


class TestTmuxSessionOutput:
    """Tests for TmuxSession output capture methods."""

    @pytest.mark.asyncio
    async def test_capture_output_not_running(self, temp_workdir: Path) -> None:
        """Test capture_output fails when session not running."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        with pytest.raises(TmuxSessionError):
            await session.capture_output()

    @pytest.mark.asyncio
    async def test_capture_output_success(
        self,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test successful output capture."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        expected_output = b"Hello, World!\nTest output"
        mock_process = create_mock_process(returncode=0, stdout=expected_output)
        mock_async_subprocess.return_value = mock_process

        output = await session.capture_output()

        assert "Hello, World!" in output

    @pytest.mark.asyncio
    async def test_capture_pane_not_running(self, temp_workdir: Path) -> None:
        """Test capture_pane fails when session not running."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        with pytest.raises(TmuxSessionError):
            await session.capture_pane()

    @pytest.mark.asyncio
    async def test_capture_pane_success(
        self,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test successful pane capture."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        expected_output = b"Pane content"
        mock_process = create_mock_process(returncode=0, stdout=expected_output)
        mock_async_subprocess.return_value = mock_process

        output = await session.capture_pane(start_line=-100, end_line=-1)

        assert "Pane content" in output


class TestTmuxSessionLifecycle:
    """Tests for TmuxSession lifecycle methods."""

    @pytest.mark.asyncio
    async def test_kill_stopped_session(self, temp_workdir: Path) -> None:
        """Test kill on already stopped session."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.STOPPED

        # Should not raise, should be no-op
        await session.kill()

        assert session.status == SessionStatus.STOPPED

    @pytest.mark.asyncio
    async def test_kill_running_session(
        self,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test kill on running session."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        await session.kill()

        assert session.status == SessionStatus.STOPPED

    @pytest.mark.asyncio
    async def test_is_alive_not_running(self, temp_workdir: Path) -> None:
        """Test is_alive returns False when not running."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        assert await session.is_alive() is False

    @pytest.mark.asyncio
    async def test_is_alive_running(
        self,
        temp_workdir: Path,
    ) -> None:
        """Test is_alive when session is running."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        with patch.object(
            TmuxSession,
            "session_exists",
            return_value=True,
        ):
            assert await session.is_alive() is True

    @pytest.mark.asyncio
    async def test_context_manager(
        self,
        temp_workdir: Path,
        mock_tmux_available: MagicMock,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test async context manager usage."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        with patch.object(TmuxSession, "session_exists", return_value=False):
            async with TmuxSession(name="test-agent", workdir=temp_workdir) as session:
                assert session.status == SessionStatus.RUNNING

            # After context exit, should be stopped
            assert session.status == SessionStatus.STOPPED


class TestTmuxSessionWaitForOutput:
    """Tests for TmuxSession.wait_for_output method."""

    @pytest.mark.asyncio
    async def test_wait_for_output_not_running(self, temp_workdir: Path) -> None:
        """Test wait_for_output fails when session not running."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        with pytest.raises(TmuxSessionError):
            await session.wait_for_output("pattern")

    @pytest.mark.asyncio
    async def test_wait_for_output_immediate_match(
        self,
        temp_workdir: Path,
    ) -> None:
        """Test wait_for_output finds pattern immediately."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        with patch.object(
            session,
            "capture_output",
            return_value="Output with pattern here",
        ):
            result = await session.wait_for_output("pattern", timeout=1.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_output_timeout(
        self,
        temp_workdir: Path,
    ) -> None:
        """Test wait_for_output times out."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        with patch.object(
            session,
            "capture_output",
            return_value="Output without the pattern",
        ):
            result = await session.wait_for_output("notfound", timeout=0.2)

        assert result is False


class TestTmuxSessionClassMethods:
    """Tests for TmuxSession class methods."""

    @pytest.mark.asyncio
    async def test_check_tmux_available_true(
        self,
        mock_tmux_available: MagicMock,
    ) -> None:
        """Test check_tmux_available returns True when installed."""
        result = await TmuxSession.check_tmux_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_tmux_available_false(
        self,
        mock_tmux_not_available: MagicMock,
    ) -> None:
        """Test check_tmux_available returns False when not installed."""
        result = await TmuxSession.check_tmux_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_list_sessions(
        self,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test list_sessions returns session list."""
        sessions_output = b"autoflow-agent-1\nautoflow-agent-2\nother-session"
        mock_process = create_mock_process(returncode=0, stdout=sessions_output)
        mock_async_subprocess.return_value = mock_process

        sessions = await TmuxSession.list_sessions()

        assert len(sessions) == 3
        assert "autoflow-agent-1" in sessions

    @pytest.mark.asyncio
    async def test_list_sessions_with_prefix(
        self,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test list_sessions filters by prefix."""
        sessions_output = b"autoflow-agent-1\nautoflow-agent-2\nother-session"
        mock_process = create_mock_process(returncode=0, stdout=sessions_output)
        mock_async_subprocess.return_value = mock_process

        sessions = await TmuxSession.list_sessions(prefix="autoflow")

        assert len(sessions) == 2
        assert all(s.startswith("autoflow") for s in sessions)

    @pytest.mark.asyncio
    async def test_session_exists_true(
        self,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test session_exists returns True for existing session."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        result = await TmuxSession.session_exists("test-session")

        assert result is True

    @pytest.mark.asyncio
    async def test_session_exists_false(
        self,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test session_exists returns False for non-existing session."""
        mock_process = create_mock_process(returncode=1)
        mock_async_subprocess.return_value = mock_process

        result = await TmuxSession.session_exists("nonexistent")

        assert result is False


# ============================================================================
# TmuxManager Tests
# ============================================================================


class TestTmuxManagerInit:
    """Tests for TmuxManager initialization."""

    def test_manager_init_default(self) -> None:
        """Test manager with default settings."""
        manager = TmuxManager()

        assert manager.prefix == "autoflow"
        assert manager.max_concurrent == 10
        assert len(manager.sessions) == 0

    def test_manager_init_custom(self) -> None:
        """Test manager with custom settings."""
        manager = TmuxManager(
            prefix="custom",
            max_concurrent=5,
            session_timeout=1800.0,
        )

        assert manager.prefix == "custom"
        assert manager.max_concurrent == 5
        assert manager.session_timeout == 1800.0

    def test_manager_stats_property(self, manager: TmuxManager) -> None:
        """Test manager stats property."""
        stats = manager.stats

        assert isinstance(stats, ManagerStats)
        assert stats.total_sessions == 0
        assert stats.active_sessions == 0


class TestTmuxManagerCreateSession:
    """Tests for TmuxManager.create_session method."""

    @pytest.mark.asyncio
    async def test_create_session_success(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
        mock_tmux_available: MagicMock,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test successful session creation."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        with patch.object(TmuxSession, "session_exists", return_value=False):
            session = await manager.create_session(
                name="test-agent",
                workdir=temp_workdir,
            )

        assert session is not None
        assert session.name == "test-agent"
        assert session.status == SessionStatus.RUNNING
        assert len(manager.sessions) == 1

    @pytest.mark.asyncio
    async def test_create_session_max_concurrent(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test session limit enforcement."""
        # Create sessions up to the limit
        for i in range(manager.max_concurrent):
            session = TmuxSession(name=f"agent-{i}", workdir=temp_workdir)
            session._status = SessionStatus.RUNNING
            manager._sessions[session.session_id] = session

        # Next creation should fail
        with pytest.raises(TmuxManagerError) as exc_info:
            await manager.create_session(
                name="overflow-agent",
                workdir=temp_workdir,
            )

        assert "Maximum concurrent sessions" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_session_with_metadata(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
        mock_tmux_available: MagicMock,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test session creation with metadata."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        metadata = {"agent_type": "claude", "task_id": "task-123"}

        with patch.object(TmuxSession, "session_exists", return_value=False):
            session = await manager.create_session(
                name="test-agent",
                workdir=temp_workdir,
                metadata=metadata,
            )

        assert manager.get_session_metadata(session.session_id) == metadata

    @pytest.mark.asyncio
    async def test_create_session_auto_start_false(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test session creation without auto-start."""
        session = await manager.create_session(
            name="test-agent",
            workdir=temp_workdir,
            auto_start=False,
        )

        assert session.status == SessionStatus.CREATED


class TestTmuxManagerGetSession:
    """Tests for TmuxManager get session methods."""

    @pytest.mark.asyncio
    async def test_get_session_by_id(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test get_session returns correct session."""
        session = await manager.create_session(
            name="test-agent",
            workdir=temp_workdir,
            auto_start=False,
        )

        retrieved = await manager.get_session(session.session_id)

        assert retrieved is session

    @pytest.mark.asyncio
    async def test_get_session_not_found(
        self,
        manager: TmuxManager,
    ) -> None:
        """Test get_session returns None for unknown ID."""
        retrieved = await manager.get_session("nonexistent-id")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_session_by_name(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test get_session_by_name returns correct session."""
        session = await manager.create_session(
            name="unique-agent-name",
            workdir=temp_workdir,
            auto_start=False,
        )

        retrieved = await manager.get_session_by_name("unique-agent-name")

        assert retrieved is session

    @pytest.mark.asyncio
    async def test_get_session_by_name_not_found(
        self,
        manager: TmuxManager,
    ) -> None:
        """Test get_session_by_name returns None for unknown name."""
        retrieved = await manager.get_session_by_name("nonexistent")

        assert retrieved is None


class TestTmuxManagerListSessions:
    """Tests for TmuxManager list sessions methods."""

    @pytest.mark.asyncio
    async def test_list_sessions_all(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test list_sessions returns all sessions."""
        await manager.create_session("agent-1", temp_workdir, auto_start=False)
        await manager.create_session("agent-2", temp_workdir, auto_start=False)

        sessions = await manager.list_sessions()

        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_filter_by_status(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test list_sessions filters by status."""
        await manager.create_session("agent-1", temp_workdir, auto_start=False)
        session2 = await manager.create_session(
            "agent-2", temp_workdir, auto_start=False
        )
        session2._status = SessionStatus.STOPPED

        running = await manager.list_sessions(status=SessionStatus.RUNNING)
        stopped = await manager.list_sessions(status=SessionStatus.STOPPED)

        assert len(running) == 0
        assert len(stopped) == 1

    @pytest.mark.asyncio
    async def test_list_sessions_filter_by_prefix(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test list_sessions filters by prefix."""
        await manager.create_session(
            "agent-1",
            temp_workdir,
            session_id="prefix-a-session",
            auto_start=False,
        )
        await manager.create_session(
            "agent-2",
            temp_workdir,
            session_id="other-b-session",
            auto_start=False,
        )

        filtered = await manager.list_sessions(prefix="prefix")

        assert len(filtered) == 1
        assert filtered[0].session_id == "prefix-a-session"

    @pytest.mark.asyncio
    async def test_list_session_infos(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test list_session_infos returns SessionInfo objects."""
        await manager.create_session("agent-1", temp_workdir, auto_start=False)

        infos = await manager.list_session_infos()

        assert len(infos) == 1
        assert isinstance(infos[0], SessionInfo)


class TestTmuxManagerKillSession:
    """Tests for TmuxManager kill session methods."""

    @pytest.mark.asyncio
    async def test_kill_session(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test kill_session removes session."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        session = await manager.create_session(
            "test-agent",
            temp_workdir,
            auto_start=False,
        )
        session._status = SessionStatus.RUNNING

        result = await manager.kill_session(session.session_id)

        assert result is True
        assert session.session_id not in manager.sessions

    @pytest.mark.asyncio
    async def test_kill_session_not_found(
        self,
        manager: TmuxManager,
    ) -> None:
        """Test kill_session returns False for unknown session."""
        result = await manager.kill_session("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_kill_sessions_by_prefix(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test kill_sessions_by_prefix removes matching sessions."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        await manager.create_session(
            "agent-1",
            temp_workdir,
            session_id="prefix-session-1",
            auto_start=False,
        )
        await manager.create_session(
            "agent-2",
            temp_workdir,
            session_id="prefix-session-2",
            auto_start=False,
        )
        await manager.create_session(
            "agent-3",
            temp_workdir,
            session_id="other-session-3",
            auto_start=False,
        )

        # Set all to running so kill will work
        for s in manager._sessions.values():
            s._status = SessionStatus.RUNNING

        count = await manager.kill_sessions_by_prefix("prefix")

        assert count == 2
        assert len(manager.sessions) == 1

    @pytest.mark.asyncio
    async def test_kill_sessions_by_status(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test kill_sessions_by_status removes matching sessions."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        session2 = await manager.create_session(
            "agent-2", temp_workdir, auto_start=False
        )
        session1._status = SessionStatus.STOPPED
        session2._status = SessionStatus.ERROR

        count_stopped = await manager.kill_sessions_by_status(SessionStatus.STOPPED)

        assert count_stopped == 1
        assert len(manager.sessions) == 1


class TestTmuxManagerCleanup:
    """Tests for TmuxManager cleanup methods."""

    @pytest.mark.asyncio
    async def test_cleanup_stopped(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test cleanup_stopped removes stopped sessions."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        await manager.create_session("agent-2", temp_workdir, auto_start=False)
        session1._status = SessionStatus.STOPPED

        count = await manager.cleanup_stopped()

        assert count == 1
        assert len(manager.sessions) == 1

    @pytest.mark.asyncio
    async def test_cleanup_errors(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test cleanup_errors removes error sessions."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        await manager.create_session("agent-2", temp_workdir, auto_start=False)
        session1._status = SessionStatus.ERROR

        count = await manager.cleanup_errors()

        assert count == 1
        assert len(manager.sessions) == 1

    @pytest.mark.asyncio
    async def test_cleanup_all(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test cleanup_all removes all sessions."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        await manager.create_session("agent-1", temp_workdir, auto_start=False)
        await manager.create_session("agent-2", temp_workdir, auto_start=False)

        # Set to running so cleanup will work
        for s in manager._sessions.values():
            s._status = SessionStatus.RUNNING

        count = await manager.cleanup_all()

        assert count == 2
        assert len(manager.sessions) == 0


class TestTmuxManagerHealthCheck:
    """Tests for TmuxManager health check methods."""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test health_check returns all healthy."""
        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        session2 = await manager.create_session(
            "agent-2", temp_workdir, auto_start=False
        )
        session1._status = SessionStatus.RUNNING
        session2._status = SessionStatus.RUNNING

        with patch.object(
            TmuxSession,
            "is_alive",
            return_value=True,
        ):
            health = await manager.health_check()

        assert all(health.values())

    @pytest.mark.asyncio
    async def test_health_check_some_unhealthy(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test health_check detects unhealthy sessions."""
        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        session2 = await manager.create_session(
            "agent-2", temp_workdir, auto_start=False
        )
        session1._status = SessionStatus.RUNNING
        session2._status = SessionStatus.RUNNING

        async def mock_is_alive(self: TmuxSession) -> bool:
            return self.session_id == session1.session_id

        with patch.object(TmuxSession, "is_alive", mock_is_alive):
            health = await manager.health_check()

        assert health[session1.session_id] is True
        assert health[session2.session_id] is False

    @pytest.mark.asyncio
    async def test_get_unhealthy_sessions(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test get_unhealthy_sessions returns only unhealthy."""
        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        session2 = await manager.create_session(
            "agent-2", temp_workdir, auto_start=False
        )
        session1._status = SessionStatus.RUNNING
        session2._status = SessionStatus.STOPPED  # Unhealthy by status

        unhealthy = await manager.get_unhealthy_sessions()

        assert len(unhealthy) == 1
        assert unhealthy[0].session_id == session2.session_id


class TestTmuxManagerBroadcast:
    """Tests for TmuxManager broadcast methods."""

    @pytest.mark.asyncio
    async def test_broadcast_command(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test broadcast_command sends to all running sessions."""
        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        session2 = await manager.create_session(
            "agent-2", temp_workdir, auto_start=False
        )
        session1._status = SessionStatus.RUNNING
        session2._status = SessionStatus.RUNNING

        with patch.object(TmuxSession, "send_command", AsyncMock()):
            results = await manager.broadcast_command("echo hello")

        assert len(results) == 2
        assert all(results.values())

    @pytest.mark.asyncio
    async def test_broadcast_command_with_failures(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test broadcast_command handles failures."""

        async def mock_send(self: TmuxSession, cmd: str) -> None:
            if "fail" in self.name:
                raise TmuxSessionError("Failed")

        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        session2 = await manager.create_session(
            "fail-agent", temp_workdir, auto_start=False
        )
        session1._status = SessionStatus.RUNNING
        session2._status = SessionStatus.RUNNING

        with patch.object(TmuxSession, "send_command", mock_send):
            results = await manager.broadcast_command("echo hello")

        assert results[session1.session_id] is True
        assert results[session2.session_id] is False

    @pytest.mark.asyncio
    async def test_capture_all_outputs(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test capture_all_outputs returns outputs from all sessions."""
        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        session2 = await manager.create_session(
            "agent-2", temp_workdir, auto_start=False
        )
        session1._status = SessionStatus.RUNNING
        session2._status = SessionStatus.RUNNING

        async def mock_capture(self: TmuxSession, lines: int = 1000) -> str:
            return f"Output from {self.name}"

        with patch.object(TmuxSession, "capture_output", mock_capture):
            outputs = await manager.capture_all_outputs()

        assert len(outputs) == 2
        assert "agent-1" in outputs[session1.session_id]
        assert "agent-2" in outputs[session2.session_id]


class TestTmuxManagerMetadata:
    """Tests for TmuxManager metadata methods."""

    @pytest.mark.asyncio
    async def test_set_and_get_metadata(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test setting and getting session metadata."""
        session = await manager.create_session(
            "test-agent",
            temp_workdir,
            auto_start=False,
        )

        result = manager.set_session_metadata(
            session.session_id,
            "task_id",
            "task-123",
        )

        assert result is True
        assert manager.get_session_metadata(session.session_id, "task_id") == "task-123"

    @pytest.mark.asyncio
    async def test_set_metadata_nonexistent_session(
        self,
        manager: TmuxManager,
    ) -> None:
        """Test set_session_metadata returns False for unknown session."""
        result = manager.set_session_metadata(
            "nonexistent",
            "key",
            "value",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_metadata_all(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test getting all metadata for a session."""
        metadata = {"key1": "value1", "key2": "value2"}
        session = await manager.create_session(
            "test-agent",
            temp_workdir,
            metadata=metadata,
            auto_start=False,
        )

        all_metadata = manager.get_session_metadata(session.session_id)

        assert all_metadata == metadata


class TestTmuxManagerOrphanedSessions:
    """Tests for TmuxManager orphaned session handling."""

    @pytest.mark.asyncio
    async def test_discover_orphaned_sessions(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test discover_orphaned_sessions finds untracked sessions."""
        await manager.create_session("agent-1", temp_workdir, auto_start=False)

        with patch.object(
            TmuxSession,
            "list_sessions",
            return_value=["autoflow-agent-1-abc", "autoflow-orphan-xyz"],
        ):
            orphaned = await manager.discover_orphaned_sessions()

        assert "autoflow-orphan-xyz" in orphaned

    @pytest.mark.asyncio
    async def test_adopt_orphaned_session(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test adopt_orphaned_session adopts existing session."""
        with patch.object(TmuxSession, "session_exists", return_value=True):
            session = await manager.adopt_orphaned_session("autoflow-orphan-xyz")

        assert session is not None
        assert session.session_id == "autoflow-orphan-xyz"
        assert session.status == SessionStatus.RUNNING
        assert manager.get_session_metadata(session.session_id, "adopted") is True

    @pytest.mark.asyncio
    async def test_adopt_orphaned_session_not_found(
        self,
        manager: TmuxManager,
    ) -> None:
        """Test adopt_orphaned_session returns None for nonexistent session."""
        with patch.object(TmuxSession, "session_exists", return_value=False):
            session = await manager.adopt_orphaned_session("nonexistent")

        assert session is None


class TestTmuxManagerStats:
    """Tests for TmuxManager statistics."""

    @pytest.mark.asyncio
    async def test_get_stats_summary(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test get_stats_summary returns correct statistics."""
        session1 = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )
        session2 = await manager.create_session(
            "agent-2", temp_workdir, auto_start=False
        )
        session1._status = SessionStatus.RUNNING
        session2._status = SessionStatus.STOPPED

        summary = manager.get_stats_summary()

        assert summary["total_sessions"] == 2
        assert summary["active_sessions"] == 1
        assert summary["stopped_sessions"] == 1
        assert summary["error_sessions"] == 0
        assert summary["max_concurrent"] == 5
        assert summary["available_slots"] == 3

    @pytest.mark.asyncio
    async def test_stats_property_updates(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test stats property reflects current state."""
        session = await manager.create_session(
            "agent-1", temp_workdir, auto_start=False
        )

        assert manager.stats.total_sessions == 1
        assert manager.stats.active_sessions == 0

        session._status = SessionStatus.RUNNING

        assert manager.stats.active_sessions == 1


class TestTmuxManagerContextManager:
    """Tests for TmuxManager async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(
        self,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test context manager cleans up on exit."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        async with TmuxManager() as manager:
            session = await manager.create_session(
                "test-agent",
                temp_workdir,
                auto_start=False,
            )
            session._status = SessionStatus.RUNNING
            assert len(manager.sessions) == 1

        # After context exit, sessions should be cleaned
        assert len(manager.sessions) == 0


class TestTmuxManagerHealthMonitor:
    """Tests for TmuxManager health monitoring."""

    @pytest.mark.asyncio
    async def test_start_stop_health_monitor(
        self,
        manager: TmuxManager,
    ) -> None:
        """Test starting and stopping health monitor."""
        await manager.start_health_monitor()

        assert manager._running is True
        assert manager._health_task is not None

        await manager.stop_health_monitor()

        assert manager._running is False
        assert manager._health_task is None

    @pytest.mark.asyncio
    async def test_health_monitor_detects_dead_sessions(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test health monitor marks dead sessions as error."""
        session = await manager.create_session(
            "test-agent", temp_workdir, auto_start=False
        )
        session._status = SessionStatus.RUNNING

        # Start monitor with very short interval
        manager.health_check_interval = 0.1
        await manager.start_health_monitor()

        # Mock is_alive to return False
        with patch.object(TmuxSession, "is_alive", return_value=False):
            # Wait for at least one health check cycle
            await asyncio.sleep(0.2)

        await manager.stop_health_monitor()

        # Session should be marked as error
        assert session.status == SessionStatus.ERROR


# ============================================================================
# Integration Tests
# ============================================================================


class TestTmuxIntegration:
    """Integration tests for TmuxManager and TmuxSession working together."""

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(
        self,
        temp_workdir: Path,
        mock_tmux_available: MagicMock,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test complete session lifecycle through manager."""
        mock_process = create_mock_process(returncode=0, stdout=b"test output")
        mock_async_subprocess.return_value = mock_process

        async with TmuxManager() as manager:
            # Create session
            with patch.object(TmuxSession, "session_exists", return_value=False):
                session = await manager.create_session(
                    name="integration-test",
                    workdir=temp_workdir,
                    metadata={"test": True},
                )

            assert session.status == SessionStatus.RUNNING

            # Send command
            await session.send_command("echo 'Integration test'")

            # Capture output
            output = await session.capture_output()
            assert "test output" in output

            # Check health
            health = await manager.health_check()
            assert health[session.session_id] is True

        # After context exit, session should be stopped
        assert session.status == SessionStatus.STOPPED

    @pytest.mark.asyncio
    async def test_multiple_sessions_parallel(
        self,
        temp_workdir: Path,
        mock_tmux_available: MagicMock,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test managing multiple sessions in parallel."""
        mock_process = create_mock_process(returncode=0)
        mock_async_subprocess.return_value = mock_process

        manager = TmuxManager(max_concurrent=3)

        try:
            # Create multiple sessions
            with patch.object(TmuxSession, "session_exists", return_value=False):
                sessions = await asyncio.gather(
                    manager.create_session("agent-1", temp_workdir),
                    manager.create_session("agent-2", temp_workdir),
                    manager.create_session("agent-3", temp_workdir),
                )

            assert len(sessions) == 3
            assert len(manager.sessions) == 3

            # Verify all are tracked
            for session in sessions:
                assert await manager.get_session(session.session_id) is session

            # Check stats
            stats = manager.stats
            assert stats.total_sessions == 3
            assert stats.active_sessions == 3

        finally:
            await manager.cleanup_all()

    @pytest.mark.asyncio
    async def test_session_recovery_from_error(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test recovering sessions from error state."""
        # Create session that goes into error state
        session = await manager.create_session(
            "error-agent",
            temp_workdir,
            auto_start=False,
        )
        session._status = SessionStatus.ERROR

        # Cleanup error sessions
        count = await manager.cleanup_errors()

        assert count == 1
        assert len(manager.sessions) == 0

        # Create new session to replace
        new_session = await manager.create_session(
            "replacement-agent",
            temp_workdir,
            auto_start=False,
        )

        assert new_session.status == SessionStatus.CREATED
        assert len(manager.sessions) == 1


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling in tmux management."""

    @pytest.mark.asyncio
    async def test_tmux_command_timeout(
        self,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test handling of tmux command timeout."""
        # Create a process that will timeout
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(side_effect=TimeoutError("Timeout"))
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()
        mock_async_subprocess.return_value = mock_process

        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        with pytest.raises(asyncio.TimeoutError):
            await session.capture_output()

    @pytest.mark.asyncio
    async def test_tmux_command_failure(
        self,
        temp_workdir: Path,
        mock_async_subprocess: MagicMock,
    ) -> None:
        """Test handling of tmux command failure."""
        mock_process = create_mock_process(
            returncode=1,
            stderr=b"session not found",
        )
        mock_async_subprocess.return_value = mock_process

        session = TmuxSession(name="test-agent", workdir=temp_workdir)
        session._status = SessionStatus.RUNNING

        with pytest.raises(TmuxSessionError):
            await session.send_command("test command")

    @pytest.mark.asyncio
    async def test_manager_concurrent_modification(
        self,
        manager: TmuxManager,
        temp_workdir: Path,
    ) -> None:
        """Test manager handles concurrent modifications safely."""

        # Create sessions concurrently
        async def create_and_remove(name: str) -> None:
            session = await manager.create_session(name, temp_workdir, auto_start=False)
            await asyncio.sleep(0.01)  # Small delay
            await manager.kill_session(session.session_id)

        # Run multiple concurrent operations
        await asyncio.gather(
            create_and_remove("agent-1"),
            create_and_remove("agent-2"),
            create_and_remove("agent-3"),
        )

        # All sessions should be cleaned up
        assert len(manager.sessions) == 0


# ============================================================================
# Representation Tests
# ============================================================================


class TestStringRepresentations:
    """Tests for string representations of tmux objects."""

    def test_session_repr(self, temp_workdir: Path) -> None:
        """Test TmuxSession __repr__."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        repr_str = repr(session)

        assert "TmuxSession" in repr_str
        assert "test-agent" in repr_str
        assert session.session_id in repr_str

    def test_session_str(self, temp_workdir: Path) -> None:
        """Test TmuxSession __str__."""
        session = TmuxSession(name="test-agent", workdir=temp_workdir)

        str_repr = str(session)

        assert "test-agent" in str_repr
        assert session.session_id in str_repr
        assert "created" in str_repr

    def test_manager_repr(self, manager: TmuxManager) -> None:
        """Test TmuxManager __repr__."""
        repr_str = repr(manager)

        assert "TmuxManager" in repr_str
        assert "sessions=0" in repr_str
        assert "max=5" in repr_str

    def test_manager_str(self, manager: TmuxManager) -> None:
        """Test TmuxManager __str__."""
        str_repr = str(manager)

        assert "Tmux Manager" in str_repr
        assert "0/5" in str_repr
