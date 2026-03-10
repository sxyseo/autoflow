"""
Autoflow Tmux Session Module

Provides individual tmux session management for running AI agents
in persistent background sessions. This enables 24/7 autonomous
operation with detached sessions that survive terminal disconnects.

Usage:
    from autoflow.tmux.session import TmuxSession

    # Create and start a session
    session = TmuxSession(name="my-agent", workdir="/path/to/project")
    await session.start()

    # Send commands
    await session.send_command("claude --print 'Fix the bug'")

    # Capture output
    output = await session.capture_output()

    # Clean up
    await session.kill()
"""

from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, Field

from autoflow.core.state import MetadataDict


class SessionStatus(str, Enum):
    """Status of a tmux session."""

    CREATED = "created"  # Session object created but not started
    RUNNING = "running"  # Session is active and running
    STOPPED = "stopped"  # Session has been stopped
    ERROR = "error"  # Session encountered an error


class SessionInfo(BaseModel):
    """Information about a tmux session."""

    session_id: str
    name: str
    workdir: str
    status: SessionStatus
    created_at: datetime = Field(default_factory=datetime.utcnow)
    pid: Optional[int] = None
    windows: int = 1
    attached: bool = False
    metadata: MetadataDict = Field(default_factory=dict)


class TmuxSessionError(Exception):
    """Exception raised for tmux session errors."""

    def __init__(self, message: str, session_id: Optional[str] = None):
        self.session_id = session_id
        super().__init__(message)


class TmuxSession:
    """
    Manages a tmux session for autonomous agent execution.

    This class wraps tmux commands to provide:
    - Session creation with unique IDs for isolation
    - Non-interactive command sending
    - Output capture for verification
    - Health monitoring
    - Clean resource cleanup

    Sessions are detached by default, enabling background operation
    for 24/7 autonomous agent execution.

    Attributes:
        name: Human-readable name for the session
        workdir: Working directory for the session
        session_id: Unique tmux session identifier
        status: Current session status
        info: Session information model

    Example:
        >>> session = TmuxSession(
        ...     name="claude-worker",
        ...     workdir="/projects/myapp"
        ... )
        >>> await session.start()
        >>> await session.send_command("claude --print 'Implement feature X'")
        >>> output = await session.capture_output()
        >>> await session.kill()
    """

    # Prefix for all autoflow tmux sessions
    SESSION_PREFIX: str = "autoflow"

    def __init__(
        self,
        name: str,
        workdir: Union[str, Path],
        session_id: Optional[str] = None,
        shell: str = "/bin/bash",
        env: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Initialize a tmux session wrapper.

        Args:
            name: Human-readable name for the session (e.g., "claude-worker")
            workdir: Working directory where commands will execute
            session_id: Optional explicit session ID (auto-generated if None)
            shell: Shell to use in the session (default: /bin/bash)
            env: Environment variables to set in the session

        Raises:
            TmuxSessionError: If tmux is not available
        """
        self.name = name
        self.workdir = Path(workdir) if isinstance(workdir, str) else workdir
        self._shell = shell
        self._env = env or {}

        # Generate unique session ID
        if session_id:
            self.session_id = session_id
        else:
            unique_suffix = uuid.uuid4().hex[:8]
            # Sanitize name for tmux (alphanumeric and hyphens only)
            safe_name = re.sub(r"[^a-zA-Z0-9-]", "-", name)
            self.session_id = f"{self.SESSION_PREFIX}-{safe_name}-{unique_suffix}"

        self._status = SessionStatus.CREATED
        self._info: Optional[SessionInfo] = None
        self._created_at = datetime.utcnow()

    @property
    def status(self) -> SessionStatus:
        """Get the current session status."""
        return self._status

    @property
    def info(self) -> SessionInfo:
        """Get session information."""
        if self._info is None:
            self._info = SessionInfo(
                session_id=self.session_id,
                name=self.name,
                workdir=str(self.workdir),
                status=self._status,
                created_at=self._created_at,
            )
        else:
            # Update status in cached info
            self._info.status = self._status
        return self._info

    @staticmethod
    async def _run_tmux_command(
        args: list[str],
        timeout: float = 30.0,
        check: bool = True,
    ) -> tuple[int, str, str]:
        """
        Run a tmux command and return the result.

        Args:
            args: Command arguments (without 'tmux' prefix)
            timeout: Command timeout in seconds
            check: If True, raise exception on non-zero exit

        Returns:
            Tuple of (exit_code, stdout, stderr)

        Raises:
            TmuxSessionError: If command fails and check=True
            asyncio.TimeoutError: If command times out
        """
        cmd = ["tmux"] + args

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            stdout_str = stdout.decode("utf-8").strip() if stdout else ""
            stderr_str = stderr.decode("utf-8").strip() if stderr else ""

            if check and process.returncode != 0:
                raise TmuxSessionError(
                    f"tmux command failed: {' '.join(args)}\n"
                    f"stderr: {stderr_str}",
                )

            return process.returncode or 0, stdout_str, stderr_str

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise

    @classmethod
    async def check_tmux_available(cls) -> bool:
        """
        Check if tmux is available on the system.

        Returns:
            True if tmux is installed and accessible
        """
        return shutil.which("tmux") is not None

    @classmethod
    async def list_sessions(cls, prefix: Optional[str] = None) -> list[str]:
        """
        List all tmux sessions.

        Args:
            prefix: Optional prefix to filter sessions

        Returns:
            List of session names
        """
        try:
            _, output, _ = await cls._run_tmux_command(
                ["list-sessions", "-F", "#{session_name}"],
                check=False,
            )
            sessions = [s.strip() for s in output.split("\n") if s.strip()]

            if prefix:
                sessions = [s for s in sessions if s.startswith(prefix)]

            return sessions
        except TmuxSessionError:
            return []

    @classmethod
    async def session_exists(cls, session_id: str) -> bool:
        """
        Check if a tmux session exists.

        Args:
            session_id: The session ID to check

        Returns:
            True if the session exists
        """
        try:
            await cls._run_tmux_command(
                ["has-session", "-t", session_id],
                check=True,
            )
            return True
        except TmuxSessionError:
            return False

    async def start(self) -> None:
        """
        Create and start the tmux session.

        Creates a new detached tmux session in the specified working directory.
        The session runs in the background and can receive commands via
        send_command().

        Raises:
            TmuxSessionError: If session creation fails
            FileNotFoundError: If working directory doesn't exist
        """
        # Verify tmux is available
        if not await self.check_tmux_available():
            raise TmuxSessionError(
                "tmux is not available. Please install tmux first.",
                session_id=self.session_id,
            )

        # Verify working directory exists
        if not self.workdir.exists():
            raise FileNotFoundError(
                f"Working directory does not exist: {self.workdir}",
            )

        # Check if session already exists
        if await self.session_exists(self.session_id):
            # Session exists, just update status
            self._status = SessionStatus.RUNNING
            return

        # Build environment variables for the session
        env_args = []
        for key, value in self._env.items():
            env_args.extend(["-e", f"{key}={value}"])

        # Create new detached session
        args = [
            "new-session",
            "-d",  # Detached
            "-s", self.session_id,  # Session name
            "-c", str(self.workdir),  # Working directory
            "-x", "120",  # Width
            "-y", "40",  # Height
        ]

        # Add shell if specified
        if self._shell:
            args.append(self._shell)

        try:
            await self._run_tmux_command(args + env_args, check=True)
            self._status = SessionStatus.RUNNING

            # Update info with session details
            self._info = SessionInfo(
                session_id=self.session_id,
                name=self.name,
                workdir=str(self.workdir),
                status=self._status,
                created_at=self._created_at,
            )

        except TmuxSessionError as e:
            self._status = SessionStatus.ERROR
            raise TmuxSessionError(
                f"Failed to create tmux session: {e}",
                session_id=self.session_id,
            ) from e

    async def send_command(
        self,
        command: str,
        enter: bool = True,
        delay: float = 0.1,
    ) -> None:
        """
        Send a command to the session.

        Sends keystrokes to the tmux session. By default, presses Enter
        after the command to execute it.

        Args:
            command: The command string to send
            enter: If True, press Enter after the command
            delay: Delay in seconds after sending (for processing)

        Raises:
            TmuxSessionError: If session is not running or send fails
        """
        if self._status != SessionStatus.RUNNING:
            raise TmuxSessionError(
                f"Session is not running (status: {self._status.value})",
                session_id=self.session_id,
            )

        # Build the send-keys command
        args = ["send-keys", "-t", self.session_id]

        if enter:
            args.extend([command, "Enter"])
        else:
            args.append(command)

        await self._run_tmux_command(args, check=True)

        # Small delay to let the command process
        if delay > 0:
            await asyncio.sleep(delay)

    async def send_keys(self, keys: str) -> None:
        """
        Send raw keystrokes to the session.

        Use this for special keys like Ctrl-C, Ctrl-D, etc.
        Key names follow tmux key naming conventions.

        Args:
            keys: Key string (e.g., "C-c" for Ctrl-C, "C-d" for Ctrl-D)

        Raises:
            TmuxSessionError: If session is not running or send fails

        Example:
            >>> await session.send_keys("C-c")  # Send Ctrl-C
        """
        if self._status != SessionStatus.RUNNING:
            raise TmuxSessionError(
                f"Session is not running (status: {self._status.value})",
                session_id=self.session_id,
            )

        await self._run_tmux_command(
            ["send-keys", "-t", self.session_id, keys],
            check=True,
        )

    async def capture_output(
        self,
        lines: int = 1000,
        escape_sequences: bool = False,
    ) -> str:
        """
        Capture current session output.

        Captures the visible content of the tmux pane, including
        scrollback history up to the specified number of lines.

        Args:
            lines: Number of lines to capture from history
            escape_sequences: If True, preserve escape sequences

        Returns:
            The captured output as a string

        Raises:
            TmuxSessionError: If capture fails
        """
        if self._status != SessionStatus.RUNNING:
            raise TmuxSessionError(
                f"Session is not running (status: {self._status.value})",
                session_id=self.session_id,
            )

        args = ["capture-pane", "-t", self.session_id, "-p"]

        if lines > 0:
            args.extend(["-S", f"-{lines}"])  # Start from N lines back

        if escape_sequences:
            args.append("-e")

        _, output, _ = await self._run_tmux_command(args, check=True)
        return output

    async def capture_pane(
        self,
        start_line: int = -1000,
        end_line: int = -1,
    ) -> str:
        """
        Capture a specific range of lines from the pane.

        Args:
            start_line: Starting line (negative for scrollback)
            end_line: Ending line (default: -1 for current line)

        Returns:
            The captured output as a string
        """
        if self._status != SessionStatus.RUNNING:
            raise TmuxSessionError(
                f"Session is not running (status: {self._status.value})",
                session_id=self.session_id,
            )

        args = [
            "capture-pane",
            "-t", self.session_id,
            "-p",
            "-S", str(start_line),
            "-E", str(end_line),
        ]

        _, output, _ = await self._run_tmux_command(args, check=True)
        return output

    async def clear_screen(self) -> None:
        """Clear the terminal screen in the session."""
        await self.send_keys("C-l")

    async def interrupt(self) -> None:
        """Send Ctrl-C to interrupt any running command."""
        await self.send_keys("C-c")

    async def send_eof(self) -> None:
        """Send Ctrl-D (EOF) to the session."""
        await self.send_keys("C-d")

    async def wait_for_output(
        self,
        pattern: str,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        Wait for a pattern to appear in the session output.

        Polls the session output at regular intervals until the pattern
        is found or timeout is reached.

        Args:
            pattern: Regex pattern to search for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds

        Returns:
            True if pattern was found, False if timeout reached

        Raises:
            TmuxSessionError: If session is not running
        """
        if self._status != SessionStatus.RUNNING:
            raise TmuxSessionError(
                f"Session is not running (status: {self._status.value})",
                session_id=self.session_id,
            )

        regex = re.compile(pattern)
        start_time = asyncio.get_event_loop().time()

        while True:
            output = await self.capture_output()
            if regex.search(output):
                return True

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                return False

            await asyncio.sleep(poll_interval)

    async def get_pid(self) -> Optional[int]:
        """
        Get the PID of the session's main process.

        Returns:
            The PID if available, None otherwise
        """
        try:
            _, output, _ = await self._run_tmux_command(
                ["display-message", "-t", self.session_id, "-p", "#{pane_pid}"],
                check=False,
            )
            if output.isdigit():
                return int(output)
            return None
        except TmuxSessionError:
            return None

    async def is_alive(self) -> bool:
        """
        Check if the session is still running.

        Returns:
            True if the session exists and is running
        """
        if self._status != SessionStatus.RUNNING:
            return False

        return await self.session_exists(self.session_id)

    async def attach(self) -> None:
        """
        Attach to the session interactively.

        Note: This will block until the session is detached.
        Typically not used in automated contexts.
        """
        if self._status != SessionStatus.RUNNING:
            raise TmuxSessionError(
                f"Session is not running (status: {self._status.value})",
                session_id=self.session_id,
            )

        await self._run_tmux_command(["attach", "-t", self.session_id])

    async def detach(self) -> None:
        """Detach any clients from this session."""
        try:
            await self._run_tmux_command(
                ["detach-client", "-s", self.session_id],
                check=False,
            )
        except TmuxSessionError:
            pass  # Ignore if no clients attached

    async def kill(self) -> None:
        """
        Kill the tmux session.

        Terminates the session and all its windows. This is a destructive
        operation that cannot be undone.

        After calling kill(), the session object cannot be reused.
        """
        if self._status == SessionStatus.STOPPED:
            return

        try:
            await self._run_tmux_command(
                ["kill-session", "-t", self.session_id],
                check=False,
            )
        except TmuxSessionError:
            pass  # Session may already be gone

        self._status = SessionStatus.STOPPED
        if self._info:
            self._info.status = SessionStatus.STOPPED

    async def rename(self, new_name: str) -> None:
        """
        Rename the session.

        Args:
            new_name: New name for the session

        Note:
            This changes the tmux session name, not the session_id
            used internally by this class.
        """
        if self._status != SessionStatus.RUNNING:
            raise TmuxSessionError(
                f"Session is not running (status: {self._status.value})",
                session_id=self.session_id,
            )

        await self._run_tmux_command(
            ["rename-session", "-t", self.session_id, new_name],
            check=True,
        )
        self.name = new_name

    def __repr__(self) -> str:
        """Return string representation of the session."""
        return (
            f"TmuxSession("
            f"session_id={self.session_id!r}, "
            f"name={self.name!r}, "
            f"status={self._status.value})"
        )

    def __str__(self) -> str:
        """Return human-readable string representation."""
        return f"tmux session '{self.name}' ({self.session_id}) [{self._status.value}]"

    async def __aenter__(self) -> "TmuxSession":
        """Async context manager entry - starts the session."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - kills the session."""
        await self.kill()
