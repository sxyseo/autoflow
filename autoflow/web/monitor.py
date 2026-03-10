"""
Autoflow State Monitor Module

Provides background file watching for the .autoflow/ state directory and
broadcasts changes via WebSocket for real-time dashboard updates. Monitors
tasks, runs, and specs for changes and notifies connected clients.

Usage:
    from autoflow.web.monitor import StateMonitor

    # Create monitor instance
    monitor = StateMonitor(state_dir=".autoflow")

    # Start monitoring (runs in background)
    await monitor.start()

    # Stop monitoring
    await monitor.stop()
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Set

from fastapi import WebSocket

from autoflow.core.state import StateManager


class WebSocketConnectionManager:
    """
    Manager for WebSocket connections.

    Manages active WebSocket connections and broadcasts updates to all
    connected clients. Provides thread-safe connection handling.

    Attributes:
        active_connections: Set of active WebSocket connections

    Example:
        >>> manager = WebSocketConnectionManager()
        >>> await manager.broadcast({"type": "status", "data": {...}})
    """

    def __init__(self) -> None:
        """Initialize the connection manager with empty connections set."""
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            websocket: The WebSocket connection to accept and register.
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from active connections.

        Args:
            websocket: The WebSocket connection to remove.
        """
        async with self._lock:
            self.active_connections.discard(websocket)

    async def send_personal_message(self, message: dict[str, object], websocket: WebSocket) -> None:
        """
        Send a message to a specific WebSocket connection.

        Args:
            message: The message dictionary to send.
            websocket: The WebSocket connection to send the message to.
        """
        try:
            await websocket.send_json(message)
        except Exception:
            # Connection may be closed, remove it
            await self.disconnect(websocket)

    async def broadcast(self, message: dict[str, object]) -> None:
        """
        Broadcast a message to all active WebSocket connections.

        Args:
            message: The message dictionary to broadcast to all connections.
        """
        async with self._lock:
            # Create a copy of connections to avoid modification during iteration
            connections = list(self.active_connections)

        # Send to all connections
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection may be closed, remove it
                await self.disconnect(connection)


class FileEvent:
    """
    Represents a file system event.

    Captures information about a file change event including the type of
    change, the file path, and the category of state that changed.

    Attributes:
        event_type: Type of event (created, modified, deleted)
        path: Path to the file that changed
        category: Category of state (task, run, spec)
        timestamp: When the event occurred

    Example:
        >>> event = FileEvent(
        ...     event_type="modified",
        ...     path=Path(".autoflow/tasks/task-001.json"),
        ...     category="task"
        ... )
    """

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"

    def __init__(
        self,
        event_type: str,
        path: Path,
        category: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Initialize a FileEvent.

        Args:
            event_type: Type of event (created, modified, deleted)
            path: Path to the file that changed
            category: Category of state (task, run, spec)
            timestamp: When the event occurred (defaults to now)
        """
        self.event_type = event_type
        self.path = path
        self.category = category
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """
        Convert event to dictionary for WebSocket broadcast.

        Returns:
            Dictionary representation of the event
        """
        return {
            "type": self.category,
            "action": self.event_type,
            "path": str(self.path),
            "timestamp": self.timestamp.isoformat(),
        }


class StateMonitor:
    """
    Monitors the Autoflow state directory for file changes.

    Watches the .autoflow/ state directory for changes to tasks, runs, and specs.
    Detects file creation, modification, and deletion events. Provides callbacks
    for handling events and integrates with WebSocket for real-time updates.

    Uses polling-based file watching with asyncio for efficient operation without
    external dependencies.

    Attributes:
        state_dir: Path to the state directory being monitored
        poll_interval: Seconds between polling checks
        state_manager: StateManager instance for reading state data
        running: Whether the monitor is currently running

    Example:
        >>> monitor = StateMonitor(state_dir=".autoflow")
        >>> await monitor.start()
        >>> # Monitor runs in background...
        >>> await monitor.stop()
    """

    # Default polling interval in seconds
    DEFAULT_POLL_INTERVAL = 1.0

    def __init__(
        self,
        state_dir: str | Path,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        """
        Initialize the StateMonitor.

        Args:
            state_dir: Path to the state directory to monitor
            poll_interval: Seconds between polling checks (default: 1.0)
        """
        self.state_dir = Path(state_dir).resolve()
        self.poll_interval = poll_interval
        self.state_manager = StateManager(self.state_dir)

        # WebSocket connection manager for broadcasting events
        self.connection_manager = WebSocketConnectionManager()

        # Tracking state
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._callback: Optional[Callable[[FileEvent], Any]] = None

        # File tracking for change detection
        self._tracked_files: dict[str, float] = {}

    @property
    def running(self) -> bool:
        """Check if the monitor is currently running."""
        return self._running

    def set_callback(self, callback: Callable[[FileEvent], Any]) -> None:
        """
        Set a callback function to handle file events.

        The callback will be invoked for each file event detected.
        This is typically used to broadcast events via WebSocket.

        Args:
            callback: Async function that takes a FileEvent parameter

        Example:
            >>> async def handle_event(event: FileEvent):
            ...     await manager.broadcast(event.to_dict())
            >>> monitor.set_callback(handle_event)
        """
        self._callback = callback

    async def start(self) -> None:
        """
        Start monitoring the state directory.

        Begins polling the state directory for changes. Runs as a background
        task until stop() is called. Safe to call multiple times.

        Raises:
            RuntimeError: If monitor is already running

        Example:
            >>> monitor = StateMonitor(".autoflow")
            >>> await monitor.start()
        """
        if self._running:
            return

        self._running = True

        # Initialize file tracking
        await self._scan_files()

        # Start monitoring task
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """
        Stop monitoring the state directory.

        Stops the background monitoring task. Safe to call multiple times.
        Waits for the monitoring loop to complete before returning.

        Example:
            >>> await monitor.stop()
        """
        if not self._running:
            return

        self._running = False

        # Cancel monitoring task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _monitor_loop(self) -> None:
        """
        Main monitoring loop.

        Continuously polls the state directory for changes and generates
        events for any modifications detected. Runs until stopped.
        """
        while self._running:
            try:
                await self._check_for_changes()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                # Task was cancelled, exit gracefully
                break
            except Exception:
                # Log error but continue monitoring
                await asyncio.sleep(self.poll_interval)

    async def _scan_files(self) -> None:
        """
        Scan all tracked files and initialize their modification times.

        Called on startup to establish baseline for change detection.
        """
        self._tracked_files.clear()

        # Scan all state subdirectories
        for category_dir, category in [
            (self.state_manager.tasks_dir, "task"),
            (self.state_manager.runs_dir, "run"),
            (self.state_manager.specs_dir, "spec"),
        ]:
            if not category_dir.exists():
                continue

            for file_path in category_dir.glob("*.json"):
                try:
                    mtime = file_path.stat().st_mtime
                    self._tracked_files[str(file_path)] = mtime
                except OSError:
                    # File may have been deleted, skip
                    continue

    async def _check_for_changes(self) -> None:
        """
        Check for file changes and generate events.

        Compares current file state with tracked state and generates
        events for new, modified, and deleted files.
        """
        current_files: set[str] = set()
        current_times: dict[str, float] = {}

        # Scan all state subdirectories
        for category_dir, category in [
            (self.state_manager.tasks_dir, "task"),
            (self.state_manager.runs_dir, "run"),
            (self.state_manager.specs_dir, "spec"),
        ]:
            if not category_dir.exists():
                continue

            for file_path in category_dir.glob("*.json"):
                file_str = str(file_path)
                current_files.add(file_str)

                try:
                    mtime = file_path.stat().st_mtime
                    current_times[file_str] = mtime

                    # Check for new or modified files
                    if file_str not in self._tracked_files:
                        # New file
                        await self._emit_event(
                            FileEvent(
                                event_type=FileEvent.CREATED,
                                path=file_path,
                                category=category,
                            )
                        )
                    elif mtime > self._tracked_files[file_str]:
                        # Modified file
                        await self._emit_event(
                            FileEvent(
                                event_type=FileEvent.MODIFIED,
                                path=file_path,
                                category=category,
                            )
                        )

                    # Update tracked time
                    self._tracked_files[file_str] = mtime

                except OSError:
                    # File may have been deleted, will be handled below
                    continue

        # Check for deleted files
        for file_str in list(self._tracked_files.keys()):
            if file_str not in current_files:
                # File was deleted
                file_path = Path(file_str)

                # Determine category from path
                category = "unknown"
                if "/tasks/" in file_str or "\\tasks\\" in file_str:
                    category = "task"
                elif "/runs/" in file_str or "\\runs\\" in file_str:
                    category = "run"
                elif "/specs/" in file_str or "\\specs\\" in file_str:
                    category = "spec"

                await self._emit_event(
                    FileEvent(
                        event_type=FileEvent.DELETED,
                        path=file_path,
                        category=category,
                    )
                )

                # Remove from tracking
                del self._tracked_files[file_str]

    async def _emit_event(self, event: FileEvent) -> None:
        """
        Emit a file event to the registered callback and broadcast via WebSocket.

        Broadcasts the event to all connected WebSocket clients and invokes
        the registered callback if one exists.

        Args:
            event: The file event to emit
        """
        # Broadcast to all WebSocket connections
        try:
            await self.broadcast(event.to_dict())
        except Exception:
            # Broadcast failed, but don't stop monitoring
            pass

        # Call registered callback if exists
        if self._callback:
            try:
                result = self._callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # Callback failed, but don't stop monitoring
                pass

    async def check_once(self) -> list[FileEvent]:
        """
        Perform a single check for changes.

        Useful for testing or one-time polling. Returns events without
        invoking the callback.

        Returns:
            List of file events detected

        Example:
            >>> events = await monitor.check_once()
            >>> for event in events:
            ...     print(f"{event.event_type}: {event.path}")
        """
        events: list[FileEvent] = []
        original_callback = self._callback

        # Collect events instead of calling callback
        def collect_callback(event: FileEvent) -> None:
            events.append(event)

        self._callback = collect_callback

        try:
            await self._check_for_changes()
        finally:
            self._callback = original_callback

        return events

    def get_status(self) -> dict[str, Any]:
        """
        Get the current status of the monitor.

        Returns:
            Dictionary with monitor status information

        Example:
            >>> status = monitor.get_status()
            >>> print(f"Running: {status['running']}")
        """
        return {
            "running": self._running,
            "state_dir": str(self.state_dir),
            "poll_interval": self.poll_interval,
            "tracked_files": len(self._tracked_files),
            "callback_registered": self._callback is not None,
        }

    async def broadcast(self, message: dict[str, object]) -> None:
        """
        Broadcast a message to all connected WebSocket clients.

        Delegates to the connection manager to send the message to all
        active connections.

        Args:
            message: The message dictionary to broadcast to all connections.

        Example:
            >>> await monitor.broadcast({
            ...     "type": "task",
            ...     "action": "created",
            ...     "data": {...}
            ... })
        """
        await self.connection_manager.broadcast(message)
