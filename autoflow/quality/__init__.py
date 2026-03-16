"""
Autoflow Quality Assurance Module

Provides tools for ensuring code quality, completion standards,
and comprehensive testing beyond simple unit tests.
"""

from autoflow.quality.completion_checker import (
    CheckResult,
    CompletionChecker,
    CompletionStandard,
)

__all__ = [
    "CheckResult",
    "CompletionChecker",
    "CompletionStandard",
]
