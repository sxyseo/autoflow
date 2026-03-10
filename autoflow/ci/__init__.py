"""
Autoflow CI - Verification Gates

This module provides automated CI verification gates:
- CIVerifier: Run verification checks
- Gate definitions: Test, lint, and security gates

All gates must pass before code is committed, enabling
closed-loop autonomous development.
"""

from autoflow.ci.gates import (
    BaseGate,
    GateConfig,
    GateResult,
    GateRunner,
    GateRunnerResult,
    GateSeverity,
    GateStatus,
    LintGate,
    SecurityGate,
    TestGate,
    TypeCheckGate,
    create_default_gates,
    create_default_runner,
)
from autoflow.ci.verifier import (
    CheckDefinition,
    CheckResult,
    CheckStatus,
    CheckType,
    CIVerifier,
    CIVerifierError,
    CIVerifierStats,
    VerificationResult,
    create_verifier,
)

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
    # Gates
    "BaseGate",
    "GateConfig",
    "GateResult",
    "GateRunner",
    "GateRunnerResult",
    "GateSeverity",
    "GateStatus",
    "LintGate",
    "SecurityGate",
    "TestGate",
    "TypeCheckGate",
    "create_default_gates",
    "create_default_runner",
]
