"""
Autoflow Skills - Skill Loading and Execution

This module provides the skills system for Autoflow:
- SkillRegistry: Load and validate skill definitions
- SkillExecutor: Execute skills with appropriate agents

Skills are OpenClaw-compatible definitions that specify:
- Role and workflow
- Input/output requirements
- Agent assignments
"""

from autoflow.skills.executor import (
    SkillExecutionContext,
    SkillExecutionResult,
    SkillExecutionStatus,
    SkillExecutor,
    SkillExecutorError,
    create_executor,
)
from autoflow.skills.registry import (
    SkillDefinition,
    SkillMetadata,
    SkillRegistry,
    SkillRegistryError,
    SkillStatus,
    create_registry,
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
]
