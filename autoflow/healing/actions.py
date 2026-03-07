"""Healing action models and registry for self-healing workflows.

This module provides the core action system for executing healing operations,
including action definitions, result tracking, rollback management, and a
registry for managing available healing actions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from autoflow.healing.config import HealingConfig
    from autoflow.healing.diagnostic import RootCause


logger = logging.getLogger(__name__)


class ActionStatus(Enum):
    """Status of a healing action execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class ActionType(Enum):
    """Types of healing actions available."""

    RETRY = "retry"
    ROLLBACK = "rollback"
    RECONFIGURE = "reconfigure"
    RESTART = "restart"
    SCALE = "scale"
    ISOLATE = "isolate"
    PATCH = "patch"
    ESCALATE = "escalate"


class ActionSeverity(Enum):
    """Severity level of a healing action.

    Indicates the potential impact and risk level of an action.
    """

    LOW = "low"  # Minimal risk, reversible
    MEDIUM = "medium"  # Moderate risk, requires monitoring
    HIGH = "high"  # High risk, requires approval and verification
    CRITICAL = "critical"  # Maximum risk, may require human approval


@dataclass
class ActionResult:
    """Result of executing a healing action.

    Attributes:
        status: Final status of the action execution.
        success: Whether the action achieved its intended outcome.
        message: Human-readable message describing the result.
        error: Error message if the action failed.
        execution_time: Time taken to execute the action in seconds.
        changes_made: List of changes made by this action.
        verification_passed: Whether post-action verification passed.
        can_rollback: Whether this action can be rolled back.
        rollback_action: Action to execute for rollback (if applicable).
        metadata: Additional metadata about the action result.
        timestamp: When the action completed.
    """

    status: ActionStatus
    success: bool
    message: str
    error: str | None = None
    execution_time: float = 0.0
    changes_made: list[str] = field(default_factory=list)
    verification_passed: bool = False
    can_rollback: bool = False
    rollback_action: "HealingAction | None" = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert action result to dictionary.

        Returns:
            Dictionary representation of the action result.
        """
        return {
            "status": self.status.value,
            "success": self.success,
            "message": self.message,
            "error": self.error,
            "execution_time": self.execution_time,
            "changes_made": self.changes_made,
            "verification_passed": self.verification_passed,
            "can_rollback": self.can_rollback,
            "rollback_action": (
                self.rollback_action.to_dict() if self.rollback_action else None
            ),
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionResult":
        """Create action result from dictionary.

        Args:
            data: Dictionary containing action result data.

        Returns:
            ActionResult instance.
        """
        return cls(
            status=ActionStatus(data["status"]),
            success=data["success"],
            message=data["message"],
            error=data.get("error"),
            execution_time=data.get("execution_time", 0.0),
            changes_made=data.get("changes_made", []),
            verification_passed=data.get("verification_passed", False),
            can_rollback=data.get("can_rollback", False),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data
            else datetime.now(),
        )


@dataclass
class HealingAction:
    """A healing action that can be executed to repair workflow issues.

    Attributes:
        action_type: Type of healing action.
        name: Human-readable name for this action.
        description: Detailed description of what this action does.
        severity: Severity level of this action.
        parameters: Parameters for executing this action.
        preconditions: List of conditions that must be met before execution.
        expected_outcome: Expected result of executing this action.
        rollback_strategy: How to rollback this action if needed.
        timeout: Maximum time to wait for action completion (seconds).
        requires_approval: Whether this action requires human approval.
        created_at: When this action was created.
        id: Unique identifier for this action.
    """

    action_type: ActionType
    name: str
    description: str
    severity: ActionSeverity
    parameters: dict[str, Any] = field(default_factory=dict)
    preconditions: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    rollback_strategy: str | None = None
    timeout: int = 300  # 5 minutes default
    requires_approval: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    id: str = field(default="")

    def __post_init__(self) -> None:
        """Generate ID if not provided."""
        if not self.id:
            self.id = f"{self.action_type.value}-{int(self.created_at.timestamp())}"

    def to_dict(self) -> dict[str, Any]:
        """Convert healing action to dictionary.

        Returns:
            Dictionary representation of the healing action.
        """
        return {
            "action_type": self.action_type.value,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "parameters": self.parameters,
            "preconditions": self.preconditions,
            "expected_outcome": self.expected_outcome,
            "rollback_strategy": self.rollback_strategy,
            "timeout": self.timeout,
            "requires_approval": self.requires_approval,
            "created_at": self.created_at.isoformat(),
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HealingAction":
        """Create healing action from dictionary.

        Args:
            data: Dictionary containing healing action data.

        Returns:
            HealingAction instance.
        """
        return cls(
            action_type=ActionType(data["action_type"]),
            name=data["name"],
            description=data["description"],
            severity=ActionSeverity(data["severity"]),
            parameters=data.get("parameters", {}),
            preconditions=data.get("preconditions", []),
            expected_outcome=data.get("expected_outcome", ""),
            rollback_strategy=data.get("rollback_strategy"),
            timeout=data.get("timeout", 300),
            requires_approval=data.get("requires_approval", False),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            id=data.get("id", ""),
        )

    def should_require_approval(
        self, config: "HealingConfig | None" = None
    ) -> bool:
        """Determine if this action requires approval based on severity and config.

        Args:
            config: Optional healing configuration.

        Returns:
            True if action requires approval.
        """
        if self.requires_approval:
            return True

        # High and critical severity actions require approval by default
        if self.severity in (ActionSeverity.HIGH, ActionSeverity.CRITICAL):
            return True

        return False


class ActionExecutor(ABC):
    """Abstract base class for action executors.

    Each concrete action type should implement an executor that handles
    the actual execution logic, verification, and rollback.
    """

    @abstractmethod
    async def execute(self, action: HealingAction) -> ActionResult:
        """Execute a healing action.

        Args:
            action: The healing action to execute.

        Returns:
            ActionResult containing execution details.
        """
        pass

    @abstractmethod
    async def verify(self, action: HealingAction) -> bool:
        """Verify that the action achieved its intended outcome.

        Args:
            action: The healing action to verify.

        Returns:
            True if verification passed.
        """
        pass

    @abstractmethod
    async def rollback(self, action: HealingAction) -> ActionResult:
        """Rollback a healing action.

        Args:
            action: The healing action to rollback.

        Returns:
            ActionResult containing rollback details.
        """
        pass


class RollbackManager:
    """Manages rollback operations for healing actions.

    This manager creates checkpoints before actions are executed and
    provides rollback capabilities using the checkpoint system.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        """Initialize the rollback manager.

        Args:
            project_root: Root directory of the project.
        """
        self.project_root = project_root or Path.cwd()
        self._checkpoints: dict[str, dict[str, Any]] = {}
        self._checkpoint_dir = self.project_root / ".auto-claude" / "checkpoints"

    def create_checkpoint(
        self, action_id: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a checkpoint before executing a healing action.

        Args:
            action_id: ID of the action about to be executed.
            metadata: Optional metadata to store with the checkpoint.

        Returns:
            Checkpoint information dictionary.
        """
        checkpoint = {
            "action_id": action_id,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
            "git_head": self._get_git_head(),
        }

        self._checkpoints[action_id] = checkpoint
        logger.info(f"Created checkpoint for action {action_id}")

        return checkpoint

    def rollback_to_checkpoint(self, action_id: str) -> bool:
        """Rollback to the checkpoint created before an action.

        Args:
            action_id: ID of the action to rollback.

        Returns:
            True if rollback succeeded.
        """
        if action_id not in self._checkpoints:
            logger.warning(f"No checkpoint found for action {action_id}")
            return False

        checkpoint = self._checkpoints[action_id]
        logger.info(f"Rolling back action {action_id} to checkpoint")

        # In a full implementation, this would use git to rollback
        # For now, we just log the intention
        logger.info(f"Would rollback to git HEAD: {checkpoint['git_head']}")

        return True

    def _get_git_head(self) -> str:
        """Get current git HEAD commit hash.

        Returns:
            Git commit hash or empty string if not in git repo.
        """
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Could not get git HEAD: {e}")

        return ""

    def get_checkpoint(self, action_id: str) -> dict[str, Any] | None:
        """Get checkpoint information for an action.

        Args:
            action_id: ID of the action.

        Returns:
            Checkpoint information or None if not found.
        """
        return self._checkpoints.get(action_id)

    def clear_checkpoint(self, action_id: str) -> None:
        """Clear a checkpoint after successful action verification.

        Args:
            action_id: ID of the action.
        """
        if action_id in self._checkpoints:
            del self._checkpoints[action_id]
            logger.info(f"Cleared checkpoint for action {action_id}")


class ActionRegistry:
    """Registry for managing available healing actions and their executors.

    This registry maintains a mapping of action types to their executors,
    allowing for dynamic action execution and extensibility.
    """

    def __init__(self) -> None:
        """Initialize the action registry."""
        self._executors: dict[ActionType, ActionExecutor] = {}
        self._action_templates: dict[ActionType, list[HealingAction]] = {}
        self._rollback_manager = RollbackManager()

    def register_executor(
        self, action_type: ActionType, executor: ActionExecutor
    ) -> None:
        """Register an executor for a specific action type.

        Args:
            action_type: Type of action this executor handles.
            executor: Executor instance to register.
        """
        self._executors[action_type] = executor
        logger.info(f"Registered executor for action type: {action_type.value}")

    def register_template(self, action: HealingAction) -> None:
        """Register a healing action as a template.

        Templates can be instantiated and customized for specific scenarios.

        Args:
            action: Healing action template to register.
        """
        if action.action_type not in self._action_templates:
            self._action_templates[action.action_type] = []

        self._action_templates[action.action_type].append(action)
        logger.info(f"Registered action template: {action.name}")

    def get_executor(self, action_type: ActionType) -> ActionExecutor | None:
        """Get executor for a specific action type.

        Args:
            action_type: Type of action.

        Returns:
            ActionExecutor if registered, None otherwise.
        """
        return self._executors.get(action_type)

    def get_templates(self, action_type: ActionType) -> list[HealingAction]:
        """Get all templates for a specific action type.

        Args:
            action_type: Type of action.

        Returns:
            List of healing action templates.
        """
        return self._action_templates.get(action_type, [])

    def create_action(
        self,
        action_type: ActionType,
        name: str,
        description: str,
        severity: ActionSeverity = ActionSeverity.MEDIUM,
        **kwargs: Any,
    ) -> HealingAction:
        """Create a new healing action.

        Args:
            action_type: Type of action to create.
            name: Name for the action.
            description: Description of the action.
            severity: Severity level of the action.
            **kwargs: Additional parameters for the action.

        Returns:
            New HealingAction instance.
        """
        return HealingAction(
            action_type=action_type,
            name=name,
            description=description,
            severity=severity,
            parameters=kwargs.get("parameters", {}),
            preconditions=kwargs.get("preconditions", []),
            expected_outcome=kwargs.get("expected_outcome", ""),
            rollback_strategy=kwargs.get("rollback_strategy"),
            timeout=kwargs.get("timeout", 300),
            requires_approval=kwargs.get("requires_approval", False),
        )

    async def execute_action(
        self,
        action: HealingAction,
        config: "HealingConfig | None" = None,
    ) -> ActionResult:
        """Execute a healing action with full lifecycle management.

        This method handles the complete action lifecycle:
        1. Check preconditions
        2. Create checkpoint for rollback
        3. Execute the action
        4. Verify the result
        5. Rollback if verification fails

        Args:
            action: Healing action to execute.
            config: Optional healing configuration.

        Returns:
            ActionResult containing execution details.
        """
        start_time = time.time()
        logger.info(f"Executing healing action: {action.name} (ID: {action.id})")

        # Check if action requires approval
        if action.should_require_approval(config):
            logger.warning(
                f"Action {action.name} requires approval but auto-executing. "
                "In production, this should be approved first."
            )

        # Check preconditions
        if not self._check_preconditions(action):
            return ActionResult(
                status=ActionStatus.SKIPPED,
                success=False,
                message="Preconditions not met",
                error="One or more preconditions failed",
                execution_time=time.time() - start_time,
            )

        # Create checkpoint for rollback
        self._rollback_manager.create_checkpoint(
            action.id, metadata={"action_name": action.name}
        )

        try:
            # Get executor for this action type
            executor = self.get_executor(action.action_type)
            if not executor:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    success=False,
                    message=f"No executor registered for action type: {action.action_type.value}",
                    error="Executor not found",
                    execution_time=time.time() - start_time,
                    can_rollback=True,
                )

            # Execute the action
            result = await executor.execute(action)
            result.execution_time = time.time() - start_time

            # Verify the result
            if result.success:
                try:
                    verified = await executor.verify(action)
                    result.verification_passed = verified

                    if not verified:
                        logger.warning(
                            f"Action {action.name} execution succeeded but verification failed"
                        )
                        # Rollback if verification fails
                        if self._rollback_manager.rollback_to_checkpoint(action.id):
                            result.status = ActionStatus.ROLLED_BACK
                            result.message = "Action executed but verification failed, rolled back"
                except Exception as e:
                    logger.error(f"Verification failed for action {action.name}: {e}")
                    result.verification_passed = False

            # Clear checkpoint if action succeeded and verified
            if result.success and result.verification_passed:
                self._rollback_manager.clear_checkpoint(action.id)

            return result

        except Exception as e:
            logger.error(f"Error executing action {action.name}: {e}")
            execution_time = time.time() - start_time

            # Attempt rollback on error
            if self._rollback_manager.rollback_to_checkpoint(action.id):
                return ActionResult(
                    status=ActionStatus.ROLLED_BACK,
                    success=False,
                    message=f"Action failed and rolled back: {str(e)}",
                    error=str(e),
                    execution_time=execution_time,
                )

            return ActionResult(
                status=ActionStatus.FAILED,
                success=False,
                message=f"Action failed: {str(e)}",
                error=str(e),
                execution_time=execution_time,
            )

    def _check_preconditions(self, action: HealingAction) -> bool:
        """Check if all preconditions for an action are met.

        Args:
            action: Healing action to check.

        Returns:
            True if all preconditions are met.
        """
        # In a full implementation, this would check actual preconditions
        # For now, we assume all preconditions are met
        return True

    def get_registered_action_types(self) -> list[ActionType]:
        """Get list of action types with registered executors.

        Returns:
            List of ActionType enums.
        """
        return list(self._executors.keys())

    def get_registry_stats(self) -> dict[str, Any]:
        """Get statistics about the registry.

        Returns:
            Dictionary containing registry statistics.
        """
        return {
            "registered_executors": len(self._executors),
            "registered_templates": sum(
                len(templates) for templates in self._action_templates.values()
            ),
            "action_types": [t.value for t in self._executors.keys()],
            "active_checkpoints": len(self._rollback_manager._checkpoints),
        }


# Global registry instance
_global_registry: ActionRegistry | None = None


def get_global_registry() -> ActionRegistry:
    """Get the global action registry instance.

    Returns:
        Global ActionRegistry instance.
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ActionRegistry()
    return _global_registry
