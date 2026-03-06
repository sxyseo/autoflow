"""
Continuous Integration module for Autoflow.

This package provides CI-related functionality including health checks,
verification runners, and quality gates.
"""

from autoflow.ci.health_check import HealthCheckRunner

__all__ = ["HealthCheckRunner"]
