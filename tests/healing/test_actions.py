"""Unit Tests for Healing Action System.

Tests the healing action models, executors, and registry for self-healing workflows.
These tests ensure the action system can:
- Create and manage healing actions with proper metadata
- Execute actions through appropriate executors
- Verify action results
- Handle rollback operations
- Manage action lifecycle through the registry
- Track action results with proper serialization
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.healing.actions import (
    ActionRegistry,
    ActionSeverity,
    ActionStatus,
    ActionType,
    ActionResult,
    ActionExecutor,
    EscalateActionExecutor,
    get_global_registry,
    HealingAction,
    PatchActionExecutor,
    ReconfigureActionExecutor,
    RestartActionExecutor,
    RetryActionExecutor,
    RollbackManager,
)
from autoflow.healing.config import HealingConfig


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_config() -> HealingConfig:
    """Create a sample healing configuration for testing."""
    return HealingConfig(
        enabled=True,
        max_healing_attempts=3,
        healing_timeout=600,
    )


@pytest.fixture
def sample_action() -> HealingAction:
    """Create a sample healing action for testing."""
    return HealingAction(
        action_type=ActionType.RETRY,
        name="Retry Failed Task",
        description="Retry the failed task with exponential backoff",
        severity=ActionSeverity.LOW,
        parameters={"max_retries": 3, "base_delay": 1.0},
        preconditions=["Task failed with transient error"],
        expected_outcome="Task completes successfully",
        rollback_strategy="Reset retry counter",
        timeout=300,
        requires_approval=False,
    )


@pytest.fixture
def sample_action_result() -> ActionResult:
    """Create a sample action result for testing."""
    return ActionResult(
        status=ActionStatus.COMPLETED,
        success=True,
        message="Action completed successfully",
        execution_time=1.5,
        changes_made=["Change 1", "Change 2"],
        verification_passed=True,
        can_rollback=True,
        metadata={"key": "value"},
    )


@pytest.fixture
def rollback_manager(tmp_path: Path) -> RollbackManager:
    """Create a RollbackManager instance with temporary directory."""
    return RollbackManager(project_root=tmp_path)


@pytest.fixture
def action_registry() -> ActionRegistry:
    """Create an ActionRegistry instance with default executors."""
    registry = ActionRegistry()
    # Register all default executors
    registry.register_executor(ActionType.RETRY, RetryActionExecutor())
    registry.register_executor(ActionType.RECONFIGURE, ReconfigureActionExecutor())
    registry.register_executor(ActionType.RESTART, RestartActionExecutor())
    registry.register_executor(ActionType.PATCH, PatchActionExecutor())
    registry.register_executor(ActionType.ESCALATE, EscalateActionExecutor())
    return registry


# ============================================================================
# Enum Tests
# ============================================================================


class TestActionStatus:
    """Tests for ActionStatus enum."""

    def test_action_status_values(self) -> None:
        """Test ActionStatus enum values."""
        assert ActionStatus.PENDING.value == "pending"
        assert ActionStatus.IN_PROGRESS.value == "in_progress"
        assert ActionStatus.COMPLETED.value == "completed"
        assert ActionStatus.FAILED.value == "failed"
        assert ActionStatus.ROLLED_BACK.value == "rolled_back"
        assert ActionStatus.SKIPPED.value == "skipped"

    def test_action_status_is_string(self) -> None:
        """Test that status values are strings."""
        assert isinstance(ActionStatus.PENDING.value, str)


class TestActionType:
    """Tests for ActionType enum."""

    def test_action_type_values(self) -> None:
        """Test ActionType enum values."""
        assert ActionType.RETRY.value == "retry"
        assert ActionType.ROLLBACK.value == "rollback"
        assert ActionType.RECONFIGURE.value == "reconfigure"
        assert ActionType.RESTART.value == "restart"
        assert ActionType.SCALE.value == "scale"
        assert ActionType.ISOLATE.value == "isolate"
        assert ActionType.PATCH.value == "patch"
        assert ActionType.ESCALATE.value == "escalate"

    def test_action_type_is_string(self) -> None:
        """Test that type values are strings."""
        assert isinstance(ActionType.RETRY.value, str)


class TestActionSeverity:
    """Tests for ActionSeverity enum."""

    def test_action_severity_values(self) -> None:
        """Test ActionSeverity enum values."""
        assert ActionSeverity.LOW.value == "low"
        assert ActionSeverity.MEDIUM.value == "medium"
        assert ActionSeverity.HIGH.value == "high"
        assert ActionSeverity.CRITICAL.value == "critical"

    def test_action_severity_is_string(self) -> None:
        """Test that severity values are strings."""
        assert isinstance(ActionSeverity.LOW.value, str)


# ============================================================================
# ActionResult Tests
# ============================================================================


class TestActionResult:
    """Tests for ActionResult dataclass."""

    def test_action_result_init(self, sample_action_result: ActionResult) -> None:
        """Test ActionResult initialization."""
        assert sample_action_result.status == ActionStatus.COMPLETED
        assert sample_action_result.success is True
        assert sample_action_result.message == "Action completed successfully"
        assert sample_action_result.execution_time == 1.5
        assert len(sample_action_result.changes_made) == 2
        assert sample_action_result.verification_passed is True
        assert sample_action_result.can_rollback is True
        assert sample_action_result.metadata == {"key": "value"}

    def test_action_result_with_defaults(self) -> None:
        """Test ActionResult with default values."""
        result = ActionResult(
            status=ActionStatus.COMPLETED,
            success=True,
            message="Done",
        )

        assert result.error is None
        assert result.execution_time == 0.0
        assert result.changes_made == []
        assert result.verification_passed is False
        assert result.can_rollback is False
        assert result.rollback_action is None
        assert result.metadata == {}

    def test_action_result_to_dict(self, sample_action_result: ActionResult) -> None:
        """Test ActionResult to_dict method."""
        result_dict = sample_action_result.to_dict()

        assert result_dict["status"] == "completed"
        assert result_dict["success"] is True
        assert result_dict["message"] == "Action completed successfully"
        assert result_dict["execution_time"] == 1.5
        assert len(result_dict["changes_made"]) == 2
        assert result_dict["verification_passed"] is True
        assert result_dict["can_rollback"] is True

    def test_action_result_from_dict(self) -> None:
        """Test ActionResult from_dict class method."""
        data = {
            "status": "completed",
            "success": True,
            "message": "Test",
            "error": None,
            "execution_time": 2.5,
            "changes_made": ["Change"],
            "verification_passed": True,
            "can_rollback": False,
            "metadata": {"test": "data"},
            "timestamp": datetime.now().isoformat(),
        }

        result = ActionResult.from_dict(data)

        assert result.status == ActionStatus.COMPLETED
        assert result.success is True
        assert result.execution_time == 2.5
        assert result.verification_passed is True

    def test_action_result_from_dict_minimal(self) -> None:
        """Test ActionResult from_dict with minimal data."""
        data = {
            "status": "completed",
            "success": True,
            "message": "Test",
        }

        result = ActionResult.from_dict(data)

        assert result.status == ActionStatus.COMPLETED
        assert result.success is True
        assert result.execution_time == 0.0
        assert result.error is None


# ============================================================================
# HealingAction Tests
# ============================================================================


class TestHealingAction:
    """Tests for HealingAction dataclass."""

    def test_healing_action_init(self, sample_action: HealingAction) -> None:
        """Test HealingAction initialization."""
        assert sample_action.action_type == ActionType.RETRY
        assert sample_action.name == "Retry Failed Task"
        assert sample_action.severity == ActionSeverity.LOW
        assert sample_action.parameters["max_retries"] == 3
        assert sample_action.timeout == 300
        assert sample_action.requires_approval is False

    def test_healing_action_id_generation(self) -> None:
        """Test that action ID is auto-generated."""
        before = datetime.now()
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Test",
            description="Test action",
            severity=ActionSeverity.LOW,
        )
        after = datetime.now()

        assert len(action.id) > 0
        assert action.id.startswith("retry-")
        # Check timestamp is reasonable
        timestamp_str = action.id.split("-")[1]
        timestamp = int(timestamp_str)
        assert before.timestamp() <= timestamp <= after.timestamp()

    def test_healing_action_custom_id(self) -> None:
        """Test HealingAction with custom ID."""
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Test",
            description="Test",
            severity=ActionSeverity.LOW,
            id="custom-action-id",
        )

        assert action.id == "custom-action-id"

    def test_healing_action_to_dict(self, sample_action: HealingAction) -> None:
        """Test HealingAction to_dict method."""
        action_dict = sample_action.to_dict()

        assert action_dict["action_type"] == "retry"
        assert action_dict["name"] == "Retry Failed Task"
        assert action_dict["severity"] == "low"
        assert action_dict["parameters"]["max_retries"] == 3
        assert action_dict["timeout"] == 300
        assert action_dict["requires_approval"] is False

    def test_healing_action_from_dict(self) -> None:
        """Test HealingAction from_dict class method."""
        data = {
            "action_type": "retry",
            "name": "Test Action",
            "description": "Test description",
            "severity": "medium",
            "parameters": {"key": "value"},
            "preconditions": ["Precondition"],
            "expected_outcome": "Success",
            "rollback_strategy": "Revert",
            "timeout": 600,
            "requires_approval": True,
            "created_at": datetime.now().isoformat(),
            "id": "test-id",
        }

        action = HealingAction.from_dict(data)

        assert action.action_type == ActionType.RETRY
        assert action.name == "Test Action"
        assert action.severity == ActionSeverity.MEDIUM
        assert action.requires_approval is True

    def test_healing_action_from_dict_defaults(self) -> None:
        """Test HealingAction from_dict with default values."""
        data = {
            "action_type": "retry",
            "name": "Test",
            "description": "Test",
            "severity": "low",
        }

        action = HealingAction.from_dict(data)

        assert action.parameters == {}
        assert action.preconditions == []
        assert action.expected_outcome == ""
        assert action.rollback_strategy is None
        assert action.timeout == 300
        assert action.requires_approval is False

    def test_should_require_approval_explicit(self) -> None:
        """Test should_require_approval with explicit flag."""
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Test",
            description="Test",
            severity=ActionSeverity.LOW,
            requires_approval=True,
        )

        assert action.should_require_approval() is True

    def test_should_require_approval_high_severity(self) -> None:
        """Test should_require_approval for HIGH severity."""
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Test",
            description="Test",
            severity=ActionSeverity.HIGH,
            requires_approval=False,
        )

        assert action.should_require_approval() is True

    def test_should_require_approval_critical_severity(self) -> None:
        """Test should_require_approval for CRITICAL severity."""
        action = HealingAction(
            action_type=ActionType.ESCALATE,
            name="Test",
            description="Test",
            severity=ActionSeverity.CRITICAL,
            requires_approval=False,
        )

        assert action.should_require_approval() is True

    def test_should_require_approval_low_severity(self) -> None:
        """Test should_require_approval for LOW severity."""
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Test",
            description="Test",
            severity=ActionSeverity.LOW,
            requires_approval=False,
        )

        assert action.should_require_approval() is False


# ============================================================================
# RetryActionExecutor Tests
# ============================================================================


class TestRetryActionExecutor:
    """Tests for RetryActionExecutor."""

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """Test successful retry action execution."""
        executor = RetryActionExecutor()
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Retry Test",
            description="Test retry",
            severity=ActionSeverity.LOW,
            parameters={"max_retries": 5, "base_delay": 2.0},
        )

        result = await executor.execute(action)

        assert result.status == ActionStatus.COMPLETED
        assert result.success is True
        assert "5 attempts" in result.message
        assert "2.0s" in result.message
        assert result.can_rollback is False

    @pytest.mark.asyncio
    async def test_execute_default_parameters(self) -> None:
        """Test retry action with default parameters."""
        executor = RetryActionExecutor()
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Retry Test",
            description="Test retry",
            severity=ActionSeverity.LOW,
        )

        result = await executor.execute(action)

        assert result.success is True
        assert "3 attempts" in result.message  # Default max_retries
        assert "1.0s" in result.message  # Default base_delay

    @pytest.mark.asyncio
    async def test_verify_success(self) -> None:
        """Test successful verification."""
        executor = RetryActionExecutor()
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Retry Test",
            description="Test",
            severity=ActionSeverity.LOW,
            parameters={"max_retries": 3},
        )

        verified = await executor.verify(action)

        assert verified is True

    @pytest.mark.asyncio
    async def test_verify_zero_retries(self) -> None:
        """Test verification fails with zero retries."""
        executor = RetryActionExecutor()
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Retry Test",
            description="Test",
            severity=ActionSeverity.LOW,
            parameters={"max_retries": 0},
        )

        verified = await executor.verify(action)

        assert verified is False

    @pytest.mark.asyncio
    async def test_rollback(self) -> None:
        """Test rollback operation."""
        executor = RetryActionExecutor()
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Retry Test",
            description="Test",
            severity=ActionSeverity.LOW,
        )

        result = await executor.rollback(action)

        assert result.status == ActionStatus.ROLLED_BACK
        assert result.success is True
        assert "reset to defaults" in result.message.lower()


# ============================================================================
# ReconfigureActionExecutor Tests
# ============================================================================


class TestReconfigureActionExecutor:
    """Tests for ReconfigureActionExecutor."""

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """Test successful reconfigure action execution."""
        executor = ReconfigureActionExecutor()
        action = HealingAction(
            action_type=ActionType.RECONFIGURE,
            name="Reconfigure Test",
            description="Test reconfigure",
            severity=ActionSeverity.MEDIUM,
            parameters={
                "config_changes": {
                    "timeout": 60,
                    "retries": 5,
                    "debug": True,
                }
            },
        )

        result = await executor.execute(action)

        assert result.status == ActionStatus.COMPLETED
        assert result.success is True
        assert "3 configuration changes" in result.message
        assert len(result.changes_made) == 3
        assert result.can_rollback is True

    @pytest.mark.asyncio
    async def test_execute_no_changes(self) -> None:
        """Test reconfigure with no changes."""
        executor = ReconfigureActionExecutor()
        action = HealingAction(
            action_type=ActionType.RECONFIGURE,
            name="Reconfigure Test",
            description="Test",
            severity=ActionSeverity.MEDIUM,
            parameters={"config_changes": {}},
        )

        result = await executor.execute(action)

        assert result.success is True
        assert "0 configuration changes" in result.message

    @pytest.mark.asyncio
    async def test_verify_success(self) -> None:
        """Test successful verification."""
        executor = ReconfigureActionExecutor()
        action = HealingAction(
            action_type=ActionType.RECONFIGURE,
            name="Reconfigure Test",
            description="Test",
            severity=ActionSeverity.MEDIUM,
            parameters={"config_changes": {"key": "value"}},
        )

        verified = await executor.verify(action)

        assert verified is True

    @pytest.mark.asyncio
    async def test_verify_no_changes(self) -> None:
        """Test verification fails with no changes."""
        executor = ReconfigureActionExecutor()
        action = HealingAction(
            action_type=ActionType.RECONFIGURE,
            name="Reconfigure Test",
            description="Test",
            severity=ActionSeverity.MEDIUM,
            parameters={"config_changes": {}},
        )

        verified = await executor.verify(action)

        assert verified is False

    @pytest.mark.asyncio
    async def test_rollback(self) -> None:
        """Test rollback operation."""
        executor = ReconfigureActionExecutor()
        action = HealingAction(
            action_type=ActionType.RECONFIGURE,
            name="Reconfigure Test",
            description="Test",
            severity=ActionSeverity.MEDIUM,
        )

        result = await executor.rollback(action)

        assert result.status == ActionStatus.ROLLED_BACK
        assert result.success is True
        assert "reverted" in result.message.lower()


# ============================================================================
# RestartActionExecutor Tests
# ============================================================================


class TestRestartActionExecutor:
    """Tests for RestartActionExecutor."""

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """Test successful restart action execution."""
        executor = RestartActionExecutor()
        action = HealingAction(
            action_type=ActionType.RESTART,
            name="Restart Service",
            description="Restart the service",
            severity=ActionSeverity.MEDIUM,
            parameters={"target": "api-service"},
        )

        result = await executor.execute(action)

        assert result.status == ActionStatus.COMPLETED
        assert result.success is True
        assert "api-service" in result.message
        assert len(result.changes_made) == 1
        assert result.can_rollback is False

    @pytest.mark.asyncio
    async def test_execute_default_target(self) -> None:
        """Test restart with default target."""
        executor = RestartActionExecutor()
        action = HealingAction(
            action_type=ActionType.RESTART,
            name="Restart",
            description="Test",
            severity=ActionSeverity.MEDIUM,
        )

        result = await executor.execute(action)

        assert result.success is True
        assert "service" in result.message

    @pytest.mark.asyncio
    async def test_verify(self) -> None:
        """Test verification."""
        executor = RestartActionExecutor()
        action = HealingAction(
            action_type=ActionType.RESTART,
            name="Restart",
            description="Test",
            severity=ActionSeverity.MEDIUM,
            parameters={"target": "database"},
        )

        verified = await executor.verify(action)

        assert verified is True

    @pytest.mark.asyncio
    async def test_rollback_no_op(self) -> None:
        """Test that restart doesn't need rollback."""
        executor = RestartActionExecutor()
        action = HealingAction(
            action_type=ActionType.RESTART,
            name="Restart",
            description="Test",
            severity=ActionSeverity.MEDIUM,
        )

        result = await executor.rollback(action)

        assert result.status == ActionStatus.COMPLETED  # Not ROLLED_BACK
        assert result.success is True
        assert "self-contained" in result.message.lower()
        assert "no rollback needed" in result.message.lower()


# ============================================================================
# PatchActionExecutor Tests
# ============================================================================


class TestPatchActionExecutor:
    """Tests for PatchActionExecutor."""

    @pytest.mark.asyncio
    async def test_execute_with_patch_file(self) -> None:
        """Test patch action with file."""
        executor = PatchActionExecutor()
        action = HealingAction(
            action_type=ActionType.PATCH,
            name="Apply Patch",
            description="Apply code patch",
            severity=ActionSeverity.HIGH,
            parameters={"patch_file": "/path/to/patch.diff"},
        )

        result = await executor.execute(action)

        assert result.status == ActionStatus.COMPLETED
        assert result.success is True
        assert "patch.diff" in result.message
        assert result.can_rollback is True
        assert action.id in executor._applied_patches

    @pytest.mark.asyncio
    async def test_execute_with_patch_content(self) -> None:
        """Test patch action with inline content."""
        executor = PatchActionExecutor()
        action = HealingAction(
            action_type=ActionType.PATCH,
            name="Apply Patch",
            description="Apply inline patch",
            severity=ActionSeverity.HIGH,
            parameters={"patch_content": "- line1\n+ line2\n"},
        )

        result = await executor.execute(action)

        assert result.success is True
        assert "inline content" in result.message
        assert action.id in executor._applied_patches

    @pytest.mark.asyncio
    async def test_execute_missing_patch(self) -> None:
        """Test patch action fails without patch specification."""
        executor = PatchActionExecutor()
        action = HealingAction(
            action_type=ActionType.PATCH,
            name="Apply Patch",
            description="Test",
            severity=ActionSeverity.HIGH,
            parameters={},
        )

        result = await executor.execute(action)

        assert result.status == ActionStatus.FAILED
        assert result.success is False
        assert "no patch specified" in result.message.lower()
        assert result.error is not None
        assert result.can_rollback is False

    @pytest.mark.asyncio
    async def test_verify(self) -> None:
        """Test verification."""
        executor = PatchActionExecutor()
        action = HealingAction(
            action_type=ActionType.PATCH,
            name="Patch",
            description="Test",
            severity=ActionSeverity.HIGH,
            parameters={"patch_file": "/path/to/patch.diff"},
        )

        verified = await executor.verify(action)

        assert verified is True

    @pytest.mark.asyncio
    async def test_rollback(self) -> None:
        """Test rollback removes patch tracking."""
        executor = PatchActionExecutor()
        action = HealingAction(
            action_type=ActionType.PATCH,
            name="Patch",
            description="Test",
            severity=ActionSeverity.HIGH,
        )

        # First apply the patch
        await executor.execute(action)
        assert action.id in executor._applied_patches

        # Then rollback
        result = await executor.rollback(action)

        assert result.status == ActionStatus.ROLLED_BACK
        assert result.success is True
        assert "reverted" in result.message.lower()
        assert action.id not in executor._applied_patches


# ============================================================================
# EscalateActionExecutor Tests
# ============================================================================


class TestEscalateActionExecutor:
    """Tests for EscalateActionExecutor."""

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """Test successful escalate action execution."""
        executor = EscalateActionExecutor()
        action = HealingAction(
            action_type=ActionType.ESCALATE,
            name="Escalate Issue",
            description="Escalate to human operator",
            severity=ActionSeverity.CRITICAL,
            parameters={
                "severity": "critical",
                "message": "Critical failure detected",
                "recipients": ["admin@example.com", "ops@example.com"],
            },
        )

        result = await executor.execute(action)

        assert result.status == ActionStatus.COMPLETED
        assert result.success is True
        assert "critical" in result.message
        # Check changes_made for recipient information
        assert any("recipients" in change for change in result.changes_made)
        assert result.can_rollback is False

    @pytest.mark.asyncio
    async def test_execute_no_recipients(self) -> None:
        """Test escalate without recipients."""
        executor = EscalateActionExecutor()
        action = HealingAction(
            action_type=ActionType.ESCALATE,
            name="Escalate",
            description="Test",
            severity=ActionSeverity.CRITICAL,
            parameters={"severity": "high"},
        )

        result = await executor.execute(action)

        assert result.success is True
        # Check changes_made for logged escalation (no recipients)
        assert any("logged" in change.lower() for change in result.changes_made)

    @pytest.mark.asyncio
    async def test_verify(self) -> None:
        """Test verification."""
        executor = EscalateActionExecutor()
        action = HealingAction(
            action_type=ActionType.ESCALATE,
            name="Escalate",
            description="Test",
            severity=ActionSeverity.CRITICAL,
            parameters={"message": "Test escalation message"},
        )

        verified = await executor.verify(action)

        assert verified is True

    @pytest.mark.asyncio
    async def test_rollback_not_supported(self) -> None:
        """Test that escalation doesn't support rollback."""
        executor = EscalateActionExecutor()
        action = HealingAction(
            action_type=ActionType.ESCALATE,
            name="Escalate",
            description="Test",
            severity=ActionSeverity.CRITICAL,
        )

        result = await executor.rollback(action)

        assert result.status == ActionStatus.COMPLETED  # Not ROLLED_BACK
        assert result.success is True
        assert "cannot be rolled back" in result.message.lower()


# ============================================================================
# RollbackManager Tests
# ============================================================================


class TestRollbackManager:
    """Tests for RollbackManager."""

    def test_init(self, rollback_manager: RollbackManager) -> None:
        """Test RollbackManager initialization."""
        assert rollback_manager.project_root is not None
        assert len(rollback_manager._checkpoints) == 0
        assert rollback_manager._checkpoint_dir.name == "checkpoints"

    def test_init_default_project_root(self) -> None:
        """Test initialization with default project root."""
        manager = RollbackManager()
        assert manager.project_root == Path.cwd()

    def test_create_checkpoint(self, rollback_manager: RollbackManager) -> None:
        """Test checkpoint creation."""
        checkpoint = rollback_manager.create_checkpoint(
            action_id="action-123",
            metadata={"task_id": "task-456"},
        )

        assert checkpoint["action_id"] == "action-123"
        assert "timestamp" in checkpoint
        assert checkpoint["metadata"]["task_id"] == "task-456"
        assert "git_head" in checkpoint
        assert "action-123" in rollback_manager._checkpoints

    def test_create_checkpoint_without_metadata(
        self, rollback_manager: RollbackManager
    ) -> None:
        """Test checkpoint creation without metadata."""
        checkpoint = rollback_manager.create_checkpoint(action_id="action-123")

        assert checkpoint["action_id"] == "action-123"
        assert checkpoint["metadata"] == {}

    def test_rollback_to_checkpoint_success(
        self, rollback_manager: RollbackManager
    ) -> None:
        """Test successful rollback to checkpoint."""
        rollback_manager.create_checkpoint(action_id="action-123")

        result = rollback_manager.rollback_to_checkpoint("action-123")

        assert result is True
        # Checkpoint should still be removed after rollback
        assert "action-123" not in rollback_manager._checkpoints

    def test_rollback_to_checkpoint_not_found(
        self, rollback_manager: RollbackManager
    ) -> None:
        """Test rollback to non-existent checkpoint."""
        result = rollback_manager.rollback_to_checkpoint("non-existent")

        assert result is False

    def test_get_checkpoint(self, rollback_manager: RollbackManager) -> None:
        """Test getting checkpoint information."""
        created = rollback_manager.create_checkpoint(
            action_id="action-123",
            metadata={"key": "value"},
        )

        retrieved = rollback_manager.get_checkpoint("action-123")

        assert retrieved is not None
        assert retrieved["action_id"] == "action-123"
        assert retrieved["metadata"]["key"] == "value"

    def test_get_checkpoint_not_found(self, rollback_manager: RollbackManager) -> None:
        """Test getting non-existent checkpoint."""
        result = rollback_manager.get_checkpoint("non-existent")

        assert result is None

    def test_clear_checkpoint(self, rollback_manager: RollbackManager) -> None:
        """Test clearing a checkpoint."""
        rollback_manager.create_checkpoint(action_id="action-123")
        assert "action-123" in rollback_manager._checkpoints

        rollback_manager.clear_checkpoint("action-123")

        assert "action-123" not in rollback_manager._checkpoints

    def test_get_git_head(self, rollback_manager: RollbackManager) -> None:
        """Test git HEAD retrieval."""
        # Should return a string (possibly empty if not in git repo)
        git_head = rollback_manager._get_git_head()
        assert isinstance(git_head, str)


# ============================================================================
# ActionRegistry Tests
# ============================================================================


class TestActionRegistry:
    """Tests for ActionRegistry."""

    def test_init(self) -> None:
        """Test ActionRegistry initialization."""
        registry = ActionRegistry()

        # All built-in executors are registered by default
        assert len(registry._executors) == 5
        assert ActionType.RETRY in registry._executors
        assert ActionType.RECONFIGURE in registry._executors
        assert ActionType.RESTART in registry._executors
        assert ActionType.PATCH in registry._executors
        assert ActionType.ESCALATE in registry._executors
        assert len(registry._action_templates) == 0
        assert isinstance(registry._rollback_manager, RollbackManager)

    def test_register_executor(self, action_registry: ActionRegistry) -> None:
        """Test executor registration."""
        executor = RetryActionExecutor()
        action_registry.register_executor(ActionType.RETRY, executor)

        assert ActionType.RETRY in action_registry._executors
        assert action_registry._executors[ActionType.RETRY] == executor

    def test_register_template(self, action_registry: ActionRegistry) -> None:
        """Test action template registration."""
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Template Retry",
            description="Template",
            severity=ActionSeverity.LOW,
        )

        action_registry.register_template(action)

        assert ActionType.RETRY in action_registry._action_templates
        assert len(action_registry._action_templates[ActionType.RETRY]) == 1
        assert action_registry._action_templates[ActionType.RETRY][0] == action

    def test_register_multiple_templates(self, action_registry: ActionRegistry) -> None:
        """Test registering multiple templates for same type."""
        action1 = HealingAction(
            action_type=ActionType.RETRY,
            name="Template 1",
            description="Template 1",
            severity=ActionSeverity.LOW,
        )
        action2 = HealingAction(
            action_type=ActionType.RETRY,
            name="Template 2",
            description="Template 2",
            severity=ActionSeverity.MEDIUM,
        )

        action_registry.register_template(action1)
        action_registry.register_template(action2)

        templates = action_registry._action_templates[ActionType.RETRY]
        assert len(templates) == 2
        assert action1 in templates
        assert action2 in templates

    def test_get_executor(self, action_registry: ActionRegistry) -> None:
        """Test getting executor."""
        executor = action_registry.get_executor(ActionType.RETRY)

        assert executor is not None
        assert isinstance(executor, RetryActionExecutor)

    def test_get_executor_not_found(self, action_registry: ActionRegistry) -> None:
        """Test getting non-registered executor."""
        executor = action_registry.get_executor(ActionType.SCALE)

        assert executor is None

    def test_get_templates(self, action_registry: ActionRegistry) -> None:
        """Test getting templates for action type."""
        action1 = HealingAction(
            action_type=ActionType.RETRY,
            name="Template 1",
            description="T1",
            severity=ActionSeverity.LOW,
        )
        action2 = HealingAction(
            action_type=ActionType.RETRY,
            name="Template 2",
            description="T2",
            severity=ActionSeverity.MEDIUM,
        )
        action_registry.register_template(action1)
        action_registry.register_template(action2)

        templates = action_registry.get_templates(ActionType.RETRY)

        assert len(templates) == 2
        assert action1 in templates
        assert action2 in templates

    def test_get_templates_empty(self, action_registry: ActionRegistry) -> None:
        """Test getting templates when none registered."""
        templates = action_registry.get_templates(ActionType.SCALE)

        assert templates == []

    def test_create_action(self, action_registry: ActionRegistry) -> None:
        """Test creating a new action."""
        action = action_registry.create_action(
            action_type=ActionType.RETRY,
            name="New Action",
            description="New action description",
            severity=ActionSeverity.HIGH,
            parameters={"key": "value"},
            timeout=600,
        )

        assert action.action_type == ActionType.RETRY
        assert action.name == "New Action"
        assert action.severity == ActionSeverity.HIGH
        assert action.parameters["key"] == "value"
        assert action.timeout == 600

    def test_create_action_defaults(self, action_registry: ActionRegistry) -> None:
        """Test creating action with defaults."""
        action = action_registry.create_action(
            action_type=ActionType.RETRY,
            name="Simple Action",
            description="Simple",
        )

        assert action.severity == ActionSeverity.MEDIUM  # Default
        assert action.parameters == {}
        assert action.preconditions == []
        assert action.expected_outcome == ""
        assert action.timeout == 300
        assert action.requires_approval is False

    @pytest.mark.asyncio
    async def test_execute_action_success(
        self, action_registry: ActionRegistry, sample_config: HealingConfig
    ) -> None:
        """Test successful action execution through registry."""
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Test Retry",
            description="Test",
            severity=ActionSeverity.LOW,
            parameters={"max_retries": 5},
        )

        result = await action_registry.execute_action(action, sample_config)

        assert result.status == ActionStatus.COMPLETED
        assert result.success is True
        assert result.execution_time >= 0

    @pytest.mark.asyncio
    async def test_execute_action_no_executor(
        self, action_registry: ActionRegistry, sample_config: HealingConfig
    ) -> None:
        """Test action execution without registered executor."""
        action = HealingAction(
            action_type=ActionType.SCALE,  # Not registered
            name="Test Scale",
            description="Test",
            severity=ActionSeverity.HIGH,
        )

        result = await action_registry.execute_action(action, sample_config)

        assert result.status == ActionStatus.FAILED
        assert result.success is False
        assert "Executor not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_action_with_checkpoint(
        self, action_registry: ActionRegistry, sample_config: HealingConfig
    ) -> None:
        """Test that checkpoint is created during execution."""
        action = HealingAction(
            action_type=ActionType.RESTART,
            name="Test Restart",
            description="Test",
            severity=ActionSeverity.MEDIUM,
        )

        result = await action_registry.execute_action(action, sample_config)

        # Should succeed and checkpoint should be cleared
        assert result.success is True
        assert action.id not in action_registry._rollback_manager._checkpoints

    def test_get_registered_action_types(self, action_registry: ActionRegistry) -> None:
        """Test getting registered action types."""
        types = action_registry.get_registered_action_types()

        assert len(types) == 5  # We registered 5 executors
        assert ActionType.RETRY in types
        assert ActionType.RECONFIGURE in types
        assert ActionType.RESTART in types
        assert ActionType.PATCH in types
        assert ActionType.ESCALATE in types

    def test_get_registry_stats(self, action_registry: ActionRegistry) -> None:
        """Test getting registry statistics."""
        # Register a template
        action = HealingAction(
            action_type=ActionType.RETRY,
            name="Template",
            description="T",
            severity=ActionSeverity.LOW,
        )
        action_registry.register_template(action)

        stats = action_registry.get_registry_stats()

        assert stats["registered_executors"] == 5
        assert stats["registered_templates"] == 1
        assert len(stats["action_types"]) == 5
        assert "active_checkpoints" in stats


# ============================================================================
# Global Registry Tests
# ============================================================================


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_global_registry_singleton(self) -> None:
        """Test that global registry is a singleton."""
        registry1 = get_global_registry()
        registry2 = get_global_registry()

        assert registry1 is registry2

    def test_global_registry_type(self) -> None:
        """Test that global registry is correct type."""
        registry = get_global_registry()

        assert isinstance(registry, ActionRegistry)
