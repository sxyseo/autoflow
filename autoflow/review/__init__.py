"""
Autoflow Review Gates Module

This module provides verification and quality gate functionality for
automatic test execution, coverage analysis, and QA findings management.
"""

__version__ = "1.0.0"

# Import main components for easy access
from .verification import VerificationOrchestrator
from .coverage import CoverageTracker
from .qa_findings import QAFindings, SeverityLevel
from .approval import ApprovalGate

__all__ = [
    "VerificationOrchestrator",
    "CoverageTracker",
    "QAFindings",
    "SeverityLevel",
    "ApprovalGate",
]
