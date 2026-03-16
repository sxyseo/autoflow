#!/usr/bin/env python3
"""
Autoflow Analysis Module

Provides code analysis capabilities including duplication detection,
code similarity analysis, and structural pattern matching.
Integrates with the verification system to detect and prevent
code duplication before it reaches the codebase.
"""

from autoflow.analysis.duplication_detector import (
    DuplicationDetector,
    DuplicationFinding,
    DuplicationReport,
    DuplicationThreshold,
)

__all__ = [
    "DuplicationDetector",
    "DuplicationFinding",
    "DuplicationReport",
    "DuplicationThreshold",
]
