"""
Autoflow CI - Verification Gates

This module provides automated CI verification gates:
- CIVerifier: Run verification checks
- Gate definitions: Test, lint, and security gates

All gates must pass before code is committed, enabling
closed-loop autonomous development.
"""

from autoflow.ci.verifier import (
    CIVerifier,
    CIVerifierError,
    CIVerifierStats,
    CheckDefinition,
    CheckResult,
    CheckStatus,
    CheckType,
    VerificationResult,
    create_verifier,
)

# Gate components will be imported here as they are implemented
# from autoflow.ci.gates import TestGate, LintGate, SecurityGate

__all__ = [
    # Verifier
    "CIVerifier",
    "CIVerifierError",
    "CIVerifierStats",
    "CheckDefinition",
    "CheckResult",
    "CheckStatus",
    "CheckType",
    "VerificationResult",
    "create_verifier",
    # Gates (future)
    # "TestGate",
    # "LintGate",
    # "SecurityGate",
]
