"""
Autoflow Skills - Skill Loading and Execution

This module provides the skills system for Autoflow:
- SkillRegistry: Load and validate skill definitions
- SkillExecutor: Execute skills with appropriate agents
- SymphonyBridge: Integrate Symphony workflows with Autoflow skills

Skills are OpenClaw-compatible definitions that specify:
- Role and workflow
- Input/output requirements
- Agent assignments
"""

from autoflow.skills.registry import (
    SkillDefinition,
    SkillMetadata,
    SkillRegistry,
    SkillRegistryError,
    SkillStatus,
    create_registry,
)
from autoflow.skills.executor import (
    SkillExecutor,
    SkillExecutorError,
    SkillExecutionContext,
    SkillExecutionResult,
    SkillExecutionStatus,
    create_executor,
)
from autoflow.skills.symphony_bridge import (
    SymphonyBridge,
    SymphonyBridgeError,
    SymphonyBridgeResult,
    SymphonyBridgeStatus,
    SymphonyWorkflowContext,
    create_symphony_bridge,
)

__all__ = [
    # Registry
    "SkillRegistry",
    "SkillDefinition",
    "SkillMetadata",
    "SkillStatus",
    "SkillRegistryError",
    "create_registry",
    # Executor
    "SkillExecutor",
    "SkillExecutorError",
    "SkillExecutionContext",
    "SkillExecutionResult",
    "SkillExecutionStatus",
    "create_executor",
    # Symphony Bridge
    "SymphonyBridge",
    "SymphonyBridgeError",
    "SymphonyBridgeResult",
    "SymphonyBridgeStatus",
    "SymphonyWorkflowContext",
    "create_symphony_bridge",
]
