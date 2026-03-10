"""
Autoflow CLI - Unified Command Line Interface

Provides commands for managing autonomous AI development workflows:
- Initialize and configure Autoflow
- Run tasks with AI agents
- Manage skills and schedulers
- Review code and verify CI gates

Usage:
    autoflow --help
    autoflow init
    autoflow status
    autoflow run "Fix the login bug"
    autoflow agent list
    autoflow skill list
    autoflow scheduler start

This module provides backward compatibility by re-exporting the main
CLI entry point from the modular cli.main module.
"""

from __future__ import annotations

# Import the main CLI from the modular structure for backward compatibility
from autoflow.cli.main import main

# Re-export all key items for backward compatibility
__all__ = ["main"]
