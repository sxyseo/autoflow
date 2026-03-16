"""
Autoflow Tmux Manager Module

Provides multi-session coordination for managing multiple tmux sessions
running AI agents concurrently. This enables parallel agent execution
with centralized monitoring and resource management.

Usage:
    from autoflow.tmux.manager import TmuxManager

    # Create manager
    manager = TmuxManager()

    # Create sessions
    session1 = await manager.create_session("agent-1", "/path/to/project")
    session2 = await manager.create_session("agent-2", "/path/to/project")

    # List all sessions
    sessions = await manager.list_sessions()

    # Clean up all sessions
    await manager.cleanup_all()
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from autoflow.tmux.session import (
    SessionInfo,
    SessionStatus,
    TmuxSession,
    TmuxSessionError,
)


class ManagerStats(BaseModel):
    """Statistics about the tmux manager."""

    total_sessions: int = 0
    active_sessions: int = 0
    stopped_sessions: int = 0
    error_sessions: int = 0
    max_concurrent: int = 10
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TmuxManagerError(Exception):
    """Exception raised for tmux manager errors."""

    def __init__(self, message: str, session_id: str | None = None):
        self.session_id = session_id
        super().__init__(message)


class TmuxManager:
    """
    Manages multiple tmux sessions for parallel agent execution.

    This class provides:
    - Centralized session creation and tracking
    - Session health monitoring
    - Resource limits (max concurrent sessions)
    - Bulk operations (cleanup all, list all)
    - Session grouping by labels/tags

    The manager maintains a registry of active sessions and provides
    convenient methods for batch operations.

    Attributes:
        prefix: Prefix for all managed session IDs
        max_concurrent: Maximum number of concurrent sessions
        sessions: Dictionary of tracked sessions

    Example:
        >>> manager = TmuxManager(max_concurrent=5)
        >>> session = await manager.create_session("worker-1", "/project")
        >>> await session.send_command("claude --print 'Hello'")
        >>> stats = manager.get_stats()
        >>> await manager.cleanup_all()
    """

    # Default prefix for managed sessions
    DEFAULT_PREFIX: str = "autoflow"

    def __init__(
        self,
        prefix: str = DEFAULT_PREFIX,
        max_concurrent: int = 10,
        session_timeout: float = 3600.0,
        health_check_interval: float = 60.0,
    ) -> None:
        """
        Initialize the tmux session manager.

        Args:
            prefix: Prefix for all managed session IDs
            max_concurrent: Maximum number of concurrent sessions allowed
            session_timeout: Default timeout for session operations (seconds)
            health_check_interval: Interval between health checks (seconds)
        """
        self.prefix = prefix
        self.max_concurrent = max_concurrent
        self.session_timeout = session_timeout
        self.health_check_interval = health_check_interval

        # Session registry
        self._sessions: dict[str, TmuxSession] = {}
        self._session_metadata: dict[str, dict[str, Any]] = {}

        # Stats tracking
        self._stats = ManagerStats(max_concurrent=max_concurrent)
        self._created_at = datetime.utcnow()

        # Health monitoring task
        self._health_task: asyncio.Task | None = None
        self._running = False

    @property
    def sessions(self) -> dict[str, TmuxSession]:
        """Get the dictionary of tracked sessions."""
        return self._sessions.copy()

    @property
    def stats(self) -> ManagerStats:
        """Get current manager statistics."""
        self._update_stats()
        return self._stats

    def _update_stats(self) -> None:
        """Update manager statistics."""
        total = len(self._sessions)
        active = sum(
            1 for s in self._sessions.values() if s.status == SessionStatus.RUNNING
        )
        stopped = sum(
            1 for s in self._sessions.values() if s.status == SessionStatus.STOPPED
        )
        error = sum(
            1 for s in self._sessions.values() if s.status == SessionStatus.ERROR
        )

        self._stats.total_sessions = total
        self._stats.active_sessions = active
        self._stats.stopped_sessions = stopped
        self._stats.error_sessions = error

    @staticmethod
    async def check_tmux_available() -> bool:
        """
        Check if tmux is available on the system.

        Returns:
            True if tmux is installed and accessible
        """
        return shutil.which("tmux") is not None

    async def create_session(
        self,
        name: str,
        workdir: str | Path,
        session_id: str | None = None,
        shell: str = "/bin/bash",
        env: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        auto_start: bool = True,
    ) -> TmuxSession:
        """
        Create and register a new tmux session.

        Args:
            name: Human-readable name for the session
            workdir: Working directory for the session
            session_id: Optional explicit session ID
            shell: Shell to use in the session
            env: Environment variables to set
            metadata: Additional metadata for tracking
            auto_start: If True, start the session immediately

        Returns:
            The created TmuxSession

        Raises:
            TmuxManagerError: If max concurrent sessions reached
            TmuxSessionError: If session creation fails
        """
        # Check session limit
        if len(self._sessions) >= self.max_concurrent:
            raise TmuxManagerError(
                f"Maximum concurrent sessions ({self.max_concurrent}) reached",
            )

        # Create session
        session = TmuxSession(
            name=name,
            workdir=workdir,
            session_id=session_id,
            shell=shell,
            env=env,
        )

        # Store metadata
        self._session_metadata[session.session_id] = metadata or {}

        # Auto-start if requested
        if auto_start:
            await session.start()

        # Register session
        self._sessions[session.session_id] = session
        self._update_stats()

        return session

    async def get_session(self, session_id: str) -> TmuxSession | None:
        """
        Get a session by ID.

        Args:
            session_id: The session ID to look up

        Returns:
            The TmuxSession if found, None otherwise
        """
        return self._sessions.get(session_id)

    async def get_session_by_name(self, name: str) -> TmuxSession | None:
        """
        Get a session by its human-readable name.

        Args:
            name: The session name to search for

        Returns:
            The first matching TmuxSession if found, None otherwise
        """
        for session in self._sessions.values():
            if session.name == name:
                return session
        return None

    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        prefix: str | None = None,
    ) -> list[TmuxSession]:
        """
        List tracked sessions with optional filtering.

        Args:
            status: Filter by session status
            prefix: Filter by session ID prefix

        Returns:
            List of matching sessions
        """
        sessions = list(self._sessions.values())

        if status:
            sessions = [s for s in sessions if s.status == status]

        if prefix:
            sessions = [s for s in sessions if s.session_id.startswith(prefix)]

        return sessions

    async def list_session_infos(
        self,
        status: SessionStatus | None = None,
    ) -> list[SessionInfo]:
        """
        Get information about all tracked sessions.

        Args:
            status: Filter by session status

        Returns:
            List of SessionInfo objects
        """
        sessions = await self.list_sessions(status=status)
        return [s.info for s in sessions]

    async def kill_session(self, session_id: str) -> bool:
        """
        Kill and unregister a session.

        Args:
            session_id: ID of the session to kill

        Returns:
            True if session was killed, False if not found
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        await session.kill()
        del self._sessions[session_id]
        self._session_metadata.pop(session_id, None)
        self._update_stats()

        return True

    async def kill_sessions_by_prefix(self, prefix: str) -> int:
        """
        Kill all sessions with a given ID prefix.

        Args:
            prefix: Session ID prefix to match

        Returns:
            Number of sessions killed
        """
        count = 0
        session_ids = [sid for sid in self._sessions if sid.startswith(prefix)]

        for session_id in session_ids:
            if await self.kill_session(session_id):
                count += 1

        return count

    async def kill_sessions_by_status(self, status: SessionStatus) -> int:
        """
        Kill all sessions with a given status.

        Args:
            status: Status to match

        Returns:
            Number of sessions killed
        """
        count = 0
        sessions = await self.list_sessions(status=status)

        for session in sessions:
            if await self.kill_session(session.session_id):
                count += 1

        return count

    async def cleanup_stopped(self) -> int:
        """
        Remove all stopped sessions from tracking.

        Returns:
            Number of sessions cleaned up
        """
        return await self.kill_sessions_by_status(SessionStatus.STOPPED)

    async def cleanup_errors(self) -> int:
        """
        Remove all error sessions from tracking.

        Returns:
            Number of sessions cleaned up
        """
        return await self.kill_sessions_by_status(SessionStatus.ERROR)

    async def cleanup_all(self) -> int:
        """
        Kill and remove all tracked sessions.

        Returns:
            Number of sessions cleaned up
        """
        count = len(self._sessions)
        session_ids = list(self._sessions.keys())

        for session_id in session_ids:
            await self.kill_session(session_id)

        return count

    async def health_check(self) -> dict[str, bool]:
        """
        Check health of all tracked sessions.

        Returns:
            Dictionary mapping session IDs to health status
        """
        health: dict[str, bool] = {}

        for session_id, session in self._sessions.items():
            if session.status != SessionStatus.RUNNING:
                health[session_id] = False
            else:
                health[session_id] = await session.is_alive()

        return health

    async def get_unhealthy_sessions(self) -> list[TmuxSession]:
        """
        Get list of sessions that are unhealthy.

        Returns:
            List of unhealthy sessions
        """
        unhealthy = []
        health = await self.health_check()

        for session_id, is_healthy in health.items():
            if not is_healthy:
                session = self._sessions.get(session_id)
                if session:
                    unhealthy.append(session)

        return unhealthy

    async def start_health_monitor(self) -> None:
        """
        Start the background health monitoring task.

        Periodically checks session health and marks dead sessions.
        """
        if self._running:
            return

        self._running = True
        self._health_task = asyncio.create_task(self._health_monitor_loop())

    async def stop_health_monitor(self) -> None:
        """Stop the background health monitoring task."""
        self._running = False

        if self._health_task:
            self._health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_task
            self._health_task = None

    async def _health_monitor_loop(self) -> None:
        """Background loop for health monitoring."""
        while self._running:
            try:
                health = await self.health_check()

                # Mark dead sessions as error
                for session_id, is_healthy in health.items():
                    if not is_healthy:
                        session = self._sessions.get(session_id)
                        if session and session.status == SessionStatus.RUNNING:
                            session._status = SessionStatus.ERROR

                self._update_stats()

            except asyncio.CancelledError:
                break
            except Exception:
                # Log but continue monitoring
                pass

            await asyncio.sleep(self.health_check_interval)

    def set_session_metadata(
        self,
        session_id: str,
        key: str,
        value: Any,
    ) -> bool:
        """
        Set metadata for a session.

        Args:
            session_id: Session ID
            key: Metadata key
            value: Metadata value

        Returns:
            True if session exists, False otherwise
        """
        if session_id not in self._session_metadata:
            return False

        self._session_metadata[session_id][key] = value
        return True

    def get_session_metadata(
        self,
        session_id: str,
        key: str | None = None,
    ) -> Any:
        """
        Get metadata for a session.

        Args:
            session_id: Session ID
            key: Optional specific key (returns all if None)

        Returns:
            Metadata value or dict, None if not found
        """
        metadata = self._session_metadata.get(session_id)

        if metadata is None:
            return None

        if key is None:
            return metadata.copy()

        return metadata.get(key)

    async def broadcast_command(
        self,
        command: str,
        status: SessionStatus | None = SessionStatus.RUNNING,
    ) -> dict[str, bool]:
        """
        Send a command to multiple sessions.

        Args:
            command: Command to send
            status: Only send to sessions with this status (None = all)

        Returns:
            Dictionary mapping session IDs to success status
        """
        results: dict[str, bool] = {}
        sessions = await self.list_sessions(status=status)

        for session in sessions:
            try:
                await session.send_command(command)
                results[session.session_id] = True
            except TmuxSessionError:
                results[session.session_id] = False

        return results

    async def capture_all_outputs(
        self,
        lines: int = 1000,
        status: SessionStatus | None = SessionStatus.RUNNING,
    ) -> dict[str, str]:
        """
        Capture output from multiple sessions.

        Args:
            lines: Number of lines to capture
            status: Only capture from sessions with this status

        Returns:
            Dictionary mapping session IDs to captured output
        """
        outputs: dict[str, str] = {}
        sessions = await self.list_sessions(status=status)

        for session in sessions:
            try:
                output = await session.capture_output(lines=lines)
                outputs[session.session_id] = output
            except TmuxSessionError:
                outputs[session.session_id] = ""

        return outputs

    async def discover_orphaned_sessions(self) -> list[str]:
        """
        Find tmux sessions that exist but aren't tracked.

        Returns:
            List of orphaned session IDs
        """
        # Get all autoflow sessions from tmux
        all_tmux_sessions = await TmuxSession.list_sessions(prefix=self.prefix)

        # Find sessions not in our registry
        orphaned = [sid for sid in all_tmux_sessions if sid not in self._sessions]

        return orphaned

    async def adopt_orphaned_session(self, session_id: str) -> TmuxSession | None:
        """
        Adopt an orphaned tmux session into management.

        Args:
            session_id: ID of the orphaned session

        Returns:
            The adopted TmuxSession, or None if not found
        """
        # Check if session exists in tmux
        if not await TmuxSession.session_exists(session_id):
            return None

        # Check if already tracked
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Create a session wrapper (without starting a new tmux session)
        session = TmuxSession(
            name=session_id.split("-")[-2] if "-" in session_id else session_id,
            workdir=".",  # Unknown, will use current
            session_id=session_id,
        )

        # Mark as running since it exists
        session._status = SessionStatus.RUNNING

        # Register
        self._sessions[session_id] = session
        self._session_metadata[session_id] = {"adopted": True}
        self._update_stats()

        return session

    async def cleanup_orphaned_sessions(self) -> int:
        """
        Kill all orphaned tmux sessions.

        Returns:
            Number of sessions cleaned up
        """
        orphaned = await self.discover_orphaned_sessions()
        count = 0

        for session_id in orphaned:
            try:
                await TmuxSession._run_tmux_command(
                    ["kill-session", "-t", session_id],
                    check=False,
                )
                count += 1
            except TmuxSessionError:
                pass

        return count

    def get_stats_summary(self) -> dict[str, Any]:
        """
        Get a summary of manager statistics.

        Returns:
            Dictionary with stats summary
        """
        self._update_stats()
        return {
            "total_sessions": self._stats.total_sessions,
            "active_sessions": self._stats.active_sessions,
            "stopped_sessions": self._stats.stopped_sessions,
            "error_sessions": self._stats.error_sessions,
            "max_concurrent": self._stats.max_concurrent,
            "available_slots": self._stats.max_concurrent - self._stats.total_sessions,
            "created_at": self._created_at.isoformat(),
        }

    def __repr__(self) -> str:
        """Return string representation of the manager."""
        self._update_stats()
        return (
            f"TmuxManager("
            f"sessions={self._stats.total_sessions}, "
            f"active={self._stats.active_sessions}, "
            f"max={self.max_concurrent})"
        )

    def __str__(self) -> str:
        """Return human-readable string representation."""
        self._update_stats()
        return (
            f"Tmux Manager: {self._stats.active_sessions}/{self.max_concurrent} "
            f"active sessions"
        )

    async def __aenter__(self) -> TmuxManager:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - cleans up all sessions."""
        await self.stop_health_monitor()
        await self.cleanup_all()
