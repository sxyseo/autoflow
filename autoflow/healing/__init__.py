"""Self-healing workflows module for autonomous workflow repair.

This module provides comprehensive self-healing capabilities that detect workflow
degradation, diagnose root causes, and apply automatic fixes with rollback safety.
"""

from __future__ import annotations

from autoflow.healing.actions import (
    ActionExecutor,
    ActionResult,
    ActionRegistry,
    ActionSeverity,
    ActionStatus,
    ActionType,
    HealingAction,
    RollbackManager,
    get_global_registry,
)
from autoflow.healing.config import HealingConfig, HealingThreshold
from autoflow.healing.diagnostic import (
    ConfidenceLevel,
    DiagnosticResult,
    FailureCategory,
    HealingPlan,
    HealingStrategy,
    RootCause,
    StrategyEvaluation,
    StrategySelector,
)
from autoflow.healing.monitor import (
    HealthAssessment,
    MetricReading,
    TaskExecution,
    WorkflowHealthMonitor,
    WorkflowHealthStatus,
)
from autoflow.healing.orchestrator import (
    EscalationManager,
    HealingEvent,
    HealingEventLogger,
    HealingOrchestrator,
    HealingOutcome,
    HealingSession,
    OrchestratorState,
)

__all__ = [
    "HealingConfig",
    "HealingThreshold",
    "WorkflowHealthMonitor",
    "WorkflowHealthStatus",
    "HealthAssessment",
    "MetricReading",
    "TaskExecution",
    "DiagnosticResult",
    "HealingStrategy",
    "FailureCategory",
    "ConfidenceLevel",
    "RootCause",
    "StrategyEvaluation",
    "HealingPlan",
    "StrategySelector",
    "HealingAction",
    "ActionResult",
    "ActionType",
    "ActionStatus",
    "ActionSeverity",
    "ActionExecutor",
    "ActionRegistry",
    "RollbackManager",
    "get_global_registry",
    "HealingOrchestrator",
    "OrchestratorState",
    "HealingOutcome",
    "HealingEvent",
    "HealingSession",
    "HealingEventLogger",
    "EscalationManager",
]
