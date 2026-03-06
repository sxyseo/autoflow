"""
Autoflow Review Gates Module

This module provides verification and quality gate functionality for
automatic test execution, coverage analysis, and QA findings management.
"""

__version__ = "1.0.0"

# Import main components for easy access
# Only import modules that exist - others will be added as they're implemented
from .coverage import (
    CoverageTracker,
    CoverageThreshold,
    CoverageReport
)

__all__ = [
    "CoverageTracker",
    "CoverageThreshold",
    "CoverageReport",
]
