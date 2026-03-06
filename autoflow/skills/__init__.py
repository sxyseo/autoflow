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

from autoflow.skills.registry import (
    SkillDefinition,
    SkillMetadata,
    SkillRegistry,
    SkillRegistryError,
    SkillStatus,
    create_registry,
)

# SkillExecutor will be imported when implemented
# from autoflow.skills.executor import SkillExecutor

__all__ = [
    "SkillRegistry",
    "SkillDefinition",
    "SkillMetadata",
    "SkillStatus",
    "SkillRegistryError",
    "create_registry",
]
