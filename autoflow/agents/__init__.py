"""
Autoflow Agents - AI Agent Adapters

This module provides unified adapters for different AI agents:
- Claude Code CLI
- OpenAI Codex CLI
- OpenClaw sessions

All adapters follow a common interface for consistent task execution.
"""

from autoflow.agents.base import (
    AgentAdapter,
    AgentConfig,
    ExecutionResult,
    ExecutionStatus,
    ResumeMode,
)
from autoflow.agents.claude_code import ClaudeCodeAdapter

# Agent adapters will be imported here as they are implemented
# from autoflow.agents.codex import CodexAdapter
# from autoflow.agents.openclaw import OpenClawAdapter

__all__ = [
    "AgentAdapter",
    "AgentConfig",
    "ClaudeCodeAdapter",
    "ExecutionResult",
    "ExecutionStatus",
    "ResumeMode",
]
