"""
Autoflow Skills - Skill Loading and Execution

This module provides the skills system for Autoflow:
- SkillRegistry: Load and validate skill definitions
- SkillExecutor: Execute skills with appropriate agents
- SkillBuilder: Create custom skills from templates
- SkillValidator: Validate skill content and structure
- SkillPackager: Package and share skills with teams

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
from autoflow.skills.builder import (
    BuilderConfig,
    PromptResponse,
    SkillBuilder,
    SkillBuilderError,
    create_builder,
)
from autoflow.skills.validation import (
    ValidationSeverity,
    ValidationError,
    ValidationResult,
    SkillValidator,
    create_validator,
)
from autoflow.skills.sharing import (
    PackageError,
    PackageFormat,
    SkillPackage,
    SkillPackageMetadata,
    SkillPackager,
    SkillImporter,
    ImportConflictResolution,
    ImportResult,
    VersionAction,
    VersionHistoryEntry,
    VersionChangeResult,
    VersionManager,
    create_packager,
    create_importer,
)
from autoflow.skills.templates import (
    TemplateCategory,
    SkillTemplate,
    RenderedTemplate,
    TemplateRenderer,
    TemplateLoaderError,
    TemplateLoader,
    create_loader,
    create_renderer,
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
    # Builder
    "SkillBuilder",
    "BuilderConfig",
    "PromptResponse",
    "SkillBuilderError",
    "create_builder",
    # Validation
    "SkillValidator",
    "ValidationResult",
    "ValidationError",
    "ValidationSeverity",
    "create_validator",
    # Sharing
    "SkillPackager",
    "SkillPackage",
    "SkillPackageMetadata",
    "SkillImporter",
    "PackageFormat",
    "PackageError",
    "ImportConflictResolution",
    "ImportResult",
    "VersionAction",
    "VersionHistoryEntry",
    "VersionChangeResult",
    "VersionManager",
    "create_packager",
    "create_importer",
    # Templates
    "TemplateCategory",
    "SkillTemplate",
    "RenderedTemplate",
    "TemplateRenderer",
    "TemplateLoaderError",
    "TemplateLoader",
    "create_loader",
    "create_renderer",
]
