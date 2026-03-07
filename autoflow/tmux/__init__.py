"""
Autoflow Tmux - Session Management for Background Execution

This module provides tmux session management for running AI agents
in persistent background sessions:

- TmuxSession: Individual tmux session wrapper
- TmuxManager: Multi-session coordination and monitoring

Enables 24/7 autonomous operation with detached sessions.
"""

from autoflow.tmux.manager import (
    ManagerStats,
    TmuxManager,
    TmuxManagerError,
)
from autoflow.tmux.session import (
    SessionInfo,
    SessionStatus,
    TmuxSession,
    TmuxSessionError,
)

__all__ = [
    "ManagerStats",
    "SessionInfo",
    "SessionStatus",
    "TmuxManager",
    "TmuxManagerError",
    "TmuxSession",
    "TmuxSessionError",
]
