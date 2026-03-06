"""
Automatic rollback and recovery system for Autoflow.

This package provides health checks, checkpoint management, and automatic
rollback capabilities to detect when AI changes break functionality and
revert to the last known good state.
"""

from autoflow.rollback.health import HealthCheck, HealthStatus

__all__ = ["HealthCheck", "HealthStatus"]
