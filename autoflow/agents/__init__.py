"""
Autoflow Agents - AI Agent Adapters

This module provides unified adapters for different AI agents:
- Claude Code CLI
- OpenAI Codex CLI
- OpenClaw sessions
- Symphony multi-agent framework

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
from autoflow.agents.codex import CodexAdapter
from autoflow.agents.openclaw import OpenClawAdapter, OpenClawRuntime, SpawnResult
from autoflow.agents.symphony import (
    SymphonyAdapter,
    SymphonyRuntime,
    SymphonySession,
)

__all__ = [
    "AgentAdapter",
    "AgentConfig",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "ExecutionResult",
    "ExecutionStatus",
    "OpenClawAdapter",
    "OpenClawRuntime",
    "ResumeMode",
    "SpawnResult",
    "SymphonyAdapter",
    "SymphonyRuntime",
    "SymphonySession",
]
