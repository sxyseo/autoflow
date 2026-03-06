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
from .approval import (
    ApprovalToken,
    ApprovalGateConfig,
    ApprovalGate,
    create_git_commit_message_with_approval,
    extract_approval_hash_from_commit
)
from .verification import (
    VerificationOrchestrator,
    VerificationResult,
    VerificationConfig,
    create_verification_report
)

__all__ = [
    "CoverageTracker",
    "CoverageThreshold",
    "CoverageReport",
    "ApprovalToken",
    "ApprovalGateConfig",
    "ApprovalGate",
    "create_git_commit_message_with_approval",
    "extract_approval_hash_from_commit",
    "VerificationOrchestrator",
    "VerificationResult",
    "VerificationConfig",
    "create_verification_report",
]
