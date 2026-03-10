"""
Autoflow Core - Orchestration, Configuration, and State Management.

This package intentionally resolves exports lazily. Several lightweight entry
points import `autoflow.core.sanitization` in minimal environments where
optional dependencies like `pydantic` are not installed. Eagerly importing the
entire core package would fail those paths before they can use the sanitization
helpers.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    # Config
    "Config": ("autoflow.core.config", "Config"),
    "SystemConfig": ("autoflow.core.config", "SystemConfig"),
    "RepositoryConfig": ("autoflow.core.config", "RepositoryConfig"),
    "RepositoriesConfig": ("autoflow.core.config", "RepositoriesConfig"),
    "load_config": ("autoflow.core.config", "load_config"),
    "load_system_config": ("autoflow.core.config", "load_system_config"),
    "get_state_dir": ("autoflow.core.config", "get_state_dir"),
    "merge_configs": ("autoflow.core.config", "merge_configs"),
    "config_to_json5": ("autoflow.core.config", "config_to_json5"),
    # State
    "StateManager": ("autoflow.core.state", "StateManager"),
    "Task": ("autoflow.core.state", "Task"),
    "TaskStatus": ("autoflow.core.state", "TaskStatus"),
    "Run": ("autoflow.core.state", "Run"),
    "RunStatus": ("autoflow.core.state", "RunStatus"),
    "Spec": ("autoflow.core.state", "Spec"),
    "Memory": ("autoflow.core.state", "Memory"),
    "ParallelTaskGroup": ("autoflow.core.state", "ParallelTaskGroup"),
    "ParallelGroupStatus": ("autoflow.core.state", "ParallelGroupStatus"),
    "read_json": ("autoflow.core.state", "read_json"),
    "write_json": ("autoflow.core.state", "write_json"),
    # Orchestrator
    "AutoflowOrchestrator": ("autoflow.core.orchestrator", "AutoflowOrchestrator"),
    "OrchestratorStatus": ("autoflow.core.orchestrator", "OrchestratorStatus"),
    "OrchestratorStats": ("autoflow.core.orchestrator", "OrchestratorStats"),
    "CyclePhase": ("autoflow.core.orchestrator", "CyclePhase"),
    "CycleResult": ("autoflow.core.orchestrator", "CycleResult"),
    "OrchestratorError": ("autoflow.core.orchestrator", "OrchestratorError"),
}


def __getattr__(name: str) -> Any:
    """Resolve core exports on first access."""
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazily loaded exports for introspection."""
    return sorted(set(globals()) | set(_EXPORTS))

__all__ = [
    # Config
    "Config",
    "SystemConfig",
    "RepositoryConfig",
    "RepositoriesConfig",
    "load_config",
    "load_system_config",
    "get_state_dir",
    "merge_configs",
    "config_to_json5",
    # State
    "StateManager",
    "Task",
    "TaskStatus",
    "Run",
    "RunStatus",
    "Spec",
    "Memory",
    "ParallelTaskGroup",
    "ParallelGroupStatus",
    "read_json",
    "write_json",
    # Orchestrator
    "AutoflowOrchestrator",
    "OrchestratorStatus",
    "OrchestratorStats",
    "CyclePhase",
    "CycleResult",
    "OrchestratorError",
]
