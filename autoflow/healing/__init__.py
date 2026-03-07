"""Self-healing workflows module for autonomous workflow repair.

This module provides comprehensive self-healing capabilities that detect workflow
degradation, diagnose root causes, and apply automatic fixes with rollback safety.
"""

from __future__ import annotations

from autoflow.healing.config import HealingConfig, HealingThreshold

__all__ = [
    "HealingConfig",
    "HealingThreshold",
]
