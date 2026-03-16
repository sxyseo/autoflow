"""
Autoflow Orchestration Module

Provides orchestration functionality for autonomous workflow coordination.
This module extracts business logic from scripts/autonomy_orchestrator.py
and scripts/cli_healthcheck.py into testable functions.

Usage:
    from autoflow.orchestration.autonomy import coordination_brief, probe_binary

    brief = coordination_brief(spec, continuous_config, config, root)
    status = probe_binary("codex")
"""

from __future__ import annotations

from autoflow.orchestration.autonomy import (
    AutonomyOrchestrator,
    build_report,
    coordination_brief,
    health_report,
    now_stamp,
    probe_binary,
    run_tick,
    taskmaster_sync,
    tmux_sessions,
)

__all__ = [
    "AutonomyOrchestrator",
    "coordination_brief",
    "health_report",
    "taskmaster_sync",
    "run_tick",
    "probe_binary",
    "tmux_sessions",
    "build_report",
    "now_stamp",
]
